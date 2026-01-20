"""WhatsApp notification service using Twilio."""
import os
from typing import Optional
from twilio.rest import Client
from app.core.config import settings


class WhatsAppService:
    """Service for sending WhatsApp messages via Twilio."""
    
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_number = settings.TWILIO_WHATSAPP_FROM
        self.client: Optional[Client] = None
        self.enabled = bool(self.account_sid and self.auth_token and self.from_number)
        
        if self.enabled:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                print(f"[WhatsApp] Service initialized with from number: {self.from_number}")
            except Exception as e:
                print(f"[WhatsApp] Failed to initialize Twilio client: {e}")
                self.enabled = False
        else:
            print("[WhatsApp] Service disabled - missing Twilio credentials")
    
    def send_message(self, to_number: str, message: str) -> bool:
        """
        Send a WhatsApp message.
        
        Args:
            to_number: Recipient's phone number in E.164 format (e.g., +447123456789)
            message: Message content
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if not self.enabled or not self.client:
            print(f"[WhatsApp] Cannot send - service not enabled")
            return False
        
        # Format numbers for WhatsApp
        from_whatsapp = f"whatsapp:{self.from_number}"
        to_whatsapp = f"whatsapp:{to_number}"
        
        try:
            message_obj = self.client.messages.create(
                body=message,
                from_=from_whatsapp,
                to=to_whatsapp
            )
            print(f"[WhatsApp] Message sent to {to_number}: SID {message_obj.sid}")
            return True
        except Exception as e:
            print(f"[WhatsApp] Failed to send message to {to_number}: {e}")
            return False
    
    def send_daily_performance_summary(
        self,
        to_number: str,
        total_labels_today: int,
        total_images_today: int,
        labeller_stats: list[dict],
        tasks_completed: list[str]
    ) -> bool:
        """
        Send daily performance summary to admin.
        
        Args:
            to_number: Admin's WhatsApp number
            total_labels_today: Total labels created today
            total_images_today: Total images labelled today
            labeller_stats: List of dicts with labeller name and labels count
            tasks_completed: List of task names completed today
        """
        lines = [
            "📊 *Daily Performance Summary*",
            f"📅 {self._get_today_date()}",
            "",
            f"🏷️ Total Labels: *{total_labels_today:,}*",
            f"🖼️ Images Processed: *{total_images_today:,}*",
        ]
        
        if tasks_completed:
            lines.extend([
                "",
                f"✅ *Tasks Completed ({len(tasks_completed)}):*"
            ])
            for task in tasks_completed[:5]:
                lines.append(f"  • {task}")
            if len(tasks_completed) > 5:
                lines.append(f"  • ... and {len(tasks_completed) - 5} more")
        
        if labeller_stats:
            lines.extend([
                "",
                "👥 *Labeller Performance:*"
            ])
            # Sort by labels descending
            sorted_stats = sorted(labeller_stats, key=lambda x: x.get('labels', 0), reverse=True)
            for stat in sorted_stats[:10]:
                name = stat.get('name', 'Unknown')
                labels = stat.get('labels', 0)
                lines.append(f"  • {name}: *{labels:,}* labels")
            if len(sorted_stats) > 10:
                lines.append(f"  • ... and {len(sorted_stats) - 10} more labellers")
        
        message = "\n".join(lines)
        return self.send_message(to_number, message)
    
    def send_task_completion_notification(
        self,
        to_number: str,
        task_name: str,
        labeller_name: str,
        total_images: int,
        completion_time: str
    ) -> bool:
        """
        Notify admin when a labeller completes a task.
        
        Args:
            to_number: Admin's WhatsApp number
            task_name: Name of the completed task
            labeller_name: Name of the labeller who completed it
            total_images: Total images in the task
            completion_time: When the task was completed
        """
        message = f"""🎉 *Task Completed!*

📋 Task: *{task_name}*
👤 Completed by: *{labeller_name}*
🖼️ Total Images: *{total_images:,}*
⏰ Time: {completion_time}

Great work! 🌟"""
        
        return self.send_message(to_number, message)
    
    def send_daily_reminder(
        self,
        to_number: str,
        labeller_name: str,
        pending_tasks: list[dict]
    ) -> bool:
        """
        Send daily reminder to labeller about pending tasks.
        
        Args:
            to_number: Labeller's WhatsApp number
            labeller_name: Labeller's name
            pending_tasks: List of dicts with task info (name, images_remaining, deadline)
        """
        if not pending_tasks:
            return True  # Nothing to remind about
        
        lines = [
            f"👋 Hi {labeller_name}!",
            "",
            "📋 *Your tasks for today:*",
        ]
        
        for task in pending_tasks[:5]:
            name = task.get('name', 'Unknown Task')
            remaining = task.get('images_remaining', 0)
            deadline = task.get('deadline')
            
            task_line = f"  • *{name}*: {remaining:,} images left"
            if deadline:
                task_line += f" (due: {deadline})"
            lines.append(task_line)
        
        if len(pending_tasks) > 5:
            lines.append(f"  • ... and {len(pending_tasks) - 5} more tasks")
        
        lines.extend([
            "",
            "💪 Have a productive day!",
            "",
            "_Reply STOP to opt out of daily reminders_"
        ])
        
        message = "\n".join(lines)
        return self.send_message(to_number, message)
    
    def _get_today_date(self) -> str:
        """Get today's date formatted nicely."""
        from datetime import datetime
        return datetime.now().strftime("%A, %d %B %Y")


# Global service instance
whatsapp_service = WhatsAppService()


