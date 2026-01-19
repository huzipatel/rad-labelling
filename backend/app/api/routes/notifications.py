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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Send a test daily summary notification (admin only)."""
    # Queue the task
    task = send_daily_performance_summary.delay()
    return {"message": "Daily summary notification queued", "task_id": str(task.id)}


@router.post("/test/labeller-reminders")
async def test_labeller_reminders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Send test daily reminders to all labellers (admin only)."""
    task = send_daily_labeller_reminders.delay()
    return {"message": "Labeller reminders queued", "task_id": str(task.id)}


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

