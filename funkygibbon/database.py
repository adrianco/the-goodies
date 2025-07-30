"""
FunkyGibbon - Database Configuration and Session Management

DEVELOPMENT CONTEXT:
Created in July 2025 as the database layer for the simplified single-house
smart home system. This module replaced a more complex multi-tenant database
design when we pivoted to focus on single-family deployments with SQLite.

FUNCTIONALITY:
- Creates and configures async SQLAlchemy engine with SQLite optimizations
- Provides async session factory for database connections
- Initializes database schema from SQLAlchemy models
- Applies SQLite-specific performance optimizations (WAL mode, caching)
- Manages database session lifecycle with proper cleanup
- Provides both dependency injection and context manager patterns

PURPOSE:
Centralizes all database configuration and connection management to ensure
consistent settings, proper async handling, and optimal SQLite performance
for our target scale of ~300 entities per house.

KNOWN ISSUES:
- SQLite file locking can cause issues with multiple processes
- No automatic migration support - schema changes require manual handling
- Connection timeout (30s) might be too long for some operations
- No connection pooling for SQLite (not needed but could confuse developers)
- WAL mode can leave -wal and -shm files that need cleanup

REVISION HISTORY:
- 2025-07-28: Initial async SQLAlchemy setup
- 2025-07-28: Added SQLite-specific optimizations (WAL, cache size)
- 2025-07-28: Added both dependency injection and context manager patterns
- 2025-07-28: Increased timeout and added pool_pre_ping for reliability

DEPENDENCIES:
- sqlalchemy: Async ORM and database toolkit
- sqlalchemy.ext.asyncio: Async extensions for SQLAlchemy
- .config: Application settings
- .models.base: Base model class with common fields

USAGE:
# For FastAPI dependency injection:
@app.get("/items")
async def get_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item))
    return result.scalars().all()

# For standalone scripts:
async with get_db_context() as db:
    await db.execute(...)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base


# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    # SQLite-specific optimizations
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    } if "sqlite" in settings.database_url else {}
)

# Create async session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Enable SQLite optimizations
        if "sqlite" in settings.database_url:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=10000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))  # 5 second timeout for busy retries
            await conn.execute(text("PRAGMA wal_autocheckpoint=1000"))  # Auto checkpoint every 1000 pages


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for dependency injection."""
    async with async_session() as session:
        try:
            # Set busy timeout for this session to handle concurrent access
            if "sqlite" in settings.database_url:
                await session.execute(text("PRAGMA busy_timeout=5000"))
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Get database session as context manager."""
    async with async_session() as session:
        try:
            # Set busy timeout for this session to handle concurrent access
            if "sqlite" in settings.database_url:
                await session.execute(text("PRAGMA busy_timeout=5000"))
            yield session
        finally:
            await session.close()