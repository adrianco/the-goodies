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
from funkygibbon.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType

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
async def test_home_entity(async_session):
    """Create a test home entity."""
    import uuid

    home = Entity(
        id=str(uuid.uuid4()),
        version=Entity.create_version("test-user"),
        entity_type=EntityType.HOME,
        name="Test Home",
        content={"is_primary": True},
        source_type=SourceType.MANUAL,
        user_id="test-user"
    )
    async_session.add(home)
    await async_session.commit()
    return home


@pytest_asyncio.fixture
async def test_room_entity(async_session, test_home_entity):
    """Create a test room entity."""
    import uuid

    room = Entity(
        id=str(uuid.uuid4()),
        version=Entity.create_version("test-user"),
        entity_type=EntityType.ROOM,
        name="Living Room",
        content={"home_id": test_home_entity.id},
        source_type=SourceType.MANUAL,
        user_id="test-user"
    )
    async_session.add(room)

    # Create relationship to home
    rel = EntityRelationship(
        id=str(uuid.uuid4()),
        from_entity_id=room.id,
        from_entity_version=room.version,
        to_entity_id=test_home_entity.id,
        to_entity_version=test_home_entity.version,
        relationship_type=RelationshipType.LOCATED_IN,
        user_id="test-user"
    )
    async_session.add(rel)

    await async_session.commit()
    return room


@pytest_asyncio.fixture
async def test_device_entity(async_session, test_home_entity, test_room_entity):
    """Create a test device entity."""
    import uuid

    device = Entity(
        id=str(uuid.uuid4()),
        version=Entity.create_version("test-user"),
        entity_type=EntityType.DEVICE,
        name="Test Light",
        content={
            "manufacturer": "Test Corp",
            "model": "TL-100",
            "serial_number": "SN-12345",
            "firmware_version": "1.0.0",
            "is_reachable": True,
            "is_blocked": False,
            "is_bridge": False
        },
        source_type=SourceType.HOMEKIT,
        user_id="test-user"
    )
    async_session.add(device)

    # Create relationship to room
    rel = EntityRelationship(
        id=str(uuid.uuid4()),
        from_entity_id=device.id,
        from_entity_version=device.version,
        to_entity_id=test_room_entity.id,
        to_entity_version=test_room_entity.version,
        relationship_type=RelationshipType.LOCATED_IN,
        user_id="test-user"
    )
    async_session.add(rel)

    await async_session.commit()
    return device
