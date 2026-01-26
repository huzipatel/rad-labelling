"""GSV Account models for storing Google Cloud account info and API keys."""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class GSVAccount(Base):
    """Stores Google Cloud accounts used for GSV API."""
    __tablename__ = "gsv_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    billing_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    target_projects: Mapped[int] = mapped_column(Integer, default=30)
    
    # OAuth tokens
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    projects: Mapped[List["GSVProject"]] = relationship("GSVProject", back_populates="account", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "billing_id": self.billing_id,
            "target_projects": self.target_projects,
            "connected": self.connected,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "projects": [p.to_dict() for p in self.projects] if self.projects else [],
            # Don't expose tokens
        }


class GSVProject(Base):
    """Stores Google Cloud projects and their API keys."""
    __tablename__ = "gsv_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gsv_accounts.id", ondelete="CASCADE"), nullable=False)
    
    project_id: Mapped[str] = mapped_column(String(100), nullable=False)  # Google Cloud project ID
    project_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    auto_created: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationship
    account: Mapped["GSVAccount"] = relationship("GSVAccount", back_populates="projects")
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "project_id": self.project_id,
            "project_name": self.project_name,
            "api_key": self.api_key,
            "auto_created": self.auto_created,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

