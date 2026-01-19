"""Task model."""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, DateTime, Integer, ForeignKey, func, Index, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class Task(Base):
    """Task model for labelling assignments."""
    
    __tablename__ = "tasks"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    location_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("location_types.id", ondelete="CASCADE"),
        nullable=False
    )
    # Legacy field - kept for backwards compatibility
    council: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    # New flexible grouping fields
    group_field: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        default="council"
    )
    group_value: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        index=True
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True
    )
    total_locations: Mapped[int] = mapped_column(Integer, default=0)
    completed_locations: Mapped[int] = mapped_column(Integer, default=0)
    failed_locations: Mapped[int] = mapped_column(Integer, default=0)
    images_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    total_images: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Sample task fields
    is_sample: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    source_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True
    )
    sample_location_ids: Mapped[Optional[List]] = mapped_column(
        JSONB,
        nullable=True,
        default=None
    )
    
    # Relationships
    location_type: Mapped["LocationType"] = relationship(
        "LocationType",
        back_populates="tasks"
    )
    assignee: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="assigned_tasks",
        foreign_keys=[assigned_to]
    )
    labels: Mapped[List["Label"]] = relationship(
        "Label",
        back_populates="task"
    )
    
    __table_args__ = (
        Index("ix_tasks_type_council", "location_type_id", "council"),
        Index("ix_tasks_assignee_status", "assigned_to", "status"),
        Index("ix_tasks_group", "location_type_id", "group_field", "group_value"),
    )
    
    @property
    def completion_percentage(self) -> float:
        """Calculate task completion percentage."""
        if self.total_locations == 0:
            return 0.0
        return (self.completed_locations / self.total_locations) * 100
    
    @property
    def download_progress(self) -> float:
        """Calculate image download progress."""
        if self.total_images == 0:
            return 0.0
        return (self.images_downloaded / self.total_images) * 100
    
    def __repr__(self) -> str:
        return f"<Task {self.id} - {self.council}>"

