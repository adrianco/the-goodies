"""
Basic tests to verify the system works.
"""

import asyncio
import json
from datetime import datetime, UTC

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from funkygibbon.database import Base
from funkygibbon.models import House, Room, Device, User
from funkygibbon.repositories import (
    HouseRepository,
    RoomRepository, 
    DeviceRepository,
    UserRepository,
    ConflictResolver
)


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.mark.asyncio
async def test_create_house(async_session: AsyncSession):
    """Test creating a house."""
    house_repo = HouseRepository()
    
    house = await house_repo.create(
        async_session,
        name="Test House",
        address="123 Test St",
        timezone="America/New_York"
    )
    
    assert house.id is not None
    assert house.name == "Test House"
    assert house.address == "123 Test St"
    assert house.timezone == "America/New_York"
    assert house.room_count == 0
    assert house.device_count == 0
    assert house.user_count == 0


@pytest.mark.asyncio
async def test_create_room_with_house(async_session: AsyncSession):
    """Test creating a room in a house."""
    house_repo = HouseRepository()
    room_repo = RoomRepository()
    
    # Create house
    house = await house_repo.create(async_session, name="Test House")
    
    # Create room
    room = await room_repo.create_with_house_name(
        async_session,
        house_id=house.id,
        house_name=house.name,
        name="Living Room",
        room_type="living_room",
        floor=1
    )
    
    assert room.id is not None
    assert room.house_id == house.id
    assert room.house_name == "Test House"
    assert room.name == "Living Room"
    assert room.room_type == "living_room"
    assert room.floor == 1
    assert room.device_count == 0


@pytest.mark.asyncio
async def test_create_device_with_room(async_session: AsyncSession):
    """Test creating a device in a room."""
    house_repo = HouseRepository()
    room_repo = RoomRepository()
    device_repo = DeviceRepository()
    
    # Create house and room
    house = await house_repo.create(async_session, name="Test House")
    room = await room_repo.create_with_house_name(
        async_session,
        house_id=house.id,
        house_name=house.name,
        name="Living Room"
    )
    
    # Create device
    device = await device_repo.create_with_names(
        async_session,
        room_id=room.id,
        room_name=room.name,
        house_id=house.id,
        house_name=house.name,
        name="Smart Light",
        device_type="light",
        manufacturer="Philips",
        model="Hue Go"
    )
    
    assert device.id is not None
    assert device.room_id == room.id
    assert device.room_name == "Living Room"
    assert device.house_id == house.id
    assert device.house_name == "Test House"
    assert device.name == "Smart Light"
    assert device.device_type == "light"


@pytest.mark.asyncio
async def test_conflict_resolution():
    """Test last-write-wins conflict resolution."""
    resolver = ConflictResolver()
    
    # Create two versions of the same entity
    local = {
        "id": "123",
        "sync_id": "abc",
        "name": "Local Name",
        "updated_at": "2024-01-01T12:00:00Z"
    }
    
    remote = {
        "id": "123",
        "sync_id": "abc",
        "name": "Remote Name",
        "updated_at": "2024-01-01T12:00:05Z"  # 5 seconds newer
    }
    
    resolution = resolver.resolve(local, remote)
    
    assert resolution.winner == remote
    assert resolution.loser == local
    assert resolution.reason == "remote has newer timestamp"
    assert resolution.timestamp_diff_ms == 5000


@pytest.mark.asyncio
async def test_soft_delete(async_session: AsyncSession):
    """Test soft delete functionality."""
    house_repo = HouseRepository()
    
    # Create and then delete a house
    house = await house_repo.create(async_session, name="To Delete")
    house_id = house.id
    
    # Soft delete
    success = await house_repo.soft_delete(async_session, house_id)
    assert success is True
    
    # Should not find with regular get
    deleted_house = await house_repo.get_by_id(async_session, house_id)
    assert deleted_house is None
    
    # But should still exist in database with is_deleted=True
    from sqlalchemy import select
    stmt = select(House).where(House.id == house_id)
    result = await async_session.execute(stmt)
    actual_house = result.scalar_one_or_none()
    assert actual_house is not None
    assert actual_house.is_deleted is True


@pytest.mark.asyncio
async def test_sync_entity_new(async_session: AsyncSession):
    """Test syncing a new entity."""
    house_repo = HouseRepository()
    
    remote_data = {
        "sync_id": "remote-123",
        "name": "Remote House",
        "address": "456 Remote St",
        "timezone": "UTC",
        "room_count": 0,
        "device_count": 0,
        "user_count": 0,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "version": "1",
        "is_deleted": False
    }
    
    entity, updated, conflict = await house_repo.sync_entity(async_session, remote_data)
    
    assert entity is not None
    assert updated is True
    assert conflict is None
    assert entity.name == "Remote House"
    assert entity.sync_id == "remote-123"


@pytest.mark.asyncio
async def test_get_changes_since(async_session: AsyncSession):
    """Test getting entities changed since a timestamp."""
    house_repo = HouseRepository()
    
    # Create some houses
    await house_repo.create(async_session, name="House 1")
    await asyncio.sleep(0.1)  # Small delay
    
    checkpoint = datetime.now(UTC)
    await asyncio.sleep(0.1)  # Small delay
    
    house2 = await house_repo.create(async_session, name="House 2")
    await house_repo.create(async_session, name="House 3")
    
    # Get changes since checkpoint
    changes = await house_repo.get_changes_since(async_session, checkpoint)
    
    assert len(changes) == 2
    assert all(h.name in ["House 2", "House 3"] for h in changes)


if __name__ == "__main__":
    # Run basic test
    async def main():
        print("Running basic tests...")
        
        # Create in-memory database
        engine = create_async_engine(TEST_DATABASE_URL, echo=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as session:
            house_repo = HouseRepository()
            
            # Test basic creation
            house = await house_repo.create(
                session,
                name="Demo House",
                address="789 Demo Lane"
            )
            print(f"Created house: {house.to_dict()}")
            
            # Test conflict resolution
            resolver = ConflictResolver()
            local = {"id": "1", "sync_id": "a", "updated_at": "2024-01-01T12:00:00Z"}
            remote = {"id": "1", "sync_id": "a", "updated_at": "2024-01-01T12:00:10Z"}
            resolution = resolver.resolve(local, remote)
            print(f"Conflict resolution: {resolution}")
        
        await engine.dispose()
        print("Tests completed!")
    
    asyncio.run(main())