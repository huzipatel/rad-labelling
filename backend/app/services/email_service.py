"""Email service for sending notifications and invitations."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import os

from app.core.config import settings


class EmailService:
    """Service for sending emails using SMTP."""
    
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_user)
        self.from_name = os.getenv("FROM_NAME", "AdVue UK")
    
    def _is_configured(self) -> bool:
        """Check if SMTP is configured."""
        return bool(self.smtp_user and self.smtp_password)
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Send an email.
        
        Returns True if sent successfully, False otherwise.
        """
        if not self._is_configured():
            print(f"[Email] SMTP not configured. Would have sent to {to_email}: {subject}")
            return False
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email
            
            # Add plain text and HTML versions
            if text_content:
                msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            print(f"[Email] Sent email to {to_email}: {subject}")
            return True
            
        except Exception as e:
            print(f"[Email] Failed to send email to {to_email}: {e}")
            return False
    
    def send_invitation(
        self,
        to_email: str,
        inviter_name: str,
        role: str,
        invitation_url: str,
        message: Optional[str] = None
    ) -> bool:
        """Send an invitation email to a new user."""
        
        role_display = {
            "labeller": "Labeller",
            "labelling_manager": "Manager",
            "admin": "Administrator"
        }.get(role, role)
        
        subject = f"You've been invited to join AdVue UK"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #0b0c0c; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f8f8; }}
                .button {{ 
                    display: inline-block; 
                    background: #00703c; 
                    color: white; 
                    padding: 12px 24px; 
                    text-decoration: none; 
                    border-radius: 4px;
                    margin: 20px 0;
                }}
                .footer {{ padding: 20px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">AdVue UK</h1>
                </div>
                <div class="content">
                    <h2>You're Invited!</h2>
                    <p><strong>{inviter_name}</strong> has invited you to join AdVue UK as a <strong>{role_display}</strong>.</p>
                    
                    {f'<p style="background: #fff; padding: 15px; border-left: 4px solid #00703c; margin: 20px 0;"><em>"{message}"</em></p>' if message else ''}
                    
                    <p>Click the button below to create your account:</p>
                    
                    <a href="{invitation_url}" class="button">Accept Invitation</a>
                    
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; font-size: 14px; color: #666;">{invitation_url}</p>
                    
                    <p><strong>This invitation will expire in 7 days.</strong></p>
                </div>
                <div class="footer">
                    <p>AdVue UK - Advertising Location Intelligence</p>
                    <p>If you didn't expect this invitation, you can safely ignore this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        You're Invited to AdVue UK!
        
        {inviter_name} has invited you to join AdVue UK as a {role_display}.
        
        {f'Message: "{message}"' if message else ''}
        
        Click here to accept: {invitation_url}
        
        This invitation will expire in 7 days.
        
        ---
        AdVue UK - Advertising Location Intelligence
        """
        
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_task_assigned(
        self,
        to_email: str,
        labeller_name: str,
        task_name: str,
        task_url: str,
        location_count: int
    ) -> bool:
        """Send notification when a task is assigned."""
        
        subject = f"New task assigned: {task_name}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #0b0c0c; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f8f8; }}
                .button {{ 
                    display: inline-block; 
                    background: #1d70b8; 
                    color: white; 
                    padding: 12px 24px; 
                    text-decoration: none; 
                    border-radius: 4px;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">AdVue UK</h1>
                </div>
                <div class="content">
                    <h2>New Task Assigned</h2>
                    <p>Hi {labeller_name},</p>
                    <p>You've been assigned a new labelling task:</p>
                    <ul>
                        <li><strong>Task:</strong> {task_name}</li>
                        <li><strong>Locations:</strong> {location_count:,}</li>
                    </ul>
                    <a href="{task_url}" class="button">Start Task</a>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(to_email, subject, html_content)


# Singleton instance
email_service = EmailService()

