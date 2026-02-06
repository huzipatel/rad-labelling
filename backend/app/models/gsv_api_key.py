"""GSV API Key model for simplified API key management."""
import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class GSVApiKey(Base):
    """Stores GSV API keys with usage tracking."""
    __tablename__ = "gsv_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Optional friendly name
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Usage tracking
    requests_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reset_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Error tracking
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    quota_exhausted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def to_dict(self, include_full_key: bool = False) -> dict:
        """Convert to dictionary for API responses.
        
        Args:
            include_full_key: If False (default), only show key prefix for security.
        """
        key_display = self.api_key if include_full_key else f"{self.api_key[:12]}...{self.api_key[-4:]}"
        
        return {
            "id": str(self.id),
            "api_key": key_display,
            "api_key_prefix": self.api_key[:12],
            "label": self.label,
            "is_active": self.is_active,
            "requests_today": self.requests_today,
            "requests_total": self.requests_total,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "consecutive_errors": self.consecutive_errors,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "last_error_message": self.last_error_message,
            "quota_exhausted": self.quota_exhausted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self._get_status(),
        }
    
    def _get_status(self) -> str:
        """Get human-readable status."""
        if not self.is_active:
            return "disabled"
        if self.quota_exhausted:
            return "quota_exhausted"
        if self.consecutive_errors >= 3:
            return "errors"
        return "active"
    
    def is_usable(self) -> bool:
        """Check if this key can be used for requests."""
        return self.is_active and not self.quota_exhausted
    
    def record_success(self) -> None:
        """Record a successful request."""
        self.requests_today += 1
        self.requests_total += 1
        self.last_used_at = datetime.utcnow()
        self.consecutive_errors = 0
    
    def record_error(self, error_message: str, is_quota_error: bool = False) -> None:
        """Record a failed request."""
        self.consecutive_errors += 1
        self.last_error_at = datetime.utcnow()
        self.last_error_message = error_message[:500] if error_message else None
        
        # Mark as quota exhausted after 5 consecutive quota errors
        if is_quota_error and self.consecutive_errors >= 5:
            self.quota_exhausted = True
    
    def reset_daily_stats(self) -> None:
        """Reset daily counters (call at midnight)."""
        today = date.today()
        if self.last_reset_date != today:
            self.requests_today = 0
            self.last_reset_date = today
            # Reset quota exhausted flag at start of new day
            self.quota_exhausted = False
            self.consecutive_errors = 0
