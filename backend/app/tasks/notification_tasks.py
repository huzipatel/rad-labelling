"""Celery tasks for WhatsApp notifications."""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
from celery import shared_task
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.celery_tasks import celery_app
from app.core.database import get_celery_session_maker
from app.services.whatsapp_service import whatsapp_service
from app.models.user import User
from app.models.task import Task
from app.models.label import Label
from app.models.notification import NotificationSettings, UserNotificationPreferences, NotificationLog


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="send_daily_performance_summary")
def send_daily_performance_summary():
    """
    Send daily performance summary to admin.
    Should be scheduled to run at the configured time (e.g., 6 PM).
    """
    async def _send():
        session_maker = get_celery_session_maker()
        async with session_maker() as db:
            # Get notification settings
            result = await db.execute(select(NotificationSettings).limit(1))
            settings = result.scalar_one_or_none()
            
            if not settings or not settings.daily_summary_enabled:
                print("[Notification] Daily summary is disabled")
                return {"status": "disabled"}
            
            if not settings.daily_summary_admin_id:
                print("[Notification] No admin configured for daily summary")
                return {"status": "no_admin"}
            
            # Get admin user
            admin_result = await db.execute(
                select(User).where(User.id == settings.daily_summary_admin_id)
            )
            admin = admin_result.scalar_one_or_none()
            
            if not admin or not admin.whatsapp_number:
                print("[Notification] Admin has no WhatsApp number")
                return {"status": "no_whatsapp"}
            
            # Calculate today's stats
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get total labels today
            labels_result = await db.execute(
                select(func.count(Label.id)).where(
                    Label.created_at >= today_start
                )
            )
            total_labels = labels_result.scalar() or 0
            
            # Get unique images labelled today
            images_result = await db.execute(
                select(func.count(func.distinct(Label.gsv_image_id))).where(
                    Label.created_at >= today_start
                )
            )
            total_images = images_result.scalar() or 0
            
            # Get labeller stats
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
            
            # Get tasks completed today
            tasks_result = await db.execute(
                select(Task.name).where(
                    and_(
                        Task.status == "completed",
                        Task.updated_at >= today_start
                    )
                )
            )
            tasks_completed = [row[0] for row in tasks_result.all()]
            
            # Send notification
            success = whatsapp_service.send_daily_performance_summary(
                to_number=admin.whatsapp_number,
                total_labels_today=total_labels,
                total_images_today=total_images,
                labeller_stats=labeller_stats,
                tasks_completed=tasks_completed
            )
            
            # Log notification
            log = NotificationLog(
                notification_type="daily_summary",
                recipient_id=admin.id,
                recipient_number=admin.whatsapp_number,
                message_preview=f"Daily summary: {total_labels} labels, {total_images} images",
                status="sent" if success else "failed"
            )
            db.add(log)
            await db.commit()
            
            return {
                "status": "sent" if success else "failed",
                "total_labels": total_labels,
                "total_images": total_images
            }
    
    return run_async(_send())


@celery_app.task(name="send_task_completion_notification")
def send_task_completion_notification(task_id: str, labeller_id: str):
    """
    Send notification when a labeller completes a task.
    Called when a task is marked as complete.
    """
    async def _send():
        session_maker = get_celery_session_maker()
        async with session_maker() as db:
            # Get notification settings
            result = await db.execute(select(NotificationSettings).limit(1))
            settings = result.scalar_one_or_none()
            
            if not settings or not settings.task_completion_enabled:
                return {"status": "disabled"}
            
            # Get task details
            task_result = await db.execute(
                select(Task).where(Task.id == task_id)
            )
            task = task_result.scalar_one_or_none()
            
            if not task:
                return {"status": "task_not_found"}
            
            # Get labeller details
            labeller_result = await db.execute(
                select(User).where(User.id == labeller_id)
            )
            labeller = labeller_result.scalar_one_or_none()
            
            if not labeller:
                return {"status": "labeller_not_found"}
            
            # Get admin(s) with WhatsApp numbers
            admins_result = await db.execute(
                select(User).where(
                    and_(
                        User.role.in_(["admin", "labelling_manager"]),
                        User.whatsapp_number.isnot(None),
                        User.is_active == True
                    )
                )
            )
            admins = admins_result.scalars().all()
            
            if not admins:
                return {"status": "no_admins_with_whatsapp"}
            
            sent_count = 0
            for admin in admins:
                # Check if admin has opted out
                prefs_result = await db.execute(
                    select(UserNotificationPreferences).where(
                        UserNotificationPreferences.user_id == admin.id
                    )
                )
                prefs = prefs_result.scalar_one_or_none()
                
                if prefs and prefs.opt_out_all_whatsapp:
                    continue
                
                success = whatsapp_service.send_task_completion_notification(
                    to_number=admin.whatsapp_number,
                    task_name=task.name,
                    labeller_name=labeller.name,
                    total_images=task.total_images or 0,
                    completion_time=datetime.utcnow().strftime("%H:%M")
                )
                
                if success:
                    sent_count += 1
                
                # Log notification
                log = NotificationLog(
                    notification_type="task_completion",
                    recipient_id=admin.id,
                    recipient_number=admin.whatsapp_number,
                    message_preview=f"Task '{task.name}' completed by {labeller.name}",
                    status="sent" if success else "failed",
                    task_id=task.id
                )
                db.add(log)
            
            await db.commit()
            return {"status": "sent", "sent_count": sent_count}
    
    return run_async(_send())


