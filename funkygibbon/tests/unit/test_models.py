"""
Unit tests for data models.
"""

import json
from datetime import datetime, UTC

import pytest

from inbetweenies.models import Home, Room, Accessory, User
from inbetweenies.sync.conflict import ConflictResolution


@pytest.mark.unit
class TestHomeModel:
    """Test Home model functionality."""
    
    def test_home_creation(self):
        """Test creating a home instance."""
        home = Home(
            id="test-home-id",
            name="Test Home",
            is_primary=True
        )
        
        assert home.id == "test-home-id"
        assert home.name == "Test Home"
        assert home.is_primary == True
    
    def test_home_to_dict(self):
        """Test converting home to dictionary."""
        home = Home(
            id="test-id",
            name="Test Home",
            is_primary=False,
            sync_id="sync-id"
        )
        home.created_at = datetime.now(UTC)
        home.updated_at = datetime.now(UTC)
        
        result = home.to_dict()
        
        assert result["id"] == "test-id"
        assert result["sync_id"] == "sync-id"
        assert result["name"] == "Test Home"
        assert result["is_primary"] == False
        assert "created_at" in result
        assert "updated_at" in result


@pytest.mark.unit
class TestRoomModel:
    """Test Room model functionality."""
    
    def test_room_creation(self):
        """Test creating a room instance."""
        room = Room(
            id="room-123",
            home_id="home-123",
            name="Living Room"
        )
        
        assert room.id == "room-123"
        assert room.home_id == "home-123"
        assert room.name == "Living Room"
    
    def test_room_to_dict(self):
        """Test room to dictionary conversion."""
        room = Room(
            id="room-123",
            home_id="home-123",
            name="Bedroom",
            sync_id="sync-room-123"
        )
        room.created_at = datetime.now(UTC)
        room.updated_at = datetime.now(UTC)
        
        result = room.to_dict()
        
        assert result["id"] == "room-123"
        assert result["home_id"] == "home-123"
        assert result["name"] == "Bedroom"
        assert result["sync_id"] == "sync-room-123"
        assert "created_at" in result
        assert "updated_at" in result


@pytest.mark.unit
class TestAccessoryModel:
    """Test Accessory model functionality."""
    
    def test_accessory_creation(self):
        """Test creating an accessory instance."""
        accessory = Accessory(
            id="accessory-123",
            home_id="home-123",
            name="Smart Light",
            manufacturer="Philips",
            model="Hue Go",
            serial_number="123456789",
            firmware_version="1.0.0",
            is_reachable=True,
            is_blocked=False,
            is_bridge=False
        )
        
        assert accessory.id == "accessory-123"
        assert accessory.home_id == "home-123"
        assert accessory.name == "Smart Light"
        assert accessory.manufacturer == "Philips"
        assert accessory.model == "Hue Go"
        assert accessory.serial_number == "123456789"
        assert accessory.firmware_version == "1.0.0"
        assert accessory.is_reachable == True
        assert accessory.is_blocked == False
        assert accessory.is_bridge == False
    
    def test_accessory_to_dict(self):
        """Test accessory to dictionary conversion."""
        accessory = Accessory(
            id="accessory-123",
            home_id="home-123",
            name="Smart Light",
            manufacturer="Philips",
            model="Hue Go",
            sync_id="sync-acc-123"
        )
        accessory.created_at = datetime.now(UTC)
        accessory.updated_at = datetime.now(UTC)
        
        result = accessory.to_dict()
        
        assert result["id"] == "accessory-123"
        assert result["home_id"] == "home-123"
        assert result["name"] == "Smart Light"
        assert result["manufacturer"] == "Philips"
        assert result["model"] == "Hue Go"
        assert result["sync_id"] == "sync-acc-123"


@pytest.mark.unit
class TestUserModel:
    """Test User model functionality."""
    
    def test_user_creation(self):
        """Test creating a user instance."""
        user = User(
            id="user-123",
            home_id="home-123",
            name="John Doe",
            is_administrator=True,
            is_owner=False,
            remote_access_allowed=True
        )
        
        assert user.id == "user-123"
        assert user.home_id == "home-123"
        assert user.name == "John Doe"
        assert user.is_administrator == True
        assert user.is_owner == False
        assert user.remote_access_allowed == True
    
    def test_user_to_dict(self):
        """Test user to dictionary conversion."""
        user = User(
            id="user-123",
            home_id="home-123",
            name="Jane Doe",
            is_administrator=False,
            is_owner=True,
            remote_access_allowed=True,
            sync_id="sync-user-123"
        )
        user.created_at = datetime.now(UTC)
        user.updated_at = datetime.now(UTC)
        
        result = user.to_dict()
        
        assert result["id"] == "user-123"
        assert result["home_id"] == "home-123"
        assert result["name"] == "Jane Doe"
        assert result["is_administrator"] == False
        assert result["is_owner"] == True
        assert result["remote_access_allowed"] == True
        assert result["sync_id"] == "sync-user-123"


@pytest.mark.unit
class TestConflictResolution:
    """Test conflict resolution model."""
    
    def test_conflict_resolution_creation(self):
        """Test creating a conflict resolution instance."""
        winner = {"id": "123", "name": "Winner", "updated_at": "2025-07-28T12:00:10Z"}
        loser = {"id": "123", "name": "Loser", "updated_at": "2025-07-28T12:00:00Z"}
        
        resolution = ConflictResolution(
            winner=winner,
            loser=loser,
            reason="winner has newer timestamp",
            timestamp_diff_ms=10000
        )
        
        assert resolution.winner == winner
        assert resolution.loser == loser
        assert resolution.reason == "winner has newer timestamp"
        assert resolution.timestamp_diff_ms == 10000