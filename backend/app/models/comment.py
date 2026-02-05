"""Comment model for manager feedback and labeller questions."""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, DateTime, Boolean, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class LabelComment(Base):
    """Comment on a label for manager feedback or labeller questions."""
    
    __tablename__ = "label_comments"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    label_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("labels.id", ondelete="CASCADE"),
        nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Comment content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Comment type: 'feedback' (manager suggestion), 'question' (labeller asking), 'reply'
    comment_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="feedback"
    )
    
    # Tagged user (for @mentions)
    tagged_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Parent comment for threading
    parent_comment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("label_comments.id", ondelete="CASCADE"),
        nullable=True
    )
    
    # Read status
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Resolved status (for manager feedback that's been addressed)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    resolved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
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
    
    # Relationships
    label: Mapped["Label"] = relationship(
        "Label",
        back_populates="comments"
    )
    author: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[author_id],
        back_populates="comments_authored"
    )
    tagged_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[tagged_user_id]
    )
    resolved_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[resolved_by_id]
    )
    parent_comment: Mapped[Optional["LabelComment"]] = relationship(
        "LabelComment",
        remote_side=[id],
        back_populates="replies"
    )
    replies: Mapped[List["LabelComment"]] = relationship(
        "LabelComment",
        back_populates="parent_comment",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<LabelComment {self.id}>"
