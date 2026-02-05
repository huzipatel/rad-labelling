"""Comment routes for manager feedback and labeller questions."""
import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.core.database import get_db
from app.models.user import User
from app.models.label import Label
from app.models.comment import LabelComment
from app.models.task import Task
from app.api.deps import get_current_user, require_manager


router = APIRouter(prefix="/comments", tags=["Comments"])


class CommentCreate(BaseModel):
    """Create comment request."""
    content: str
    comment_type: str = "feedback"  # feedback, question, reply
    tagged_user_id: Optional[str] = None
    parent_comment_id: Optional[str] = None


class CommentResponse(BaseModel):
    """Comment response."""
    id: str
    label_id: str
    author_id: Optional[str]
    author_name: Optional[str]
    content: str
    comment_type: str
    tagged_user_id: Optional[str]
    tagged_user_name: Optional[str]
    parent_comment_id: Optional[str]
    is_read: bool
    is_resolved: bool
    created_at: str
    replies: List["CommentResponse"] = []

    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    """List of comments response."""
    comments: List[CommentResponse]
    total: int
    unread_count: int


@router.post("/label/{label_id}")
async def create_comment(
    label_id: uuid.UUID,
    comment_data: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a comment on a label."""
    # Get the label
    result = await db.execute(
        select(Label).where(Label.id == label_id)
    )
    label = result.scalar_one_or_none()
    
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")
    
    # Verify access - labellers can only comment on their own labels, managers can comment on any
    if current_user.role == "labeller":
        if label.labeller_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        # Labellers can only create questions, not feedback
        if comment_data.comment_type == "feedback":
            raise HTTPException(status_code=403, detail="Labellers cannot create feedback comments")
    
    # Create the comment
    comment = LabelComment(
        id=uuid.uuid4(),
        label_id=label_id,
        author_id=current_user.id,
        content=comment_data.content,
        comment_type=comment_data.comment_type,
        tagged_user_id=uuid.UUID(comment_data.tagged_user_id) if comment_data.tagged_user_id else None,
        parent_comment_id=uuid.UUID(comment_data.parent_comment_id) if comment_data.parent_comment_id else None
    )
    
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    
    return {
        "id": str(comment.id),
        "message": "Comment created successfully"
    }


@router.get("/label/{label_id}", response_model=CommentListResponse)
async def get_label_comments(
    label_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all comments for a label."""
    # Get the label
    result = await db.execute(
        select(Label).where(Label.id == label_id)
    )
    label = result.scalar_one_or_none()
    
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")
    
    # Verify access
    if current_user.role == "labeller" and label.labeller_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get comments with author info (only top-level comments, not replies)
    comments_result = await db.execute(
        select(LabelComment)
        .options(selectinload(LabelComment.author), selectinload(LabelComment.tagged_user), selectinload(LabelComment.replies))
        .where(
            LabelComment.label_id == label_id,
            LabelComment.parent_comment_id.is_(None)
        )
        .order_by(LabelComment.created_at.desc())
    )
    comments = comments_result.scalars().all()
    
    # Count unread for this user
    unread_result = await db.execute(
        select(func.count(LabelComment.id))
        .where(
            LabelComment.label_id == label_id,
            LabelComment.is_read == False,
            LabelComment.author_id != current_user.id
        )
    )
    unread_count = unread_result.scalar() or 0
    
    def format_comment(c: LabelComment) -> dict:
        return {
            "id": str(c.id),
            "label_id": str(c.label_id),
            "author_id": str(c.author_id) if c.author_id else None,
            "author_name": c.author.name if c.author else "Unknown",
            "content": c.content,
            "comment_type": c.comment_type,
            "tagged_user_id": str(c.tagged_user_id) if c.tagged_user_id else None,
            "tagged_user_name": c.tagged_user.name if c.tagged_user else None,
            "parent_comment_id": str(c.parent_comment_id) if c.parent_comment_id else None,
            "is_read": c.is_read,
            "is_resolved": c.is_resolved,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "replies": [format_comment(r) for r in c.replies] if c.replies else []
        }
    
    return {
        "comments": [format_comment(c) for c in comments],
        "total": len(comments),
        "unread_count": unread_count
    }


@router.get("/my-unread")
async def get_my_unread_comments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get unread comments for the current user (tagged or on their labels)."""
    # For labellers: get comments on their labels
    # For managers: get comments where they are tagged
    
    if current_user.role == "labeller":
        # Get labels belonging to this user
        labels_result = await db.execute(
            select(Label.id).where(Label.labeller_id == current_user.id)
        )
        label_ids = [r[0] for r in labels_result.all()]
        
        if not label_ids:
            return {"comments": [], "total": 0}
        
        comments_result = await db.execute(
            select(LabelComment)
            .options(selectinload(LabelComment.author), selectinload(LabelComment.label))
            .where(
                LabelComment.label_id.in_(label_ids),
                LabelComment.is_read == False,
                LabelComment.author_id != current_user.id
            )
            .order_by(LabelComment.created_at.desc())
            .limit(50)
        )
    else:
        # Manager: get comments where they are tagged or questions from labellers
        comments_result = await db.execute(
            select(LabelComment)
            .options(selectinload(LabelComment.author), selectinload(LabelComment.label))
            .where(
                or_(
                    LabelComment.tagged_user_id == current_user.id,
                    LabelComment.comment_type == "question"
                ),
                LabelComment.is_read == False
            )
            .order_by(LabelComment.created_at.desc())
            .limit(50)
        )
    
    comments = comments_result.scalars().all()
    
    return {
        "comments": [
            {
                "id": str(c.id),
                "label_id": str(c.label_id),
                "location_identifier": c.label.location.identifier if c.label and hasattr(c.label, 'location') else None,
                "author_name": c.author.name if c.author else "Unknown",
                "content": c.content[:100] + "..." if len(c.content) > 100 else c.content,
                "comment_type": c.comment_type,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in comments
        ],
        "total": len(comments)
    }


@router.post("/{comment_id}/read")
async def mark_comment_read(
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a comment as read."""
    result = await db.execute(
        select(LabelComment).where(LabelComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    comment.is_read = True
    comment.read_at = datetime.utcnow()
    await db.commit()
    
    return {"message": "Comment marked as read"}


@router.post("/{comment_id}/resolve")
async def resolve_comment(
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Mark a comment as resolved (managers only)."""
    result = await db.execute(
        select(LabelComment).where(LabelComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    comment.is_resolved = True
    comment.resolved_at = datetime.utcnow()
    comment.resolved_by_id = current_user.id
    await db.commit()
    
    return {"message": "Comment marked as resolved"}


@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a comment (author or manager only)."""
    result = await db.execute(
        select(LabelComment).where(LabelComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Only author or manager can delete
    if current_user.role == "labeller" and comment.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    await db.delete(comment)
    await db.commit()
    
    return {"message": "Comment deleted"}


@router.get("/task/{task_id}/summary")
async def get_task_comments_summary(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get summary of comments for a task (managers only)."""
    # Get all labels for this task
    labels_result = await db.execute(
        select(Label.id).where(Label.task_id == task_id)
    )
    label_ids = [r[0] for r in labels_result.all()]
    
    if not label_ids:
        return {
            "total_comments": 0,
            "unresolved_feedback": 0,
            "open_questions": 0,
            "labels_with_comments": 0
        }
    
    # Count comments
    total_result = await db.execute(
        select(func.count(LabelComment.id))
        .where(LabelComment.label_id.in_(label_ids))
    )
    total_comments = total_result.scalar() or 0
    
    # Count unresolved feedback
    unresolved_result = await db.execute(
        select(func.count(LabelComment.id))
        .where(
            LabelComment.label_id.in_(label_ids),
            LabelComment.comment_type == "feedback",
            LabelComment.is_resolved == False
        )
    )
    unresolved_feedback = unresolved_result.scalar() or 0
    
    # Count open questions
    questions_result = await db.execute(
        select(func.count(LabelComment.id))
        .where(
            LabelComment.label_id.in_(label_ids),
            LabelComment.comment_type == "question",
            LabelComment.is_resolved == False
        )
    )
    open_questions = questions_result.scalar() or 0
    
    # Count labels with comments
    labels_with_comments_result = await db.execute(
        select(func.count(func.distinct(LabelComment.label_id)))
        .where(LabelComment.label_id.in_(label_ids))
    )
    labels_with_comments = labels_with_comments_result.scalar() or 0
    
    return {
        "total_comments": total_comments,
        "unresolved_feedback": unresolved_feedback,
        "open_questions": open_questions,
        "labels_with_comments": labels_with_comments
    }
