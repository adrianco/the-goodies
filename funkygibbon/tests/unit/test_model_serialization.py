"""
Test model serialization methods to catch lazy loading issues.

These tests ensure that to_dict() methods work correctly without
triggering lazy loads in async contexts.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inbetweenies.models import Home, Room, Accessory, User
from funkygibbon.repositories import (
    HomeRepository,
    RoomRepository, 
    AccessoryRepository,
    UserRepository
)


@pytest.mark.asyncio
class TestModelSerialization:
    """Test model to_dict() methods for lazy loading issues."""
    
    async def test_accessory_to_dict_without_relationships(self, async_session: AsyncSession):
        """Test Accessory.to_dict() doesn't trigger lazy loading."""
        # Create test data
        home_repo = HomeRepository()
        room_repo = RoomRepository()
        accessory_repo = AccessoryRepository()
        
        # Create home
        home = await home_repo.create(
            async_session,
            name="Test Home",
            is_primary=True
        )
        
        # Create rooms
        room1 = await room_repo.create(
            async_session,
            home_id=home.id,
            name="Room 1"
        )
        room2 = await room_repo.create(
            async_session,
            home_id=home.id,
            name="Room 2"
        )
        
        # Create accessory without room associations
        # (room associations need to be added separately via the API)
        accessory = await accessory_repo.create(
            async_session,
            home_id=home.id,
            name="Test Light",
            manufacturer="Test Corp",
            model="Light v1"
        )
        
        await async_session.commit()
        
        # Store the id before expiring
        accessory_id = accessory.id
        
        # Clear the session to ensure no cached relationships
        async_session.expire_all()
        
        # Get accessory without loading relationships
        fresh_accessory = await accessory_repo.get_by_id(async_session, accessory_id)
        
        # This should NOT trigger lazy loading
        try:
            accessory_dict = fresh_accessory.to_dict()
            
            # Verify basic fields are present
            assert accessory_dict["id"] == accessory_id
            assert accessory_dict["name"] == "Test Light"
            assert accessory_dict["manufacturer"] == "Test Corp"
            assert accessory_dict["model"] == "Light v1"
            
            # room_ids should not be in the dict to avoid lazy loading
            assert "room_ids" not in accessory_dict
            
        except Exception as e:
            pytest.fail(f"to_dict() triggered lazy loading: {e}")
    
    async def test_home_to_dict_safe(self, async_session: AsyncSession):
        """Test Home.to_dict() doesn't access relationships."""
        home_repo = HomeRepository()
        room_repo = RoomRepository()
        
        # Create home with rooms
        home = await home_repo.create(
            async_session,
            name="Test Home",
            is_primary=True
        )
        
        await room_repo.create(
            async_session,
            home_id=home.id,
            name="Room 1"
        )
        
        await async_session.commit()
        
        # Store the id before expiring
        home_id = home.id
        
        async_session.expire_all()
        
        # Get home without relationships
        fresh_home = await home_repo.get_by_id(async_session, home_id)
        
        # Should not trigger lazy loading
        home_dict = fresh_home.to_dict()
        
        assert home_dict["id"] == home_id
        assert home_dict["name"] == "Test Home"
        assert "rooms" not in home_dict
        assert "accessories" not in home_dict
        assert "users" not in home_dict
    
    async def test_room_to_dict_safe(self, async_session: AsyncSession):
        """Test Room.to_dict() doesn't access relationships."""
        home_repo = HomeRepository()
        room_repo = RoomRepository()
        accessory_repo = AccessoryRepository()
        
        # Create test data
        home = await home_repo.create(
            async_session,
            name="Test Home"
        )
        
        room = await room_repo.create(
            async_session,
            home_id=home.id,
            name="Test Room"
        )
        
        await accessory_repo.create(
            async_session,
            home_id=home.id,
            name="Test Device"
        )
        
        await async_session.commit()
        
        # Store the id before expiring
        room_id = room.id
        
        async_session.expire_all()
        
        # Get room without relationships
        fresh_room = await room_repo.get_by_id(async_session, room_id)
        
        # Should not trigger lazy loading
        room_dict = fresh_room.to_dict()
        
        assert room_dict["id"] == room_id
        assert room_dict["name"] == "Test Room"
        assert "home" not in room_dict
        assert "accessories" not in room_dict
    
    async def test_user_to_dict_safe(self, async_session: AsyncSession):
        """Test User.to_dict() doesn't access relationships."""
        home_repo = HomeRepository()
        user_repo = UserRepository()
        
        # Create test data
        home = await home_repo.create(
            async_session,
            name="Test Home"
        )
        
        user = await user_repo.create(
            async_session,
            home_id=home.id,
            name="Test User",
            is_administrator=True
        )
        
        await async_session.commit()
        
        # Store the id before expiring
        user_id = user.id
        
        async_session.expire_all()
        
        # Get user without relationships
        fresh_user = await user_repo.get_by_id(async_session, user_id)
        
        # Should not trigger lazy loading
        user_dict = fresh_user.to_dict()
        
        assert user_dict["id"] == user_id
        assert user_dict["name"] == "Test User"
        assert "home" not in user_dict