"""
Unit tests for repository layer.

REVISION HISTORY:
- 2025-07-28: Fixed fixture name from db_session to async_session for proper test execution
"""

import asyncio
from datetime import datetime, timedelta, UTC

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inbetweenies.models import Home, Room, Accessory, User
from funkygibbon.repositories import (
    HomeRepository,
    RoomRepository,
    AccessoryRepository,
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
            "updated_at": "2025-07-28T12:00:00Z"
        }
        
        remote = {
            "id": "123",
            "sync_id": "abc",
            "name": "Remote",
            "updated_at": "2025-07-28T12:00:10Z"
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
            "updated_at": "2025-07-28T12:00:10Z"
        }
        
        remote = {
            "id": "123",
            "sync_id": "abc",
            "name": "Remote",
            "updated_at": "2025-07-28T12:00:00Z"
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
            "updated_at": "2025-07-28T12:00:00Z"
        }
        
        remote = {
            "id": "123",
            "sync_id": "bbb",
            "name": "Remote",
            "updated_at": "2025-07-28T12:00:00Z"
        }
        
        resolution = resolver.resolve(local, remote)
        
        assert resolution.winner == remote
        assert resolution.loser == local
        assert "sync_id" in resolution.reason


@pytest.mark.unit
@pytest.mark.asyncio
class TestHomeRepository:
    """Test Home repository operations."""
    
    async def test_create_home(self, async_session: AsyncSession):
        """Test creating a home."""
        repo = HomeRepository()
        
        home = await repo.create(
            async_session,
            name="Test Home",
            is_primary=True
        )
        
        assert home.id is not None
        assert home.sync_id is not None
        assert home.name == "Test Home"
        # No version or is_deleted in simplified models
    
    async def test_get_by_id(self, async_session: AsyncSession):
        """Test getting home by ID."""
        repo = HomeRepository()
        
        # Create home
        home = await repo.create(async_session, name="Test Home")
        
        # Get by ID
        retrieved = await repo.get_by_id(async_session, home.id)
        
        assert retrieved is not None
        assert retrieved.id == home.id
        assert retrieved.name == "Test Home"
    
    async def test_get_by_sync_id(self, async_session: AsyncSession):
        """Test getting home by sync ID."""
        repo = HomeRepository()
        
        # Create home
        home = await repo.create(async_session, name="Test Home")
        
        # Get by sync ID
        retrieved = await repo.get_by_sync_id(async_session, home.sync_id)
        
        assert retrieved is not None
        assert retrieved.sync_id == home.sync_id
        assert retrieved.name == "Test Home"
    
    async def test_update_home(self, async_session: AsyncSession):
        """Test updating a home."""
        repo = HomeRepository()
        
        # Create and update
        home = await repo.create(async_session, name="Old Name")
        updated = await repo.update(
            async_session,
            home.id,
            name="New Name",
            is_primary=False
        )
        
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.is_primary == False
        # No version tracking in simplified models
    
    async def test_soft_delete(self, async_session: AsyncSession):
        """Test soft deleting a home."""
        repo = HomeRepository()
        
        # Create and delete
        home = await repo.create(async_session, name="To Delete")
        success = await repo.soft_delete(async_session, home.id)
        
        assert success is True
        
        # Should not find deleted home
        deleted = await repo.get_by_id(async_session, home.id)
        assert deleted is None
    
    async def test_get_all(self, async_session: AsyncSession):
        """Test getting all homes."""
        repo = HomeRepository()
        
        # Create multiple homes
        await repo.create(async_session, name="Home 1")
        await repo.create(async_session, name="Home 2")
        await repo.create(async_session, name="Home 3")
        
        # Get all
        homes = await repo.get_all(async_session)
        
        assert len(homes) >= 3
        names = [h.name for h in homes]
        assert "Home 1" in names
        assert "Home 2" in names
        assert "Home 3" in names


