"""Authentication routes."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import httpx

from app.core.database import get_db
from app.core.config import settings
from app.core.security import (
    create_token_response,
    get_password_hash,
    verify_password,
    Token
)
from app.models.user import User
from app.api.deps import get_current_user


router = APIRouter(prefix="/auth", tags=["Authentication"])


class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    """Google OAuth token request."""
    token: str


class UserResponse(BaseModel):
    """User response model."""
    id: str
    email: str
    name: str
    role: str
    
    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Authentication response."""
    user: UserResponse
    token: Token


@router.post("/register", response_model=AuthResponse)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user (default role: labeller)."""
    # Check if user exists
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    user = User(
        email=user_data.email,
        name=user_data.name,
        hashed_password=get_password_hash(user_data.password),
        role="labeller"  # Default role
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Generate token
    token = create_token_response(str(user.id), user.email, user.role)
    
    return AuthResponse(
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role
        ),
        token=token
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password."""
    result = await db.execute(
        select(User).where(User.email == credentials.email)
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    token = create_token_response(str(user.id), user.email, user.role)
    
    return AuthResponse(
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role
        ),
        token=token
    )


@router.get("/google")
async def google_login():
    """Redirect to Google OAuth login."""
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
    )
    return RedirectResponse(url=google_auth_url)


@router.get("/google/callback", response_model=AuthResponse)
async def google_callback(
    code: str,
    db: AsyncSession = Depends(get_db)
):
    """Handle Google OAuth callback."""
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )
    
    if token_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange code for token"
        )
    
    token_data = token_response.json()
    id_token_str = token_data.get("id_token")
    
    # Verify and decode the ID token
    try:
        idinfo = id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid token: {str(e)}"
        )
    
    google_id = idinfo.get("sub")
    email = idinfo.get("email")
    name = idinfo.get("name", email.split("@")[0])
    
    # Find or create user
    result = await db.execute(
        select(User).where(
            (User.google_id == google_id) | (User.email == email)
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        # Create new user
        user = User(
            email=email,
            name=name,
            google_id=google_id,
            role="labeller"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif not user.google_id:
        # Link existing account to Google
        user.google_id = google_id
        await db.commit()
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    token = create_token_response(str(user.id), user.email, user.role)
    
    return AuthResponse(
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role
        ),
        token=token
    )


@router.post("/google/token", response_model=AuthResponse)
async def google_token_auth(
    auth_request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate with a Google ID token (for frontend OAuth flow)."""
    try:
        idinfo = id_token.verify_oauth2_token(
            auth_request.token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid token: {str(e)}"
        )
    
    google_id = idinfo.get("sub")
    email = idinfo.get("email")
    name = idinfo.get("name", email.split("@")[0])
    
    # Find or create user
    result = await db.execute(
        select(User).where(
            (User.google_id == google_id) | (User.email == email)
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            email=email,
            name=name,
            google_id=google_id,
            role="labeller"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif not user.google_id:
        user.google_id = google_id
        await db.commit()
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    token = create_token_response(str(user.id), user.email, user.role)
    
    return AuthResponse(
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role
        ),
        token=token
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        role=current_user.role
    )

