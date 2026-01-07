"""Shapefile models for spatial data management."""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, DateTime, ForeignKey, func, Integer, BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class Shapefile(Base):
    """Shapefile metadata and feature tracking."""
    
    __tablename__ = "shapefiles"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    shapefile_type: Mapped[str] = mapped_column(
        String(50), 
        nullable=False
    )  # council_boundaries, combined_authorities, road_classifications
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    geometry_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    attribute_columns: Mapped[dict] = mapped_column(JSONB, default=dict)
    name_column: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Legacy single column
    # Multiple attribute mappings: [{"source_column": "LAD21NM", "target_column": "council"}, ...]
    attribute_mappings: Mapped[List[dict]] = mapped_column(JSONB, default=list)
    is_loaded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    loaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    def __repr__(self) -> str:
        return f"<Shapefile {self.name}>"


class UploadJob(Base):
    """Track large file upload progress."""
    
    __tablename__ = "upload_jobs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending"
    )  # pending, uploading, analyzing, processing, completed, failed
    stage: Mapped[str] = mapped_column(
        String(100),
        default="Initializing"
    )  # Human readable stage description
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    uploaded_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    shapefile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )  # Set when shapefile record is created
    job_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)  # Store form data
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    def __repr__(self) -> str:
        return f"<UploadJob {self.id} - {self.status}>"


class EnhancementJob(Base):
    """Track enhancement job progress."""
    
    __tablename__ = "enhancement_jobs"
    
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
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending"
    )  # pending, running, completed, failed
    total_locations: Mapped[int] = mapped_column(Integer, default=0)
    processed_locations: Mapped[int] = mapped_column(Integer, default=0)
    enhanced_locations: Mapped[int] = mapped_column(Integer, default=0)
    enhance_council: Mapped[bool] = mapped_column(default=True)
    enhance_road: Mapped[bool] = mapped_column(default=True)
    enhance_authority: Mapped[bool] = mapped_column(default=True)
    councils_found: Mapped[List[str]] = mapped_column(JSONB, default=list)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    def __repr__(self) -> str:
        return f"<EnhancementJob {self.id} - {self.status}>"

