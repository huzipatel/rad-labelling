"""Authentication routes."""
import uuid
import secrets
from datetime import datetime, timedelta, timezone
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
from app.models.user import User, PasswordReset
from app.api.deps import get_current_user
from app.services.email_service import email_service


def utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


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


class ForgotPasswordRequest(BaseModel):
    """Forgot password request."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset password request."""
    token: str
    new_password: str


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


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Request a password reset email.
    
    Always returns success to prevent email enumeration attacks.
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    user = result.scalar_one_or_none()
    
    if user and user.is_active:
        # Generate reset token
        token = secrets.token_urlsafe(32)
        expires_at = utc_now() + timedelta(hours=1)
        
        # Invalidate any existing reset tokens for this user
        existing_result = await db.execute(
            select(PasswordReset).where(
                PasswordReset.user_id == user.id,
                PasswordReset.used_at.is_(None)
            )
        )
        for old_reset in existing_result.scalars().all():
            old_reset.used_at = utc_now()  # Mark as used/invalidated
        
        # Create new reset token
        password_reset = PasswordReset(
            user_id=user.id,
            token=token,
            expires_at=expires_at
        )
        db.add(password_reset)
        await db.commit()
        
        # Build reset URL
        frontend_url = settings.FRONTEND_URL if settings.FRONTEND_URL else (
            settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:5173"
        )
        reset_url = f"{frontend_url}/reset-password?token={token}"
        
        # Send email
        email_service.send_password_reset(
            to_email=user.email,
            user_name=user.name,
            reset_url=reset_url
        )
        
        print(f"[Auth] Password reset requested for {user.email}")
    else:
        # Log but don't reveal whether user exists
        print(f"[Auth] Password reset requested for unknown/inactive email: {request.email}")
    
    # Always return success to prevent email enumeration
    return {
        "message": "If an account with that email exists, we've sent a password reset link."
    }


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reset password using a valid reset token."""
    # Find the reset token
    result = await db.execute(
        select(PasswordReset).where(PasswordReset.token == request.token)
    )
    password_reset = result.scalar_one_or_none()
    
    if not password_reset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link"
        )
    
    # Check if already used
    if password_reset.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has already been used"
        )
    
    # Check if expired
    if password_reset.expires_at < utc_now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired. Please request a new one."
        )
    
    # Get the user
    user_result = await db.execute(
        select(User).where(User.id == password_reset.user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to reset password for this account"
        )
    
    # Validate new password
    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    
    # Update password
    user.hashed_password = get_password_hash(request.new_password)
    
    # Mark token as used
    password_reset.used_at = utc_now()
    
    await db.commit()
    
    print(f"[Auth] Password reset completed for {user.email}")
    
    return {
        "message": "Password has been reset successfully. You can now log in with your new password."
    }


@router.get("/verify-reset-token")
async def verify_reset_token(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Verify if a reset token is valid (for frontend to check before showing form)."""
    result = await db.execute(
        select(PasswordReset).where(PasswordReset.token == token)
    )
    password_reset = result.scalar_one_or_none()
    
    if not password_reset:
        return {"valid": False, "error": "Invalid reset link"}
    
    if password_reset.used_at is not None:
        return {"valid": False, "error": "This reset link has already been used"}
    
    if password_reset.expires_at < utc_now():
        return {"valid": False, "error": "This reset link has expired"}
    
    return {"valid": True}

