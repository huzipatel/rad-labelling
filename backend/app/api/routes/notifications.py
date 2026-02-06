"""Notification settings and management routes."""
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.models.user import User
from app.models.notification import NotificationSettings, UserNotificationPreferences, NotificationLog
from app.api.deps import require_manager, require_admin, get_current_user
from app.tasks.notification_tasks import (
    send_daily_performance_summary,
    send_daily_labeller_reminders,
    send_task_completion_notification
)


router = APIRouter(prefix="/notifications", tags=["Notifications"])


# Request/Response Models
class NotificationSettingsUpdate(BaseModel):
    """Update notification settings request."""
    daily_summary_enabled: Optional[bool] = None
    daily_summary_time: Optional[str] = None  # HH:MM format
    daily_summary_admin_id: Optional[str] = None
    task_completion_enabled: Optional[bool] = None
    daily_reminders_enabled: Optional[bool] = None
    daily_reminder_time: Optional[str] = None  # HH:MM format


class NotificationSettingsResponse(BaseModel):
    """Notification settings response."""
    id: str
    daily_summary_enabled: bool
    daily_summary_time: str
    daily_summary_admin_id: Optional[str]
    daily_summary_admin_name: Optional[str] = None
    task_completion_enabled: bool
    daily_reminders_enabled: bool
    daily_reminder_time: str
    updated_at: datetime


class UserPreferencesUpdate(BaseModel):
    """Update user notification preferences."""
    opt_out_daily_reminders: Optional[bool] = None
    opt_out_task_assignments: Optional[bool] = None
    opt_out_all_whatsapp: Optional[bool] = None


class UserPreferencesResponse(BaseModel):
    """User notification preferences response."""
    opt_out_daily_reminders: bool
    opt_out_task_assignments: bool
    opt_out_all_whatsapp: bool
    opt_out_date: Optional[datetime]


class NotificationLogResponse(BaseModel):
    """Notification log entry response."""
    id: str
    notification_type: str
    recipient_number: str
    message_preview: str
    status: str
    error_message: Optional[str]
    created_at: datetime
    sent_at: Optional[datetime]


