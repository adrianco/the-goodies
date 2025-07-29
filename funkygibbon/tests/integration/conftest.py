"""
FunkyGibbon - Integration Test Configuration

DEVELOPMENT CONTEXT:
Fixtures for integration tests that test the full API stack.

REVISION HISTORY:
- 2024-01-15: Created async fixtures for API testing
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from funkygibbon.api.app import create_app
from funkygibbon.database import Base, get_db

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine):
    """Create test database session."""
    async_session_maker = async_sessionmaker(
        test_engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def app(test_session):
    """Create test FastAPI app with test database."""
    app = create_app()
    
    # Override the get_db dependency
    async def override_get_db():
        yield test_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield app
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client(app):
    """Create async test client."""
    from httpx import ASGITransport
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client