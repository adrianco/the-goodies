"""
Test sync tracking functionality.

DEVELOPMENT CONTEXT:
Created in July 2025 to test the client-side sync tracking implementation
that resolves the TODO items in repository base class. These tests verify
that local changes are properly tracked for sync operations.

FUNCTIONALITY:
Tests the ClientSyncTracking model and repository integration:
- Entity creation/update marks entities as pending
- Sync status transitions (pending → synced → pending)
- Conflict tracking and resolution
- Repository methods: get_pending(), get_conflicts(), mark_synced()

PURPOSE:
Ensures that local change detection works correctly so the sync engine
can identify entities that need to be synchronized with the server.

REVISION HISTORY:
- 2025-07-29: Initial comprehensive sync tracking test suite
- 2025-07-29: Added conflict tracking and status transition tests

DEPENDENCIES:
- pytest-asyncio for async test support
- SQLAlchemy async session for database operations
- ClientSyncTracking model and repository classes
"""

import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from blowingoff.models import Base, Home, Room, Accessory, ClientSyncTracking
from blowingoff.repositories import ClientHomeRepository, ClientRoomRepository, ClientAccessoryRepository


@pytest_asyncio.fixture
async def sync_session():
    """Create test database session with sync tracking."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession)
    
    async with session_factory() as session:
        yield session
    
    await engine.dispose()


@pytest.mark.asyncio
class TestSyncTracking:
    """Test sync tracking functionality."""
    
    async def test_create_entity_marks_pending(self, sync_session):
        """Test that creating an entity marks it as pending."""
        repo = ClientHomeRepository(sync_session)
        
        # Create a home
        home = await repo.create(
            id="test-home-1",
            name="Test Home",
            is_primary=True
        )
        
        # Check that sync tracking record was created
        result = await sync_session.execute(
            select(ClientSyncTracking).where(
                ClientSyncTracking.entity_id == "test-home-1"
            )
        )
        sync_record = result.scalar_one_or_none()
        
        assert sync_record is not None
        assert sync_record.entity_type == "home"
        assert sync_record.sync_status == "pending"
        assert sync_record.operation == "create"
    
    async def test_update_entity_marks_pending(self, sync_session):
        """Test that updating an entity marks it as pending."""
        repo = ClientHomeRepository(sync_session)
        
        # Create a home
        home = await repo.create(
            id="test-home-2",
            name="Test Home",
            is_primary=True
        )
        await sync_session.commit()
        
        # Mark it as synced first
        await repo.mark_synced("test-home-2", datetime.now())
        await sync_session.commit()
        
        # Verify it's marked as synced
        result = await sync_session.execute(
            select(ClientSyncTracking).where(
                ClientSyncTracking.entity_id == "test-home-2"
            )
        )
        sync_record = result.scalar_one()
        assert sync_record.sync_status == "synced"
        
        # Update the home
        await repo.update("test-home-2", name="Updated Home Name")
        await sync_session.commit()
        
        # Check that it's marked as pending again
        result = await sync_session.execute(
            select(ClientSyncTracking).where(
                ClientSyncTracking.entity_id == "test-home-2"
            )
        )
        sync_record = result.scalar_one()
        assert sync_record.sync_status == "pending"
        assert sync_record.operation == "update"
    
    async def test_get_pending_entities(self, sync_session):
        """Test getting entities with pending changes."""
        repo = ClientHomeRepository(sync_session)
        
        # Create multiple homes
        await repo.create(id="home-1", name="Home 1", is_primary=True)
        await repo.create(id="home-2", name="Home 2", is_primary=False)
        await repo.create(id="home-3", name="Home 3", is_primary=False)
        await sync_session.commit()
        
        # Mark one as synced
        await repo.mark_synced("home-2", datetime.now())
        await sync_session.commit()
        
        # Get pending entities
        pending = await repo.get_pending()
        pending_ids = [h.id for h in pending]
        
        assert len(pending) == 2
        assert "home-1" in pending_ids
        assert "home-3" in pending_ids
        assert "home-2" not in pending_ids
    
    async def test_mark_conflict(self, sync_session):
        """Test marking entity as having conflict."""
        repo = ClientAccessoryRepository(sync_session)
        
        # Create an accessory
        accessory = await repo.create(
            id="acc-1",
            home_id="home-1", 
            name="Test Accessory",
            manufacturer="Test Corp",
            serial_number="SN123",
            firmware_version="1.0"
        )
        await sync_session.commit()
        
        # Mark as conflict
        await repo.mark_conflict("acc-1", "Server version is newer")
        await sync_session.commit()
        
        # Check conflict status
        result = await sync_session.execute(
            select(ClientSyncTracking).where(
                ClientSyncTracking.entity_id == "acc-1"
            )
        )
        sync_record = result.scalar_one()
        
        assert sync_record.sync_status == "conflict"
        assert sync_record.conflict_reason == "Server version is newer"
        assert sync_record.retry_count == 1
    
    async def test_get_conflicts(self, sync_session):
        """Test getting entities with conflicts."""
        repo = ClientRoomRepository(sync_session)
        
        # Create rooms
        await repo.create(id="room-1", home_id="home-1", name="Room 1")
        await repo.create(id="room-2", home_id="home-1", name="Room 2")
        await sync_session.commit()
        
        # Mark one as conflict
        await repo.mark_conflict("room-1", "Timestamp conflict")
        await sync_session.commit()
        
        # Get conflicts
        conflicts = await repo.get_conflicts()
        conflict_ids = [r.id for r in conflicts]
        
        assert len(conflicts) == 1
        assert "room-1" in conflict_ids
        assert "room-2" not in conflict_ids
    
    async def test_mark_synced_clears_conflict(self, sync_session):
        """Test that marking as synced clears conflict status."""
        repo = ClientHomeRepository(sync_session)
        
        # Create home and mark as conflict
        await repo.create(id="home-conflict", name="Conflict Home", is_primary=False)
        await repo.mark_conflict("home-conflict", "Test conflict")
        await sync_session.commit()
        
        # Verify conflict state
        result = await sync_session.execute(
            select(ClientSyncTracking).where(
                ClientSyncTracking.entity_id == "home-conflict"
            )
        )
        sync_record = result.scalar_one()
        assert sync_record.sync_status == "conflict"
        assert sync_record.retry_count == 1
        
        # Mark as synced
        await repo.mark_synced("home-conflict", datetime.now())
        await sync_session.commit()
        
        # Verify conflict is cleared
        result = await sync_session.execute(
            select(ClientSyncTracking).where(
                ClientSyncTracking.entity_id == "home-conflict"
            )
        )
        sync_record = result.scalar_one()
        assert sync_record.sync_status == "synced"
        assert sync_record.conflict_reason is None
        assert sync_record.retry_count == 0