# Admin endpoints
@router.get("/settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get current notification settings."""
    result = await db.execute(select(NotificationSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    # Create default settings if none exist
    if not settings:
        settings = NotificationSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    # Get admin name if set
    admin_name = None
    if settings.daily_summary_admin_id:
        admin_result = await db.execute(
            select(User).where(User.id == settings.daily_summary_admin_id)
        )
        admin = admin_result.scalar_one_or_none()
        if admin:
            admin_name = admin.name
    
    return NotificationSettingsResponse(
        id=str(settings.id),
        daily_summary_enabled=settings.daily_summary_enabled,
        daily_summary_time=settings.daily_summary_time,
        daily_summary_admin_id=str(settings.daily_summary_admin_id) if settings.daily_summary_admin_id else None,
        daily_summary_admin_name=admin_name,
        task_completion_enabled=settings.task_completion_enabled,
        daily_reminders_enabled=settings.daily_reminders_enabled,
        daily_reminder_time=settings.daily_reminder_time,
        updated_at=settings.updated_at
    )


@router.patch("/settings", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    updates: NotificationSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update notification settings (admin only)."""
    result = await db.execute(select(NotificationSettings).limit(1))
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = NotificationSettings()
        db.add(settings)
    
    # Apply updates
    if updates.daily_summary_enabled is not None:
        settings.daily_summary_enabled = updates.daily_summary_enabled
    if updates.daily_summary_time is not None:
        # Validate time format
        try:
            datetime.strptime(updates.daily_summary_time, "%H:%M")
            settings.daily_summary_time = updates.daily_summary_time
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid time format. Use HH:MM"
            )
    if updates.daily_summary_admin_id is not None:
        # Validate admin exists and has WhatsApp number
        admin_result = await db.execute(
            select(User).where(User.id == uuid.UUID(updates.daily_summary_admin_id))
        )
        admin = admin_result.scalar_one_or_none()
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin user not found"
            )
        if not admin.whatsapp_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected admin does not have a WhatsApp number configured"
            )
        settings.daily_summary_admin_id = uuid.UUID(updates.daily_summary_admin_id)
    if updates.task_completion_enabled is not None:
        settings.task_completion_enabled = updates.task_completion_enabled
    if updates.daily_reminders_enabled is not None:
        settings.daily_reminders_enabled = updates.daily_reminders_enabled
    if updates.daily_reminder_time is not None:
        try:
            datetime.strptime(updates.daily_reminder_time, "%H:%M")
            settings.daily_reminder_time = updates.daily_reminder_time
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid time format. Use HH:MM"
            )
    
    await db.commit()
    await db.refresh(settings)
    
    # Get admin name
    admin_name = None
    if settings.daily_summary_admin_id:
        admin_result = await db.execute(
            select(User).where(User.id == settings.daily_summary_admin_id)
        )
        admin = admin_result.scalar_one_or_none()
        if admin:
            admin_name = admin.name
    
    return NotificationSettingsResponse(
        id=str(settings.id),
        daily_summary_enabled=settings.daily_summary_enabled,
        daily_summary_time=settings.daily_summary_time,
        daily_summary_admin_id=str(settings.daily_summary_admin_id) if settings.daily_summary_admin_id else None,
        daily_summary_admin_name=admin_name,
        task_completion_enabled=settings.task_completion_enabled,
        daily_reminders_enabled=settings.daily_reminders_enabled,
        daily_reminder_time=settings.daily_reminder_time,
        updated_at=settings.updated_at
    )


@router.post("/test/daily-summary")
async def test_daily_summary(
    direct: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Send a test daily summary notification (admin only).
    
    Args:
        direct: If True, send directly without Celery (for testing when Celery isn't running)
    """
    if not direct:
        # Queue the task via Celery
        try:
            task = send_daily_performance_summary.delay()
            return {"message": "Daily summary notification queued", "task_id": str(task.id)}
        except Exception as e:
            return {"message": f"Failed to queue task (Celery may not be running): {str(e)}", "error": True}
    
    # Direct send - bypass Celery for immediate testing
    try:
        from app.services.whatsapp_service import whatsapp_service
        from sqlalchemy import func
        from datetime import datetime
        from app.models.label import Label
        from app.models.task import Task
        
        # Get notification settings
        try:
            result = await db.execute(select(NotificationSettings).limit(1))
            settings_obj = result.scalar_one_or_none()
        except Exception as e:
            return {"message": f"Database error fetching notification settings: {str(e)}", "error": True}
        
        if not settings_obj:
            return {"message": "No notification settings found. Please configure settings first.", "error": True}
        
        if not settings_obj.daily_summary_enabled:
            return {"message": "Daily summary is disabled. Enable it in settings first.", "error": True}
        
        if not settings_obj.daily_summary_admin_id:
            return {"message": "No admin selected for daily summary. Select an admin in settings.", "error": True}
        
        # Get admin user
        try:
            admin_result = await db.execute(
                select(User).where(User.id == settings_obj.daily_summary_admin_id)
            )
            admin = admin_result.scalar_one_or_none()
        except Exception as e:
            return {"message": f"Database error fetching admin user: {str(e)}", "error": True}
        
        if not admin:
            return {"message": "Selected admin user not found.", "error": True}
        
        if not admin.whatsapp_number:
            return {"message": f"Admin '{admin.name}' does not have a WhatsApp number configured.", "error": True}
        
        # Check if WhatsApp service is enabled
        if not whatsapp_service.enabled:
            return {
                "message": "WhatsApp service not enabled. Check Twilio credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER).",
                "error": True
            }
        
        # Calculate today's stats
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get total labels today (with error handling)
        try:
            labels_result = await db.execute(
                select(func.count(Label.id)).where(Label.created_at >= today_start)
            )
            total_labels = labels_result.scalar() or 0
        except Exception as e:
            print(f"[Notifications] Error counting labels: {e}")
            total_labels = 0
        
        # Get labeller stats (with error handling)
        labeller_stats = []
        try:
            labeller_stats_result = await db.execute(
                select(
                    User.name,
                    func.count(Label.id).label('labels')
                ).join(
                    Label, Label.labeller_id == User.id
                ).where(
                    Label.created_at >= today_start
                ).group_by(
                    User.id, User.name
                ).order_by(
                    func.count(Label.id).desc()
                )
            )
            labeller_stats = [
                {"name": row.name, "labels": row.labels}
                for row in labeller_stats_result.all()
            ]
        except Exception as e:
            print(f"[Notifications] Error getting labeller stats: {e}")
            labeller_stats = []
        
        # Get tasks completed today (with error handling)
        tasks_completed = []
        try:
            tasks_result = await db.execute(
                select(Task.name).where(
                    Task.status == "completed",
                    Task.updated_at >= today_start
                )
            )
            tasks_completed = [row[0] for row in tasks_result.all() if row[0]]
        except Exception as e:
            print(f"[Notifications] Error getting completed tasks: {e}")
            tasks_completed = []
        
        # Send notification directly
        try:
            success = whatsapp_service.send_daily_performance_summary(
                to_number=admin.whatsapp_number,
                total_labels_today=total_labels,
                total_images_today=total_labels,  # Approximation
                labeller_stats=labeller_stats,
                tasks_completed=tasks_completed
            )
            
            if success:
                # Log the notification
                try:
                    from app.models.notification import NotificationLog
                    log = NotificationLog(
                        notification_type="daily_summary",
                        recipient_id=admin.id,
                        recipient_number=admin.whatsapp_number,
                        message_preview=f"Test daily summary: {total_labels} labels",
                        status="sent"
                    )
                    db.add(log)
                    await db.commit()
                except Exception as log_error:
                    print(f"[Notifications] Error logging notification: {log_error}")
                    # Don't fail the whole request just because logging failed
                
                return {
                    "message": f"WhatsApp message sent successfully to {admin.whatsapp_number}",
                    "recipient": admin.name,
                    "stats": {
                        "total_labels": total_labels,
                        "labellers": len(labeller_stats),
                        "tasks_completed": len(tasks_completed)
                    }
                }
            else:
                return {
                    "message": f"Failed to send WhatsApp message to {admin.whatsapp_number}. Check Render logs for details.",
                    "error": True,
                    "hint": "Common issues: (1) Recipient hasn't joined Twilio sandbox, (2) Invalid phone number format, (3) Twilio credentials expired"
                }
        except Exception as e:
            return {
                "message": f"Error sending WhatsApp message: {str(e)}",
                "error": True
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "message": f"Unexpected error in test_daily_summary: {str(e)}",
            "error": True
        }


@router.post("/test/labeller-reminders")
async def test_labeller_reminders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Send test daily reminders to all labellers (admin only)."""
    try:
        task = send_daily_labeller_reminders.delay()
        return {"message": "Labeller reminders queued", "task_id": str(task.id)}
    except Exception as e:
        return {"message": f"Failed to queue task (Celery may not be running): {str(e)}", "error": True}


@router.get("/diagnostic")
async def whatsapp_diagnostic(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Diagnostic endpoint to check WhatsApp notification setup.
    Returns detailed status of all components.
    """
    from app.services.whatsapp_service import whatsapp_service
    from app.core.config import settings as app_settings
    
    issues = []
    warnings = []
    
    # Check Twilio credentials
    twilio_status = {
        "account_sid_set": bool(app_settings.TWILIO_ACCOUNT_SID),
        "auth_token_set": bool(app_settings.TWILIO_AUTH_TOKEN),
        "whatsapp_number_set": bool(app_settings.TWILIO_WHATSAPP_NUMBER),
        "whatsapp_number": app_settings.TWILIO_WHATSAPP_NUMBER if app_settings.TWILIO_WHATSAPP_NUMBER else None,
        "service_enabled": whatsapp_service.enabled,
        "client_initialized": whatsapp_service.client is not None
    }
    
    if not twilio_status["account_sid_set"]:
        issues.append("TWILIO_ACCOUNT_SID environment variable not set")
    if not twilio_status["auth_token_set"]:
        issues.append("TWILIO_AUTH_TOKEN environment variable not set")
    if not twilio_status["whatsapp_number_set"]:
        issues.append("TWILIO_WHATSAPP_NUMBER environment variable not set")
    if not twilio_status["service_enabled"]:
        issues.append("WhatsApp service is disabled due to missing credentials")
    
    # Check notification settings
    result = await db.execute(select(NotificationSettings).limit(1))
    settings_obj = result.scalar_one_or_none()
    
    settings_status = {
        "settings_exist": settings_obj is not None,
        "daily_summary_enabled": settings_obj.daily_summary_enabled if settings_obj else False,
        "daily_summary_admin_id": str(settings_obj.daily_summary_admin_id) if settings_obj and settings_obj.daily_summary_admin_id else None,
        "task_completion_enabled": settings_obj.task_completion_enabled if settings_obj else False,
        "daily_reminders_enabled": settings_obj.daily_reminders_enabled if settings_obj else False
    }
    
    if not settings_status["settings_exist"]:
        warnings.append("No notification settings configured yet")
    elif not settings_status["daily_summary_enabled"]:
        warnings.append("Daily summary notifications are disabled")
    elif not settings_status["daily_summary_admin_id"]:
        warnings.append("No admin selected to receive daily summaries")
    
    # Check admin user
    admin_status = None
    if settings_status["daily_summary_admin_id"]:
        admin_result = await db.execute(
            select(User).where(User.id == uuid.UUID(settings_status["daily_summary_admin_id"]))
        )
        admin = admin_result.scalar_one_or_none()
        
        if admin:
            admin_status = {
                "name": admin.name,
                "email": admin.email,
                "whatsapp_number": admin.whatsapp_number,
                "has_whatsapp": bool(admin.whatsapp_number)
            }
            if not admin.whatsapp_number:
                issues.append(f"Selected admin '{admin.name}' has no WhatsApp number configured")
        else:
            issues.append("Selected admin user not found in database")
    
    # Check users with WhatsApp numbers
    users_with_whatsapp = await db.execute(
        select(User).where(User.whatsapp_number.isnot(None), User.is_active == True)
    )
    whatsapp_users = users_with_whatsapp.scalars().all()
    
    users_status = {
        "total_with_whatsapp": len(whatsapp_users),
        "users": [
            {"name": u.name, "role": u.role, "whatsapp": u.whatsapp_number}
            for u in whatsapp_users[:10]  # Limit to 10
        ]
    }
    
    # Sandbox info
    sandbox_info = {
        "sandbox_number": "+14155238886",
        "how_to_join": "Text 'join <your-sandbox-code>' to the sandbox number from the recipient's phone",
        "note": "Each recipient must join the sandbox before they can receive messages"
    }
    
    return {
        "twilio": twilio_status,
        "settings": settings_status,
        "admin": admin_status,
        "users_with_whatsapp": users_status,
        "sandbox_info": sandbox_info,
        "issues": issues,
        "warnings": warnings,
        "ready_to_send": len(issues) == 0 and twilio_status["service_enabled"]
    }


class DirectTestRequest(BaseModel):
    """Request for direct WhatsApp test."""
    phone_number: str
    message: Optional[str] = None


@router.post("/test/direct")
async def test_whatsapp_direct(
    request: DirectTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Send a test WhatsApp message directly to a specific number.
    Useful for testing Twilio sandbox connectivity.
    
    Args:
        phone_number: Phone number in E.164 format (e.g., +447123456789)
        message: Optional custom message (defaults to a test message)
    """
    from app.services.whatsapp_service import whatsapp_service
    
    if not whatsapp_service.enabled:
        return {
            "success": False,
            "error": "WhatsApp service not enabled. Check Twilio credentials.",
            "hint": "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_NUMBER in environment"
        }
    
    # Validate phone number format
    phone = request.phone_number.strip()
    if not phone.startswith('+'):
        return {
            "success": False,
            "error": "Phone number must start with '+' (E.164 format)",
            "example": "+447123456789"
        }
    
    # Default test message
    message = request.message or f"""🧪 Test Message from AdVue UK

This is a test WhatsApp notification.

If you received this, your Twilio sandbox is working correctly!

Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    try:
        success = whatsapp_service.send_message(phone, message)
        
        if success:
            return {
                "success": True,
                "message": f"WhatsApp message sent to {phone}",
                "note": "Check your WhatsApp for the message"
            }
        else:
            return {
                "success": False,
                "error": f"Failed to send message to {phone}",
                "common_causes": [
                    "Recipient hasn't joined the Twilio sandbox",
                    "Invalid phone number format",
                    "Twilio credentials incorrect or expired"
                ],
                "sandbox_join_instructions": {
                    "step1": "Save the sandbox number (+14155238886) to your phone contacts",
                    "step2": "Open WhatsApp and message that number",
                    "step3": "Send the join code (check Twilio console for your specific code)",
                    "step4": "Wait for confirmation, then try again"
                }
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception occurred: {str(e)}"
        }


# User preferences endpoints
@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_my_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current user's notification preferences."""
    result = await db.execute(
        select(UserNotificationPreferences).where(
            UserNotificationPreferences.user_id == current_user.id
        )
    )
    prefs = result.scalar_one_or_none()
    
    if not prefs:
        return UserPreferencesResponse(
            opt_out_daily_reminders=False,
            opt_out_task_assignments=False,
            opt_out_all_whatsapp=False,
            opt_out_date=None
        )
    
    return UserPreferencesResponse(
        opt_out_daily_reminders=prefs.opt_out_daily_reminders,
        opt_out_task_assignments=prefs.opt_out_task_assignments,
        opt_out_all_whatsapp=prefs.opt_out_all_whatsapp,
        opt_out_date=prefs.opt_out_date
    )


@router.patch("/preferences", response_model=UserPreferencesResponse)
async def update_my_preferences(
    updates: UserPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update current user's notification preferences."""
    result = await db.execute(
        select(UserNotificationPreferences).where(
            UserNotificationPreferences.user_id == current_user.id
        )
    )
    prefs = result.scalar_one_or_none()
    
    if not prefs:
        prefs = UserNotificationPreferences(user_id=current_user.id)
        db.add(prefs)
    
    # Track if opting out
    was_opted_out = prefs.opt_out_all_whatsapp or prefs.opt_out_daily_reminders
    
    if updates.opt_out_daily_reminders is not None:
        prefs.opt_out_daily_reminders = updates.opt_out_daily_reminders
    if updates.opt_out_task_assignments is not None:
        prefs.opt_out_task_assignments = updates.opt_out_task_assignments
    if updates.opt_out_all_whatsapp is not None:
        prefs.opt_out_all_whatsapp = updates.opt_out_all_whatsapp
    
    # Update opt-out date
    is_opted_out = prefs.opt_out_all_whatsapp or prefs.opt_out_daily_reminders
    if is_opted_out and not was_opted_out:
        prefs.opt_out_date = datetime.utcnow()
    elif not is_opted_out:
        prefs.opt_out_date = None
    
    await db.commit()
    await db.refresh(prefs)
    
    return UserPreferencesResponse(
        opt_out_daily_reminders=prefs.opt_out_daily_reminders,
        opt_out_task_assignments=prefs.opt_out_task_assignments,
        opt_out_all_whatsapp=prefs.opt_out_all_whatsapp,
        opt_out_date=prefs.opt_out_date
    )


# Notification logs
@router.get("/logs", response_model=List[NotificationLogResponse])
async def get_notification_logs(
    limit: int = 50,
    notification_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get recent notification logs."""
    query = select(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(limit)
    
    if notification_type:
        query = query.where(NotificationLog.notification_type == notification_type)
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return [
        NotificationLogResponse(
            id=str(log.id),
            notification_type=log.notification_type,
            recipient_number=log.recipient_number,
            message_preview=log.message_preview,
            status=log.status,
            error_message=log.error_message,
            created_at=log.created_at,
            sent_at=log.sent_at
        )
        for log in logs
    ]


# Webhook for Twilio WhatsApp replies
@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    From: str,
    Body: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle incoming WhatsApp messages from Twilio webhook.
    This can process opt-out requests.
    """
    from app.tasks.notification_tasks import process_whatsapp_opt_out
    
    # Clean the phone number (remove 'whatsapp:' prefix if present)
    phone_number = From.replace("whatsapp:", "").strip()
    
    # Queue processing
    process_whatsapp_opt_out.delay(phone_number, Body)
    
    # Return 200 to acknowledge receipt
    return {"status": "received"}


