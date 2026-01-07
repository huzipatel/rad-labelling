"""Download log model for tracking GSV image downloads."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class DownloadStatus(str, enum.Enum):
    """Download status enum."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadLog(Base):
    """Log entry for image download operations."""
    __tablename__ = "download_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True)
    
    # Status tracking
    status = Column(String(50), default=DownloadStatus.PENDING.value)
    
    # Progress
    total_locations = Column(Integer, default=0)
    processed_locations = Column(Integer, default=0)
    successful_downloads = Column(Integer, default=0)
    failed_downloads = Column(Integer, default=0)
    skipped_existing = Column(Integer, default=0)
    
    # Current operation
    current_location_id = Column(UUID(as_uuid=True), nullable=True)
    current_location_identifier = Column(String(255), nullable=True)
    
    # Error tracking
    last_error = Column(Text, nullable=True)
    error_count = Column(Integer, default=0)
    
    # Log messages (JSON array of log entries)
    log_messages = Column(Text, default="[]")
    
    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    task = relationship("Task", backref="download_logs")

