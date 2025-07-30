"""Unit tests for Blowing-Off models."""

import pytest
from datetime import datetime, UTC

from blowingoff.models import Home, Room, Accessory, User, SyncMetadata


class TestModels:
    """Test model functionality."""
    
    def test_home_creation(self):
        """Test creating a home."""
        home = Home(
            id="home-1",
            name="Test Home",
            is_primary=True
        )
        
        assert home.id == "home-1"
        assert home.name == "Test Home"
        assert home.is_primary == True
        
    def test_room_creation(self):
        """Test creating a room."""
        room = Room(
            id="room-1",
            home_id="home-1",
            name="Living Room"
        )
        
        assert room.id == "room-1"
        assert room.home_id == "home-1"
        assert room.name == "Living Room"
        
    def test_sync_metadata(self):
        """Test sync metadata."""
        metadata = SyncMetadata(
            client_id="client-1",
            last_sync_time=datetime.now(UTC),
            server_url="http://localhost:8000"
        )
        
        assert metadata.client_id == "client-1"
        assert metadata.last_sync_time is not None
        assert metadata.server_url == "http://localhost:8000"
        assert metadata.sync_failures == 0
        assert metadata.total_syncs == 0
        
    def test_to_dict(self):
        """Test converting model to dictionary."""
        now = datetime.now(UTC)
        home = Home(
            id="home-1",
            name="Test Home",
            is_primary=True
        )
        home.updated_at = now
        home.sync_id = "sync-123"
        
        home_dict = home.to_dict()
        
        assert home_dict["id"] == "home-1"
        assert home_dict["name"] == "Test Home"
        assert home_dict["is_primary"] == True
        assert home_dict["sync_id"] == "sync-123"
        assert home_dict["updated_at"] == now.isoformat()