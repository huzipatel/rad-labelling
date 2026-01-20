"""User invitation management routes."""
import uuid
import secrets
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User, Invitation
from app.api.deps import require_manager, require_admin
from app.services.email_service import email_service


router = APIRouter(prefix="/invitations", tags=["Invitations"])


class InvitationCreate(BaseModel):
    """Create invitation request."""
    email: EmailStr
    name: Optional[str] = None
    role: str = "labeller"  # labeller, labelling_manager, admin
    message: Optional[str] = None


class InvitationResponse(BaseModel):
    """Invitation response."""
    id: str
    email: str
    name: Optional[str]
    role: str
    status: str
    message: Optional[str]
    invited_by_name: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]


class InvitationAccept(BaseModel):
    """Accept invitation request."""
    token: str
    name: str
    password: str
    phone_number: Optional[str] = None
    whatsapp_number: Optional[str] = None


class InvitationValidate(BaseModel):
    """Validate invitation response."""
    valid: bool
    email: str
    name: Optional[str]
    role: str
    message: Optional[str]
    inviter_name: str


@router.post("/", response_model=InvitationResponse)
async def create_invitation(
    request: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """
    Create and send an invitation to a new user.
    
    Managers can invite labellers.
    Admins can invite anyone.
    """
    # Validate role permissions
    if request.role == "admin" and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can invite other admins"
        )
    
    if request.role == "labelling_manager" and current_user.role not in ["admin", "labelling_manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only managers and admins can invite managers"
        )
    
    # Check if user already exists
    existing_user = await db.execute(
        select(User).where(User.email == request.email)
    )
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists"
        )
    
    # Check for existing pending invitation
    existing_invite = await db.execute(
        select(Invitation).where(
            Invitation.email == request.email,
            Invitation.status == "pending"
        )
    )
    if existing_invite.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An invitation has already been sent to this email"
        )
    
    # Create invitation token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    invitation = Invitation(
        email=request.email,
        name=request.name,
        role=request.role,
        token=token,
        invited_by_id=current_user.id,
        message=request.message,
        status="pending",
        expires_at=expires_at
    )
    
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    
    # Send invitation email
    frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:5173"
    invitation_url = f"{frontend_url}/accept-invite?token={token}"
    
    email_sent = email_service.send_invitation(
        to_email=request.email,
        inviter_name=current_user.name,
        role=request.role,
        invitation_url=invitation_url,
        message=request.message
    )
    
    if not email_sent:
        print(f"[Invitation] Email not sent (SMTP not configured). Invitation URL: {invitation_url}")
    
    return InvitationResponse(
        id=str(invitation.id),
        email=invitation.email,
        name=invitation.name,
        role=invitation.role,
        status=invitation.status,
        message=invitation.message,
        invited_by_name=current_user.name,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at
    )


@router.get("/", response_model=List[InvitationResponse])
async def list_invitations(
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """List all invitations."""
    query = select(Invitation).order_by(Invitation.created_at.desc())
    
    if status_filter:
        query = query.where(Invitation.status == status_filter)
    
    result = await db.execute(query)
    invitations = result.scalars().all()
    
    # Get inviter names
    inviter_ids = {inv.invited_by_id for inv in invitations}
    inviters_result = await db.execute(
        select(User).where(User.id.in_(inviter_ids))
    )
    inviters = {str(u.id): u.name for u in inviters_result.scalars().all()}
    
    return [
        InvitationResponse(
            id=str(inv.id),
            email=inv.email,
            name=inv.name,
            role=inv.role,
            status=inv.status,
            message=inv.message,
            invited_by_name=inviters.get(str(inv.invited_by_id), "Unknown"),
            created_at=inv.created_at,
            expires_at=inv.expires_at,
            accepted_at=inv.accepted_at
        )
        for inv in invitations
    ]


@router.get("/validate/{token}", response_model=InvitationValidate)
async def validate_invitation(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Validate an invitation token.
    
    This is a public endpoint - no authentication required.
    """
    result = await db.execute(
        select(Invitation).where(Invitation.token == token)
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invitation token"
        )
    
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has already been used"
        )
    
    if invitation.expires_at < datetime.utcnow():
        invitation.status = "expired"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired"
        )
    
    # Get inviter name
    inviter_result = await db.execute(
        select(User).where(User.id == invitation.invited_by_id)
    )
    inviter = inviter_result.scalar_one_or_none()
    
    return InvitationValidate(
        valid=True,
        email=invitation.email,
        name=invitation.name,
        role=invitation.role,
        message=invitation.message,
        inviter_name=inviter.name if inviter else "Unknown"
    )


@router.post("/accept")
async def accept_invitation(
    request: InvitationAccept,
    db: AsyncSession = Depends(get_db)
):
    """
    Accept an invitation and create a new user account.
    
    This is a public endpoint - no authentication required.
    """
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    # Find invitation
    result = await db.execute(
        select(Invitation).where(Invitation.token == request.token)
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invitation token"
        )
    
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has already been used"
        )
    
    if invitation.expires_at < datetime.utcnow():
        invitation.status = "expired"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired"
        )
    
    # Check email not already taken
    existing = await db.execute(
        select(User).where(User.email == invitation.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists"
        )
    
    # Create user
    hashed_password = pwd_context.hash(request.password)
    
    user = User(
        email=invitation.email,
        name=request.name,
        hashed_password=hashed_password,
        role=invitation.role,
        phone_number=request.phone_number,
        whatsapp_number=request.whatsapp_number
    )
    
    db.add(user)
    
    # Mark invitation as accepted
    invitation.status = "accepted"
    invitation.accepted_at = datetime.utcnow()
    
    await db.commit()
    
    return {
        "message": "Account created successfully",
        "email": user.email,
        "role": user.role
    }


@router.delete("/{invitation_id}")
async def cancel_invitation(
    invitation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Cancel a pending invitation."""
    result = await db.execute(
        select(Invitation).where(Invitation.id == invitation_id)
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only cancel pending invitations"
        )
    
    await db.delete(invitation)
    await db.commit()
    
    return {"message": "Invitation cancelled"}


@router.post("/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Resend an invitation email and reset expiration."""
    result = await db.execute(
        select(Invitation).where(Invitation.id == invitation_id)
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resend pending invitations"
        )
    
    # Generate new token and extend expiration
    invitation.token = secrets.token_urlsafe(32)
    invitation.expires_at = datetime.utcnow() + timedelta(days=7)
    await db.commit()
    
    # Resend email
    frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:5173"
    invitation_url = f"{frontend_url}/accept-invite?token={invitation.token}"
    
    email_service.send_invitation(
        to_email=invitation.email,
        inviter_name=current_user.name,
        role=invitation.role,
        invitation_url=invitation_url,
        message=invitation.message
    )
    
    return {"message": "Invitation resent"}


