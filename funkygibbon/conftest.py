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
- 2025-07-28: Created async version of test fixtures

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
from funkygibbon.models import Home, Room, Accessory, Service, Characteristic, User

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
async def test_home(async_session):
    """Create a test home."""
    import uuid
    
    home = Home(
        id=str(uuid.uuid4()),
        name="Test Home",
        is_primary=True
    )
    async_session.add(home)
    await async_session.commit()
    return home


@pytest_asyncio.fixture
async def test_room(async_session, test_home):
    """Create a test room."""
    import uuid
    
    room = Room(
        id=str(uuid.uuid4()),
        home_id=test_home.id,
        name="Living Room"
    )
    async_session.add(room)
    await async_session.commit()
    return room


@pytest_asyncio.fixture
async def test_accessory(async_session, test_home, test_room):
    """Create a test accessory."""
    import uuid
    
    accessory = Accessory(
        id=str(uuid.uuid4()),
        home_id=test_home.id,
        name="Test Light",
        manufacturer="Test Corp",
        model="TL-100",
        serial_number="SN-12345",
        firmware_version="1.0.0",
        is_reachable=True,
        is_blocked=False,
        is_bridge=False
    )
    async_session.add(accessory)
    
    # Link to room
    from funkygibbon.models import accessory_rooms
    await async_session.execute(
        accessory_rooms.insert().values(
            accessory_id=accessory.id,
            room_id=test_room.id
        )
    )
    
    await async_session.commit()
    return accessory


@pytest_asyncio.fixture
async def test_user(async_session, test_home):
    """Create a test user."""
    import uuid
    
    user = User(
        id=str(uuid.uuid4()),
        home_id=test_home.id,
        name="Test User",
        is_administrator=True,
        is_owner=True,
        remote_access_allowed=True
    )
    async_session.add(user)
    await async_session.commit()
    return user