"""Database connection and session management."""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData, text

from app.core.config import settings


def get_async_database_url(url: str) -> str:
    """
    Convert database URL to async format for SQLAlchemy.
    
    Render/Heroku provide: postgres://user:pass@host:5432/db
    SQLAlchemy asyncpg needs: postgresql+asyncpg://user:pass@host:5432/db
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# Naming convention for constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """Base class for all database models."""
    metadata = metadata


# Convert DATABASE_URL to async format
database_url = get_async_database_url(settings.DATABASE_URL)
print(f"[Database] Connecting to: {database_url.split('@')[1] if '@' in database_url else 'configured database'}")

# Create async engine for web server
engine = create_async_engine(
    database_url,
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=30,
    pool_recycle=1800,  # Recycle connections after 30 minutes
    pool_pre_ping=True,  # Check connection health before use
)

# Create async session factory for web server
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


def get_celery_engine():
    """Create a separate engine for Celery workers to avoid pool conflicts."""
    return create_async_engine(
        database_url,
        echo=False,
        pool_size=2,  # Smaller pool for worker
        max_overflow=3,
        pool_timeout=60,  # Longer timeout for workers
        pool_recycle=600,  # Recycle more frequently
        pool_pre_ping=True,
        connect_args={
            "timeout": 60,  # Connection timeout
            "command_timeout": 300,  # Query timeout (5 min)
        }
    )


def get_celery_session_maker():
    """Create a session maker for Celery workers."""
    celery_engine = get_celery_engine()
    return async_sessionmaker(
        celery_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    # Import all models to ensure they're registered
    from app.models import (
        User, Invitation, Location, LocationType, Task, Label, GSVImage,
        CouncilBoundary, CombinedAuthority, RoadClassification,
        Shapefile, EnhancementJob, UploadJob, DownloadLog,
        NotificationSettings, UserNotificationPreferences, NotificationLog
    )
    
    # Enable PostGIS extension first (required for geography/geometry types)
    print("[Database] Enabling PostGIS extension...")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    print("[Database] PostGIS extension enabled")
    
    print("[Database] Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[Database] Tables created successfully")
    
    # Add missing columns to existing tables (safe to run multiple times)
    print("[Database] Adding missing columns to users table...")
    try:
        async with engine.begin() as conn:
            # Check and add each column individually with explicit error handling
            # phone_number
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='phone_number'"
            ))
            if not result.fetchone():
                print("[Database] Adding phone_number column...")
                await conn.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(20)"))
            
            # whatsapp_number
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='whatsapp_number'"
            ))
            if not result.fetchone():
                print("[Database] Adding whatsapp_number column...")
                await conn.execute(text("ALTER TABLE users ADD COLUMN whatsapp_number VARCHAR(20)"))
            
            # notify_daily_reminder
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='notify_daily_reminder'"
            ))
            if not result.fetchone():
                print("[Database] Adding notify_daily_reminder column...")
                await conn.execute(text("ALTER TABLE users ADD COLUMN notify_daily_reminder BOOLEAN DEFAULT TRUE"))
            
            # notify_task_assigned
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='notify_task_assigned'"
            ))
            if not result.fetchone():
                print("[Database] Adding notify_task_assigned column...")
                await conn.execute(text("ALTER TABLE users ADD COLUMN notify_task_assigned BOOLEAN DEFAULT TRUE"))
        
        print("[Database] Users table columns updated")
    except Exception as e:
        print(f"[Database] Error adding user columns: {e}")
    
    # Add sample task columns
    print("[Database] Adding missing columns to tasks table...")
    try:
        async with engine.begin() as conn:
            # is_sample
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='tasks' AND column_name='is_sample'"
            ))
            if not result.fetchone():
                print("[Database] Adding is_sample column...")
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN is_sample BOOLEAN DEFAULT FALSE"))
            
            # source_task_id
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='tasks' AND column_name='source_task_id'"
            ))
            if not result.fetchone():
                print("[Database] Adding source_task_id column...")
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN source_task_id UUID"))
            
            # sample_location_ids
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='tasks' AND column_name='sample_location_ids'"
            ))
            if not result.fetchone():
                print("[Database] Adding sample_location_ids column...")
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN sample_location_ids JSONB"))
        
        print("[Database] Tasks table columns updated")
    except Exception as e:
        print(f"[Database] Error adding task columns: {e}")
    
    print("[Database] Schema migration completed")


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()

