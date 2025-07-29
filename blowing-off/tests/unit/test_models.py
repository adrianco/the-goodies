"""Unit tests for Blowing-Off models."""

import pytest
from datetime import datetime, UTC

from blowingoff.models import ClientHouse, ClientRoom, ClientDevice, SyncStatus
from blowingoff.models.base import ClientTimestampMixin


class TestModels:
    """Test model functionality."""
    
    def test_client_house_creation(self):
        """Test creating a client house."""
        house = ClientHouse(
            id="house-1",
            name="Test House",
            address="123 Test St",
            timezone="UTC"
        )
        
        assert house.id == "house-1"
        assert house.name == "Test House"
        assert house.address == "123 Test St"
        assert house.timezone == "UTC"
        # sync_status is set by SQLAlchemy when persisted
        assert house.sync_status is None or house.sync_status == SyncStatus.PENDING
        
    def test_client_room_creation(self):
        """Test creating a client room."""
        room = ClientRoom(
            id="room-1",
            house_id="house-1",
            name="Living Room",
            floor=1,
            room_type="living_room"
        )
        
        assert room.id == "room-1"
        assert room.house_id == "house-1"
        assert room.name == "Living Room"
        assert room.floor == 1
        assert room.room_type == "living_room"
        # sync_status is set by SQLAlchemy when persisted
        assert room.sync_status is None or room.sync_status == SyncStatus.PENDING
        
    def test_sync_status_transitions(self):
        """Test sync status transitions."""
        house = ClientHouse(
            id="house-1",
            name="Test House"
        )
        
        # Default status - set it manually for testing
        house.sync_status = SyncStatus.PENDING
        assert house.sync_status == SyncStatus.PENDING
        
        # Mark as synced
        house.sync_id = "sync-123"
        house.mark_synced(datetime.now(UTC))
        assert house.sync_status == SyncStatus.SYNCED
        assert house.sync_id == "sync-123"
        assert house.sync_error is None
        
        # Mark as conflict
        house.mark_conflict("Version mismatch")
        assert house.sync_status == SyncStatus.CONFLICT
        assert house.sync_error == "Version mismatch"
        
        # Mark as error
        house.mark_error("Network error")
        assert house.sync_status == SyncStatus.ERROR
        assert house.sync_error == "Network error"
        
    def test_to_sync_dict(self):
        """Test converting model to sync dictionary."""
        now = datetime.now(UTC)
        house = ClientHouse(
            id="house-1",
            name="Test House",
            address="123 Test St",
            timezone="UTC",
            metadata_json='{"custom": "data"}'
        )
        house.updated_at = now
        house.sync_id = "sync-123"
        
        sync_dict = house.to_sync_dict()
        
        assert sync_dict["id"] == "house-1"
        assert sync_dict["name"] == "Test House"
        assert sync_dict["address"] == "123 Test St"
        assert sync_dict["timezone"] == "UTC"
        assert sync_dict["metadata"] == '{"custom": "data"}'
        assert sync_dict["sync_id"] == "sync-123"
        assert sync_dict["updated_at"] == now.isoformat()