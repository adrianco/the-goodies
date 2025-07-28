"""
Integration tests for sync functionality.
"""

import asyncio
from datetime import datetime, timedelta, UTC

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.models import House
from funkygibbon.repositories import HouseRepository, RoomRepository, DeviceRepository


@pytest.mark.integration
@pytest.mark.asyncio
class TestSyncIntegration:
    """Test end-to-end sync scenarios."""
    
    async def test_sync_new_entity(self, db_session: AsyncSession):
        """Test syncing a completely new entity."""
        repo = HouseRepository()
        
        remote_data = {
            "sync_id": "new-sync-id",
            "name": "New Remote House",
            "address": "789 New St",
            "timezone": "UTC",
            "room_count": 0,
            "device_count": 0,
            "user_count": 0,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "version": "1",
            "is_deleted": False
        }
        
        entity, updated, conflict = await repo.sync_entity(db_session, remote_data)
        
        assert entity is not None
        assert updated is True
        assert conflict is None
        assert entity.name == "New Remote House"
        assert entity.sync_id == "new-sync-id"
    
    async def test_sync_conflict_remote_wins(self, db_session: AsyncSession):
        """Test sync conflict where remote wins."""
        repo = HouseRepository()
        
        # Create local entity
        local = await repo.create(
            db_session,
            name="Local House",
            sync_id="conflict-sync-id"
        )
        
        # Wait to ensure different timestamps
        await asyncio.sleep(0.1)
        
        # Create remote data with newer timestamp
        remote_data = {
            "sync_id": "conflict-sync-id",
            "name": "Remote House",
            "address": "Remote Address",
            "timezone": "America/New_York",
            "room_count": 5,
            "device_count": 10,
            "user_count": 2,
            "created_at": local.created_at,
            "updated_at": datetime.now(UTC) + timedelta(seconds=10),
            "version": "2",
            "is_deleted": False
        }
        
        entity, updated, conflict = await repo.sync_entity(db_session, remote_data)
        
        assert entity is not None
        assert updated is True
        assert conflict is not None
        assert conflict.winner["name"] == "Remote House"
        assert conflict.loser["name"] == "Local House"
        assert entity.name == "Remote House"
        assert entity.address == "Remote Address"
    
    async def test_sync_conflict_local_wins(self, db_session: AsyncSession):
        """Test sync conflict where local wins."""
        repo = HouseRepository()
        
        # Create local entity with recent timestamp
        local = await repo.create(
            db_session,
            name="Local House Latest",
            sync_id="local-wins-sync-id"
        )
        
        # Create remote data with older timestamp
        remote_data = {
            "sync_id": "local-wins-sync-id",
            "name": "Remote House Old",
            "address": "Old Address",
            "timezone": "UTC",
            "room_count": 0,
            "device_count": 0,
            "user_count": 0,
            "created_at": local.created_at,
            "updated_at": local.updated_at - timedelta(seconds=10),
            "version": "1",
            "is_deleted": False
        }
        
        entity, updated, conflict = await repo.sync_entity(db_session, remote_data)
        
        assert entity is not None
        assert updated is False  # Local wins, no update
        assert conflict is not None
        assert conflict.winner["name"] == "Local House Latest"
        assert conflict.loser["name"] == "Remote House Old"
        assert entity.name == "Local House Latest"  # Unchanged
    
    async def test_sync_cascade_updates(self, db_session: AsyncSession):
        """Test syncing with cascading counter updates."""
        house_repo = HouseRepository()
        room_repo = RoomRepository()
        device_repo = DeviceRepository()
        
        # Create house
        house = await house_repo.create(db_session, name="Test House")
        
        # Create rooms
        room1 = await room_repo.create_with_house_name(
            db_session, house.id, house.name, name="Room 1"
        )
        room2 = await room_repo.create_with_house_name(
            db_session, house.id, house.name, name="Room 2"
        )
        
        # Create devices
        for i in range(3):
            await device_repo.create_with_names(
                db_session,
                room_id=room1.id,
                room_name=room1.name,
                house_id=house.id,
                house_name=house.name,
                name=f"Device {i+1}",
                device_type="sensor"
            )
        
        # Update counters
        await house_repo.update_counters(db_session, house.id)
        await room_repo.update_device_count(db_session, room1.id)
        
        # Verify counters
        updated_house = await house_repo.get_by_id(db_session, house.id)
        updated_room = await room_repo.get_by_id(db_session, room1.id)
        
        assert updated_house.room_count == 2
        assert updated_house.device_count == 3
        assert updated_room.device_count == 3
    
    async def test_get_changes_batch(self, db_session: AsyncSession):
        """Test getting changes in batches."""
        house_repo = HouseRepository()
        
        # Create many houses
        base_time = datetime.now(UTC)
        
        for i in range(10):
            await house_repo.create(
                db_session,
                name=f"House {i}",
                created_at=base_time + timedelta(seconds=i),
                updated_at=base_time + timedelta(seconds=i)
            )
        
        # Get changes with limit
        changes = await house_repo.get_changes_since(
            db_session,
            base_time - timedelta(seconds=1),
            limit=5
        )
        
        assert len(changes) == 5
        
        # Verify they're the oldest 5
        for i, house in enumerate(changes):
            assert house.name == f"House {i}"