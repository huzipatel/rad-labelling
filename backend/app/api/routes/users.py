"""User management routes."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.security import get_password_hash
from app.core.permissions import UserRole
from app.models.user import User
from app.api.deps import get_current_user, require_manager, require_admin


router = APIRouter(prefix="/users", tags=["Users"])


class UserCreate(BaseModel):
    """Create user request."""
    email: EmailStr
    name: str
    password: Optional[str] = None
    role: str = "labeller"
    hourly_rate: Optional[float] = None
    whatsapp_number: Optional[str] = None


class UserUpdate(BaseModel):
    """Update user request."""
    name: Optional[str] = None
    role: Optional[str] = None
    hourly_rate: Optional[float] = None
    whatsapp_number: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    """User response model."""
    id: str
    email: str
    name: str
    role: str
    hourly_rate: Optional[float] = None
    whatsapp_number: Optional[str] = None
    is_active: bool
    
    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """Paginated user list response."""
    users: List[UserResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """List all users (manager/admin only)."""
    query = select(User)
    count_query = select(func.count(User.id))
    
    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            (User.name.ilike(search_filter)) | (User.email.ilike(search_filter))
        )
        count_query = count_query.where(
            (User.name.ilike(search_filter)) | (User.email.ilike(search_filter))
        )
    
    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get paginated results
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(User.created_at.desc())
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    return UserListResponse(
        users=[
            UserResponse(
                id=str(u.id),
                email=u.email,
                name=u.name,
                role=u.role,
                hourly_rate=float(u.hourly_rate) if u.hourly_rate else None,
                whatsapp_number=u.whatsapp_number,
                is_active=u.is_active
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/labellers", response_model=List[UserResponse])
async def list_labellers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """List all users who can be assigned tasks (labellers, managers, and admins)."""
    result = await db.execute(
        select(User).where(
            User.role.in_(["labeller", "labelling_manager", "admin"]),
            User.is_active == True
        ).order_by(User.name)
    )
    users = result.scalars().all()
    
    return [
        UserResponse(
            id=str(u.id),
            email=u.email,
            name=u.name,
            role=u.role,
            hourly_rate=float(u.hourly_rate) if u.hourly_rate else None,
            whatsapp_number=u.whatsapp_number,
            is_active=u.is_active
        )
        for u in users
    ]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Get a specific user by ID."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        hourly_rate=float(user.hourly_rate) if user.hourly_rate else None,
        whatsapp_number=user.whatsapp_number,
        is_active=user.is_active
    )


@router.post("", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new user (admin only)."""
    # Check if creating a manager (only admin can do this)
    if user_data.role == "labelling_manager":
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can create labelling managers"
            )
    
    # Check if email exists
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate role
    valid_roles = ["labeller", "labelling_manager", "admin"]
    if user_data.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )
    
    # Create user
    user = User(
        email=user_data.email,
        name=user_data.name,
        role=user_data.role,
        hourly_rate=user_data.hourly_rate,
        whatsapp_number=user_data.whatsapp_number
    )
    
    if user_data.password:
        user.hashed_password = get_password_hash(user_data.password)
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        hourly_rate=float(user.hourly_rate) if user.hourly_rate else None,
        whatsapp_number=user.whatsapp_number,
        is_active=user.is_active
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a user (admin only)."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update fields
    if user_data.name is not None:
        user.name = user_data.name
    if user_data.role is not None:
        # Validate role change
        if user_data.role == "admin" and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can promote to admin"
            )
        user.role = user_data.role
    if user_data.hourly_rate is not None:
        user.hourly_rate = user_data.hourly_rate
    if user_data.whatsapp_number is not None:
        user.whatsapp_number = user_data.whatsapp_number
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    
    await db.commit()
    await db.refresh(user)
    
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        hourly_rate=float(user.hourly_rate) if user.hourly_rate else None,
        whatsapp_number=user.whatsapp_number,
        is_active=user.is_active
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Deactivate a user (admin only)."""
    if str(user_id) == str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_active = False
    await db.commit()
    
    return {"message": "User deactivated successfully"}

