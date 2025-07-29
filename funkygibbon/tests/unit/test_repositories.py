"""
Unit tests for repository layer.

REVISION HISTORY:
- 2025-07-28: Fixed fixture name from db_session to async_session for proper test execution
"""

import asyncio
from datetime import datetime, timedelta, UTC

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.models import House, Room, Device, User
from funkygibbon.repositories import (
    HouseRepository,
    RoomRepository,
    DeviceRepository,
    UserRepository,
    ConflictResolver
)


@pytest.mark.unit
@pytest.mark.asyncio
class TestConflictResolver:
    """Test conflict resolution logic."""
    
    async def test_remote_wins_newer_timestamp(self):
        """Test remote wins with newer timestamp."""
        resolver = ConflictResolver()
        
        local = {
            "id": "123",
            "sync_id": "abc",
            "name": "Local",
            "updated_at": "2024-01-01T12:00:00Z"
        }
        
        remote = {
            "id": "123",
            "sync_id": "abc",
            "name": "Remote",
            "updated_at": "2024-01-01T12:00:10Z"
        }
        
        resolution = resolver.resolve(local, remote)
        
        assert resolution.winner == remote
        assert resolution.loser == local
        assert resolution.reason == "remote has newer timestamp"
        assert resolution.timestamp_diff_ms == 10000
    
    async def test_local_wins_newer_timestamp(self):
        """Test local wins with newer timestamp."""
        resolver = ConflictResolver()
        
        local = {
            "id": "123",
            "sync_id": "abc",
            "name": "Local",
            "updated_at": "2024-01-01T12:00:10Z"
        }
        
        remote = {
            "id": "123",
            "sync_id": "abc",
            "name": "Remote",
            "updated_at": "2024-01-01T12:00:00Z"
        }
        
        resolution = resolver.resolve(local, remote)
        
        assert resolution.winner == local
        assert resolution.loser == remote
        assert resolution.reason == "local has newer timestamp"
        assert resolution.timestamp_diff_ms == -10000
    
    async def test_sync_id_tiebreaker(self):
        """Test sync_id used as tiebreaker for equal timestamps."""
        resolver = ConflictResolver()
        
        local = {
            "id": "123",
            "sync_id": "aaa",
            "name": "Local",
            "updated_at": "2024-01-01T12:00:00Z"
        }
        
        remote = {
            "id": "123",
            "sync_id": "bbb",
            "name": "Remote",
            "updated_at": "2024-01-01T12:00:00Z"
        }
        
        resolution = resolver.resolve(local, remote)
        
        assert resolution.winner == remote
        assert resolution.loser == local
        assert "sync_id" in resolution.reason


@pytest.mark.unit
@pytest.mark.asyncio
class TestHouseRepository:
    """Test House repository operations."""
    
    async def test_create_house(self, async_session: AsyncSession):
        """Test creating a house."""
        repo = HouseRepository()
        
        house = await repo.create(
            async_session,
            name="Test House",
            address="123 Test St",
            timezone="UTC"
        )
        
        assert house.id is not None
        assert house.sync_id is not None
        assert house.name == "Test House"
        assert house.version == "1"
        assert house.is_deleted is False
    
    async def test_get_by_id(self, async_session: AsyncSession):
        """Test getting house by ID."""
        repo = HouseRepository()
        
        # Create house
        house = await repo.create(async_session, name="Test House")
        
        # Get by ID
        retrieved = await repo.get_by_id(async_session, house.id)
        
        assert retrieved is not None
        assert retrieved.id == house.id
        assert retrieved.name == "Test House"
    
    async def test_get_by_sync_id(self, async_session: AsyncSession):
        """Test getting house by sync ID."""
        repo = HouseRepository()
        
        # Create house
        house = await repo.create(async_session, name="Test House")
        
        # Get by sync ID
        retrieved = await repo.get_by_sync_id(async_session, house.sync_id)
        
        assert retrieved is not None
        assert retrieved.sync_id == house.sync_id
        assert retrieved.name == "Test House"
    
    async def test_update_house(self, async_session: AsyncSession):
        """Test updating a house."""
        repo = HouseRepository()
        
        # Create and update
        house = await repo.create(async_session, name="Old Name")
        updated = await repo.update(
            async_session,
            house.id,
            name="New Name",
            address="456 New St"
        )
        
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.address == "456 New St"
        assert updated.version == "2"
    
    async def test_soft_delete(self, async_session: AsyncSession):
        """Test soft deleting a house."""
        repo = HouseRepository()
        
        # Create and delete
        house = await repo.create(async_session, name="To Delete")
        success = await repo.soft_delete(async_session, house.id)
        
        assert success is True
        
        # Should not find deleted house
        deleted = await repo.get_by_id(async_session, house.id)
        assert deleted is None
    
    async def test_get_all(self, async_session: AsyncSession):
        """Test getting all houses."""
        repo = HouseRepository()
        
        # Create multiple houses
        await repo.create(async_session, name="House 1")
        await repo.create(async_session, name="House 2")
        await repo.create(async_session, name="House 3")
        
        # Get all
        houses = await repo.get_all(async_session)
        
        assert len(houses) >= 3
        names = [h.name for h in houses]
        assert "House 1" in names
        assert "House 2" in names
        assert "House 3" in names


