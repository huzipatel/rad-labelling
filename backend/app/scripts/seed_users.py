"""
Seed script to create test users for development.

Run with: docker-compose exec backend python -m app.scripts.seed_users
"""
import asyncio
import sys
import uuid
from sqlalchemy import select
from app.core.database import async_session_maker
from app.core.security import get_password_hash
from app.models.user import User


TEST_USERS = [
    {
        "name": "Admin User",
        "email": "admin@advue.uk",
        "password": "admin123",
        "role": "admin",
    },
    {
        "name": "Manager User", 
        "email": "manager@advue.uk",
        "password": "manager123",
        "role": "labelling_manager",
    },
    {
        "name": "Labeller User",
        "email": "labeller@advue.uk", 
        "password": "labeller123",
        "role": "labeller",
    },
]


def log(message: str):
    """Print with flush for immediate output."""
    print(message, flush=True)


async def seed_users():
    """Create test users if they don't exist."""
    log("Starting user seeding...")
    
    try:
        async with async_session_maker() as session:
            for user_data in TEST_USERS:
                # Check if user exists
                result = await session.execute(
                    select(User).where(User.email == user_data["email"])
                )
                existing_user = result.scalar_one_or_none()
                
                if existing_user:
                    log(f"[OK] User already exists: {user_data['email']} ({user_data['role']})")
                    continue
                
                # Create new user
                new_user = User(
                    id=uuid.uuid4(),
                    name=user_data["name"],
                    email=user_data["email"],
                    hashed_password=get_password_hash(user_data["password"]),
                    role=user_data["role"],
                    is_active=True,
                )
                session.add(new_user)
                await session.commit()
                log(f"[NEW] Created user: {user_data['email']} ({user_data['role']})")
        
        log("")
        log("=" * 50)
        log("TEST ACCOUNTS READY")
        log("=" * 50)
        log("")
        log("Sign in with these credentials:")
        log("")
        for user in TEST_USERS:
            log(f"  {user['role'].upper()}")
            log(f"    Email:    {user['email']}")
            log(f"    Password: {user['password']}")
            log("")
            
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(seed_users())

