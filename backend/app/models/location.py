"""Location and LocationType models."""
import uuid
from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import String, DateTime, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geography

from app.core.database import Base


class LocationType(Base):
    """Location type model (bus_stops, phone_boxes, etc.)."""
    
    __tablename__ = "location_types"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    label_fields: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict
    )
    identifier_field: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="atco_code"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    locations: Mapped[List["Location"]] = relationship(
        "Location",
        back_populates="location_type"
    )
    tasks: Mapped[List["Task"]] = relationship(
        "Task",
        back_populates="location_type"
    )
    
    def __repr__(self) -> str:
        return f"<LocationType {self.name}>"


class Location(Base):
    """Location model for advertising locations."""
    
    __tablename__ = "locations"
    
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
    identifier: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    coordinates: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326),
        nullable=True
    )
    council: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    combined_authority: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    road_classification: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    original_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict
    )
    is_enhanced: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    location_type: Mapped["LocationType"] = relationship(
        "LocationType",
        back_populates="locations"
    )
    labels: Mapped[List["Label"]] = relationship(
        "Label",
        back_populates="location"
    )
    gsv_images: Mapped[List["GSVImage"]] = relationship(
        "GSVImage",
        back_populates="location"
    )
    
    __table_args__ = (
        Index("ix_locations_type_council", "location_type_id", "council"),
    )
    
    def __repr__(self) -> str:
        return f"<Location {self.identifier}>"