@celery_app.task(name="send_daily_labeller_reminders")
def send_daily_labeller_reminders():
    """
    Send daily reminders to labellers about their pending tasks.
    Should be scheduled to run at the configured time (e.g., 9 AM).
    """
    async def _send():
        session_maker = get_celery_session_maker()
        async with session_maker() as db:
            # Get notification settings
            result = await db.execute(select(NotificationSettings).limit(1))
            settings = result.scalar_one_or_none()
            
            if not settings or not settings.daily_reminders_enabled:
                return {"status": "disabled"}
            
            # Get all active labellers with WhatsApp numbers
            labellers_result = await db.execute(
                select(User).where(
                    and_(
                        User.role == "labeller",
                        User.whatsapp_number.isnot(None),
                        User.is_active == True
                    )
                )
            )
            labellers = labellers_result.scalars().all()
            
            sent_count = 0
            skipped_count = 0
            
            for labeller in labellers:
                # Check if labeller has opted out
                prefs_result = await db.execute(
                    select(UserNotificationPreferences).where(
                        UserNotificationPreferences.user_id == labeller.id
                    )
                )
                prefs = prefs_result.scalar_one_or_none()
                
                if prefs and (prefs.opt_out_daily_reminders or prefs.opt_out_all_whatsapp):
                    skipped_count += 1
                    continue
                
                # Get pending tasks for this labeller
                tasks_result = await db.execute(
                    select(Task).where(
                        and_(
                            Task.assigned_to_id == labeller.id,
                            Task.status.in_(["assigned", "in_progress"])
                        )
                    )
                )
                tasks = tasks_result.scalars().all()
                
                if not tasks:
                    continue  # No pending tasks
                
                pending_tasks = []
                for task in tasks:
                    # Calculate remaining images
                    labelled_result = await db.execute(
                        select(func.count(func.distinct(Label.gsv_image_id))).where(
                            and_(
                                Label.task_id == task.id,
                                Label.labeller_id == labeller.id
                            )
                        )
                    )
                    labelled_count = labelled_result.scalar() or 0
                    remaining = (task.total_images or 0) - labelled_count
                    
                    if remaining > 0:
                        pending_tasks.append({
                            "name": task.name,
                            "images_remaining": remaining,
                            "deadline": task.deadline.strftime("%d %b") if task.deadline else None
                        })
                
                if not pending_tasks:
                    continue
                
                success = whatsapp_service.send_daily_reminder(
                    to_number=labeller.whatsapp_number,
                    labeller_name=labeller.name,
                    pending_tasks=pending_tasks
                )
                
                if success:
                    sent_count += 1
                
                # Log notification
                log = NotificationLog(
                    notification_type="daily_reminder",
                    recipient_id=labeller.id,
                    recipient_number=labeller.whatsapp_number,
                    message_preview=f"Daily reminder: {len(pending_tasks)} pending tasks",
                    status="sent" if success else "failed"
                )
                db.add(log)
            
            await db.commit()
            return {
                "status": "completed",
                "sent_count": sent_count,
                "skipped_count": skipped_count
            }
    
    return run_async(_send())


@celery_app.task(name="process_whatsapp_opt_out")
def process_whatsapp_opt_out(phone_number: str, message: str):
    """
    Process opt-out requests from WhatsApp messages.
    This can be called by a Twilio webhook.
    """
    async def _process():
        message_lower = message.lower().strip()
        
        # Check if this is an opt-out message
        opt_out_keywords = ["stop", "unsubscribe", "opt out", "opt-out"]
        is_opt_out = any(keyword in message_lower for keyword in opt_out_keywords)
        
        if not is_opt_out:
            return {"status": "not_opt_out"}
        
        session_maker = get_celery_session_maker()
        async with session_maker() as db:
            # Find user by WhatsApp number
            user_result = await db.execute(
                select(User).where(User.whatsapp_number == phone_number)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                return {"status": "user_not_found"}
            
            # Update or create preferences
            prefs_result = await db.execute(
                select(UserNotificationPreferences).where(
                    UserNotificationPreferences.user_id == user.id
                )
            )
            prefs = prefs_result.scalar_one_or_none()
            
            if prefs:
                prefs.opt_out_daily_reminders = True
                prefs.opt_out_date = datetime.utcnow()
            else:
                prefs = UserNotificationPreferences(
                    user_id=user.id,
                    opt_out_daily_reminders=True,
                    opt_out_date=datetime.utcnow()
                )
                db.add(prefs)
            
            await db.commit()
            
            # Send confirmation
            whatsapp_service.send_message(
                phone_number,
                "✅ You've been unsubscribed from daily reminders. "
                "You can re-enable notifications from the web app settings."
            )
            
            return {"status": "opted_out", "user_id": str(user.id)}
    
    return run_async(_process())

