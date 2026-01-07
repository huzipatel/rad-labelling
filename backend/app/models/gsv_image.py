"""Google Street View Image model."""
import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, DateTime, Date, Integer, Boolean, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class GSVImage(Base):
    """GSV Image model for storing downloaded Street View images."""
    
    __tablename__ = "gsv_images"
    
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
    heading: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch: Mapped[float] = mapped_column(Float, default=0)
    zoom: Mapped[float] = mapped_column(Float, default=1)
    gcs_path: Mapped[str] = mapped_column(String(500), nullable=False)
    gcs_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    capture_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    pano_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_user_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    
    # Relationships
    location: Mapped["Location"] = relationship(
        "Location",
        back_populates="gsv_images"
    )
    
    @property
    def filename(self) -> str:
        """Generate filename for the image."""
        location = self.location
        date_str = self.capture_date.strftime("%Y%m") if self.capture_date else "unknown"
        if self.is_user_snapshot:
            return f"{location.identifier}_snapshot_{self.heading}_{date_str}.jpg"
        return f"{location.identifier}_{self.heading}_{date_str}.jpg"
    
    def __repr__(self) -> str:
        return f"<GSVImage {self.location_id} heading={self.heading}>"