@pytest.mark.unit
@pytest.mark.asyncio
class TestRoomRepository:
    """Test Room repository operations."""
    
    async def test_create_room_with_house_name(self, async_session: AsyncSession):
        """Test creating a room with denormalized house name."""
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
        
        assert room.house_id == house.id
        assert room.house_name == "Test House"
        assert room.name == "Living Room"
        assert room.room_type == "living_room"
        assert room.floor == 1
    
    async def test_get_by_house(self, async_session: AsyncSession):
        """Test getting rooms by house."""
        house_repo = HouseRepository()
        room_repo = RoomRepository()
        
        # Create house and rooms
        house = await house_repo.create(async_session, name="Test House")
        
        await room_repo.create_with_house_name(
            async_session, house.id, house.name, name="Room 1"
        )
        await room_repo.create_with_house_name(
            async_session, house.id, house.name, name="Room 2"
        )
        
        # Get rooms
        rooms = await room_repo.get_by_house(async_session, house.id)
        
        assert len(rooms) == 2
        names = [r.name for r in rooms]
        assert "Room 1" in names
        assert "Room 2" in names


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeviceRepository:
    """Test Device repository operations."""
    
    async def test_create_device_with_names(self, async_session: AsyncSession):
        """Test creating a device with denormalized names."""
        house_repo = HouseRepository()
        room_repo = RoomRepository()
        device_repo = DeviceRepository()
        
        # Create house and room
        house = await house_repo.create(async_session, name="Test House")
        room = await room_repo.create_with_house_name(
            async_session, house.id, house.name, name="Living Room"
        )
        
        # Create device
        device = await device_repo.create_with_names(
            async_session,
            room_id=room.id,
            room_name=room.name,
            house_id=house.id,
            house_name=house.name,
            name="Smart Light",
            device_type="light"
        )
        
        assert device.room_id == room.id
        assert device.room_name == "Living Room"
        assert device.house_id == house.id
        assert device.house_name == "Test House"
        assert device.name == "Smart Light"
    
    async def test_update_device_state(self, async_session: AsyncSession):
        """Test updating device state."""
        house_repo = HouseRepository()
        room_repo = RoomRepository()
        device_repo = DeviceRepository()
        
        # Setup
        house = await house_repo.create(async_session, name="Test House")
        room = await room_repo.create_with_house_name(
            async_session, house.id, house.name, name="Living Room"
        )
        device = await device_repo.create_with_names(
            async_session,
            room_id=room.id,
            room_name=room.name,
            house_id=house.id,
            house_name=house.name,
            name="Smart Light",
            device_type="light"
        )
        
        # Update state
        state = await device_repo.update_state(
            async_session,
            device_id=device.id,
            state_type="on_off",
            state_value="on",
            state_json={"brightness": 80},
            user_id="user-123"
        )
        
        assert state is not None
        assert state.device_id == device.id
        assert state.state_type == "on_off"
        assert state.state_value == "on"
        assert state.user_id == "user-123"


@pytest.mark.unit
@pytest.mark.asyncio
class TestUserRepository:
    """Test User repository operations."""
    
    async def test_get_by_email(self, async_session: AsyncSession):
        """Test getting user by email."""
        house_repo = HouseRepository()
        user_repo = UserRepository()
        
        # Create house and user
        house = await house_repo.create(async_session, name="Test House")
        user = await user_repo.create(
            async_session,
            house_id=house.id,
            name="John Doe",
            email="john@example.com",
            role="admin"
        )
        
        # Get by email
        retrieved = await user_repo.get_by_email(async_session, "john@example.com")
        
        assert retrieved is not None
        assert retrieved.id == user.id
        assert retrieved.email == "john@example.com"
    
    async def test_get_admins(self, async_session: AsyncSession):
        """Test getting admin users."""
        house_repo = HouseRepository()
        user_repo = UserRepository()
        
        # Create house and users
        house = await house_repo.create(async_session, name="Test House")
        
        await user_repo.create(
            async_session, house_id=house.id, name="Admin 1", role="admin"
        )
        await user_repo.create(
            async_session, house_id=house.id, name="Admin 2", role="admin"
        )
        await user_repo.create(
            async_session, house_id=house.id, name="Member", role="member"
        )
        
        # Get admins
        admins = await user_repo.get_admins(async_session, house.id)
        
        assert len(admins) == 2
        for admin in admins:
            assert admin.role == "admin"