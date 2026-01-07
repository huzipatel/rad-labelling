"""Label model."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, Boolean, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class Label(Base):
    """Label model for storing labelling results."""
    
    __tablename__ = "labels"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False
    )
    labeller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Standard bus stop label fields
    advertising_present: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    bus_shelter_present: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    number_of_panels: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pole_stop: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    unmarked_stop: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Image selection (1-4 for GSV images, 5+ for snapshots)
    selected_image: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Custom fields for other location types
    custom_fields: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending"
    )
    unable_to_label: Mapped[bool] = mapped_column(Boolean, default=False)
    unable_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    labelling_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    labelling_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Relationships
    location: Mapped["Location"] = relationship(
        "Location",
        back_populates="labels"
    )
    task: Mapped["Task"] = relationship(
        "Task",
        back_populates="labels"
    )
    labeller: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="labels"
    )
    
    @property
    def labelling_duration_seconds(self) -> Optional[float]:
        """Calculate time spent labelling this location."""
        if self.labelling_started_at and self.labelling_completed_at:
            delta = self.labelling_completed_at - self.labelling_started_at
            return delta.total_seconds()
        return None
    
    def __repr__(self) -> str:
        return f"<Label {self.id}>"

