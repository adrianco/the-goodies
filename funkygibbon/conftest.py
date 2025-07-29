"""
FunkyGibbon - Async Test Configuration and Fixtures

DEVELOPMENT CONTEXT:
Updated test configuration for async SQLAlchemy models. Provides proper
async fixtures for database sessions and test data generation.

FUNCTIONALITY:
- Async database session fixtures
- Test data factories for all entity types
- Proper cleanup and isolation between tests

REVISION HISTORY:
- 2024-01-15: Created async version of test fixtures

DEPENDENCIES:
- pytest-asyncio: Async test support
- SQLAlchemy: Async ORM
- aiosqlite: Async SQLite driver
"""

import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from datetime import datetime, UTC

from funkygibbon.database import Base
from funkygibbon.models import House, Room, Device, User

# Use SQLite in-memory database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_engine():
    """Create async engine for tests."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """Create async database session for tests."""
    async_session_maker = async_sessionmaker(
        async_engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_house(async_session):
    """Create a test house."""
    from funkygibbon.repositories import HouseRepository
    
    repo = HouseRepository()
    house = await repo.create(
        async_session,
        name="Test House",
        address="123 Test St",
        timezone="UTC"
    )
    await async_session.commit()
    return house


@pytest_asyncio.fixture
async def test_room(async_session, test_house):
    """Create a test room."""
    from funkygibbon.repositories import RoomRepository
    
    repo = RoomRepository()
    room = await repo.create(
        async_session,
        house_id=test_house.id,
        name="Living Room",
        floor=1,
        room_type="living_room"
    )
    await async_session.commit()
    return room


@pytest_asyncio.fixture
async def test_device(async_session, test_room):
    """Create a test device."""
    from funkygibbon.repositories import DeviceRepository
    
    repo = DeviceRepository()
    device = await repo.create(
        async_session,
        room_id=test_room.id,
        name="Test Light",
        device_type="light",
        manufacturer="Test Corp",
        model="TL-100"
    )
    await async_session.commit()
    return device


@pytest_asyncio.fixture
async def test_user(async_session, test_house):
    """Create a test user."""
    from funkygibbon.repositories import UserRepository
    
    repo = UserRepository()
    user = await repo.create(
        async_session,
        house_id=test_house.id,
        name="Test User",
        email="test@example.com",
        role="admin"
    )
    await async_session.commit()
    return user