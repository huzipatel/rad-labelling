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

# Create async engine
engine = create_async_engine(
    database_url,
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
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
        User, Location, LocationType, Task, Label, GSVImage,
        CouncilBoundary, CombinedAuthority, RoadClassification,
        Shapefile, EnhancementJob, UploadJob, DownloadLog
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


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()

