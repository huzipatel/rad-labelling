"""WhatsApp notification service using Twilio."""
from typing import Optional
from twilio.rest import Client

from app.core.config import settings


class WhatsAppNotifier:
    """Send WhatsApp notifications via Twilio."""
    
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_number = settings.TWILIO_WHATSAPP_NUMBER
        self._client = None
    
    @property
    def client(self) -> Optional[Client]:
        """Get or create Twilio client."""
        if not self.account_sid or not self.auth_token:
            return None
        
        if self._client is None:
            self._client = Client(self.account_sid, self.auth_token)
        
        return self._client
    
    async def send_message(
        self,
        to_number: str,
        message: str
    ) -> Optional[str]:
        """
        Send a WhatsApp message.
        
        Args:
            to_number: Recipient phone number (with country code)
            message: Message body
        
        Returns:
            Message SID if successful, None otherwise
        """
        if not self.client:
            print("Twilio not configured, skipping WhatsApp notification")
            return None
        
        # Ensure numbers are in WhatsApp format
        from_whatsapp = f"whatsapp:{self.from_number}"
        to_whatsapp = f"whatsapp:{to_number}"
        
        try:
            msg = self.client.messages.create(
                body=message,
                from_=from_whatsapp,
                to=to_whatsapp
            )
            return msg.sid
        except Exception as e:
            print(f"Failed to send WhatsApp message: {e}")
            return None
    
    async def notify_task_completion(
        self,
        manager_number: str,
        task_info: dict
    ) -> Optional[str]:
        """
        Send task completion notification to a manager.
        
        Args:
            manager_number: Manager's WhatsApp number
            task_info: Dictionary with task details
        
        Returns:
            Message SID if successful
        """
        message = f"""✅ Labelling Task Completed

Type: {task_info.get('location_type', 'Unknown')}
Council: {task_info.get('council', 'Unknown')}
Labeller: {task_info.get('labeller_name', 'Unknown')}

📊 Results:
• Completed: {task_info.get('completed', 0)}/{task_info.get('total', 0)}
• With Advertising: {task_info.get('with_advertising', 0)}
• Unable to Label: {task_info.get('unable', 0)}

⏱️ Time Taken: {task_info.get('duration', 'Unknown')}
📈 Rate: {task_info.get('rate', 'Unknown')} locations/hour"""
        
        return await self.send_message(manager_number, message)
    
    async def notify_download_complete(
        self,
        manager_number: str,
        task_info: dict
    ) -> Optional[str]:
        """
        Send image download completion notification.
        
        Args:
            manager_number: Manager's WhatsApp number
            task_info: Dictionary with download details
        """
        message = f"""📥 Image Download Complete

Task: {task_info.get('location_type', 'Unknown')} - {task_info.get('council', 'Unknown')}

📊 Summary:
• Images Downloaded: {task_info.get('images_downloaded', 0)}
• Failed: {task_info.get('failed', 0)}

The task is now ready for labelling."""
        
        return await self.send_message(manager_number, message)
    
    async def notify_managers_bulk(
        self,
        manager_numbers: list,
        message: str
    ) -> int:
        """
        Send message to multiple managers.
        
        Returns count of successful sends.
        """
        success_count = 0
        
        for number in manager_numbers:
            result = await self.send_message(number, message)
            if result:
                success_count += 1
        
        return success_count

