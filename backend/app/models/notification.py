"""Notification-related database models."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class NotificationSettings(Base):
    """Global notification settings for the application."""
    
    __tablename__ = "notification_settings"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Daily performance summary settings
    daily_summary_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_summary_time: Mapped[str] = mapped_column(String(5), default="18:00")  # HH:MM format
    daily_summary_admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    
    # Task completion notifications
    task_completion_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Daily reminders for labellers
    daily_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_reminder_time: Mapped[str] = mapped_column(String(5), default="09:00")  # HH:MM format
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class UserNotificationPreferences(Base):
    """Per-user notification preferences (opt-out settings)."""
    
    __tablename__ = "user_notification_preferences"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True
    )
    
    # Opt-out flags
    opt_out_daily_reminders: Mapped[bool] = mapped_column(Boolean, default=False)
    opt_out_task_assignments: Mapped[bool] = mapped_column(Boolean, default=False)
    opt_out_all_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # When user opted out
    opt_out_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationship
    user = relationship("User", backref="notification_preferences")


class NotificationLog(Base):
    """Log of sent notifications for audit and debugging."""
    
    __tablename__ = "notification_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Notification details
    notification_type: Mapped[str] = mapped_column(String(50))  # daily_summary, task_completion, daily_reminder
    recipient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    recipient_number: Mapped[str] = mapped_column(String(20))
    
    # Content (truncated for storage)
    message_preview: Mapped[str] = mapped_column(Text)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, sent, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