@pytest.mark.unit
@pytest.mark.asyncio
class TestRoomRepository:
    """Test Room repository operations."""
    
    async def test_create_room_with_home_name(self, async_session: AsyncSession):
        """Test creating a room with denormalized home name."""
        home_repo = HomeRepository()
        room_repo = RoomRepository()
        
        # Create home
        home = await home_repo.create(async_session, name="Test Home")
        
        # Create room
        room = await room_repo.create_with_home_name(
            async_session,
            home_id=home.id,
            home_name=home.name,
            name="Living Room"
        )
        
        assert room.home_id == home.id
        assert room.name == "Living Room"
    
    async def test_get_by_home(self, async_session: AsyncSession):
        """Test getting rooms by home."""
        home_repo = HomeRepository()
        room_repo = RoomRepository()
        
        # Create home and rooms
        home = await home_repo.create(async_session, name="Test Home")
        
        await room_repo.create_with_home_name(
            async_session, home.id, home.name, name="Room 1"
        )
        await room_repo.create_with_home_name(
            async_session, home.id, home.name, name="Room 2"
        )
        
        # Get rooms
        rooms = await room_repo.get_by_home(async_session, home.id)
        
        assert len(rooms) == 2
        names = [r.name for r in rooms]
        assert "Room 1" in names
        assert "Room 2" in names


@pytest.mark.unit
@pytest.mark.asyncio
class TestAccessoryRepository:
    """Test Accessory repository operations."""
    
    async def test_create_accessory(self, async_session: AsyncSession):
        """Test creating an accessory."""
        home_repo = HomeRepository()
        room_repo = RoomRepository()
        accessory_repo = AccessoryRepository()
        
        # Create home and room
        home = await home_repo.create(async_session, name="Test Home")
        room = await room_repo.create_with_home_name(
            async_session, home.id, home.name, name="Living Room"
        )
        
        # Create accessory
        accessory = await accessory_repo.create(
            async_session,
            home_id=home.id,
            name="Smart Light",
            manufacturer="Test Corp",
            model="Light v1"
        )
        
        assert accessory.home_id == home.id
        assert accessory.name == "Smart Light"
        assert accessory.manufacturer == "Test Corp"
        assert accessory.model == "Light v1"
    
    async def test_update_reachability(self, async_session: AsyncSession):
        """Test updating accessory reachability."""
        home_repo = HomeRepository()
        accessory_repo = AccessoryRepository()
        
        # Setup
        home = await home_repo.create(async_session, name="Test Home")
        accessory = await accessory_repo.create(
            async_session,
            home_id=home.id,
            name="Smart Light",
            is_reachable=True
        )
        
        # Update reachability
        updated = await accessory_repo.update_reachability(
            async_session,
            accessory.id,
            is_reachable=False
        )
        
        assert updated is not None
        assert updated.is_reachable == False


@pytest.mark.unit
@pytest.mark.asyncio
class TestUserRepository:
    """Test User repository operations."""
    
    async def test_get_by_name(self, async_session: AsyncSession):
        """Test getting user by name."""
        home_repo = HomeRepository()
        user_repo = UserRepository()
        
        # Create home and user
        home = await home_repo.create(async_session, name="Test Home")
        user = await user_repo.create(
            async_session,
            home_id=home.id,
            name="John Doe",
            is_administrator=True
        )
        
        # Get by name
        retrieved = await user_repo.get_by_name(async_session, "John Doe")
        
        assert retrieved is not None
        assert retrieved.id == user.id
        assert retrieved.name == "John Doe"
    
    async def test_get_admins(self, async_session: AsyncSession):
        """Test getting admin users."""
        home_repo = HomeRepository()
        user_repo = UserRepository()
        
        # Create home and users
        home = await home_repo.create(async_session, name="Test Home")
        
        await user_repo.create(
            async_session, home_id=home.id, name="Admin 1", is_administrator=True
        )
        await user_repo.create(
            async_session, home_id=home.id, name="Admin 2", is_administrator=True
        )
        await user_repo.create(
            async_session, home_id=home.id, name="Member", is_administrator=False
        )
        
        # Get admins
        admins = await user_repo.get_admins(async_session, home.id)
        
        assert len(admins) == 2
        for admin in admins:
            assert admin.is_administrator == True