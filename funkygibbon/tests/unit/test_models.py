"""
Unit tests for data models.
"""

import json
from datetime import datetime, UTC

import pytest

from funkygibbon.models import House, Room, Device, User, EntityState, Event
from funkygibbon.models.base import ConflictResolution


@pytest.mark.unit
class TestHouseModel:
    """Test House model functionality."""
    
    def test_house_creation(self):
        """Test creating a house instance."""
        house = House(
            name="Test House",
            address="123 Test St",
            latitude=40.7128,
            longitude=-74.0060,
            timezone="America/New_York",
            room_count=0,
            device_count=0,
            user_count=0
        )
        
        assert house.name == "Test House"
        assert house.address == "123 Test St"
        assert house.latitude == 40.7128
        assert house.longitude == -74.0060
        assert house.timezone == "America/New_York"
        assert house.room_count == 0
        assert house.device_count == 0
        assert house.user_count == 0
    
    def test_house_to_dict(self):
        """Test converting house to dictionary."""
        house = House(
            id="test-id",
            sync_id="sync-id",
            name="Test House",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            room_count=0,
            device_count=0,
            user_count=0,
            version="1",
            is_deleted=False
        )
        
        result = house.to_dict()
        
        assert result["id"] == "test-id"
        assert result["sync_id"] == "sync-id"
        assert result["name"] == "Test House"
        assert "created_at" in result
        assert "updated_at" in result
        assert result["version"] == "1"
        assert result["is_deleted"] is False


@pytest.mark.unit
class TestRoomModel:
    """Test Room model functionality."""
    
    def test_room_creation(self):
        """Test creating a room instance."""
        room = Room(
            house_id="house-123",
            house_name="Test House",
            name="Living Room",
            room_type="living_room",
            floor=1,
            temperature=22.5,
            humidity=45.0,
            device_count=0
        )
        
        assert room.house_id == "house-123"
        assert room.house_name == "Test House"
        assert room.name == "Living Room"
        assert room.room_type == "living_room"
        assert room.floor == 1
        assert room.temperature == 22.5
        assert room.humidity == 45.0
        assert room.device_count == 0
    
    def test_room_sensor_data(self):
        """Test room sensor data fields."""
        room = Room(
            house_id="house-123",
            house_name="Test House",
            name="Bedroom",
            last_motion_at="2024-01-01T12:00:00Z"
        )
        
        assert room.last_motion_at == "2024-01-01T12:00:00Z"
        assert room.temperature is None
        assert room.humidity is None


@pytest.mark.unit
class TestDeviceModel:
    """Test Device model functionality."""
    
    def test_device_creation(self):
        """Test creating a device instance."""
        device = Device(
            room_id="room-123",
            house_id="house-123",
            room_name="Living Room",
            house_name="Test House",
            name="Smart Light",
            device_type="light",
            manufacturer="Philips",
            model="Hue Go"
        )
        
        assert device.room_id == "room-123"
        assert device.house_id == "house-123"
        assert device.room_name == "Living Room"
        assert device.house_name == "Test House"
        assert device.name == "Smart Light"
        assert device.device_type == "light"
        assert device.manufacturer == "Philips"
        assert device.model == "Hue Go"
    
    def test_device_json_fields(self):
        """Test device JSON storage fields."""
        state_data = {"on": True, "brightness": 80, "color": "warm"}
        capabilities = ["on_off", "dimming", "color"]
        
        device = Device(
            room_id="room-123",
            house_id="house-123",
            room_name="Living Room",
            house_name="Test House",
            name="Smart Light",
            device_type="light",
            state_json=json.dumps(state_data),
            capabilities_json=json.dumps(capabilities)
        )
        
        assert device.state_json == json.dumps(state_data)
        assert device.capabilities_json == json.dumps(capabilities)
        
        # Test parsing JSON
        parsed_state = json.loads(device.state_json)
        assert parsed_state["on"] is True
        assert parsed_state["brightness"] == 80


@pytest.mark.unit
class TestUserModel:
    """Test User model functionality."""
    
    def test_user_creation(self):
        """Test creating a user instance."""
        user = User(
            house_id="house-123",
            name="John Doe",
            email="john@example.com",
            role="admin"
        )
        
        assert user.house_id == "house-123"
        assert user.name == "John Doe"
        assert user.email == "john@example.com"
        assert user.role == "admin"
    
    def test_user_device_tracking(self):
        """Test user device ID tracking."""
        device_ids = ["device-1", "device-2", "device-3"]
        user = User(
            house_id="house-123",
            name="Jane Doe",
            device_ids_json=json.dumps(device_ids)
        )
        
        parsed_devices = json.loads(user.device_ids_json)
        assert len(parsed_devices) == 3
        assert "device-1" in parsed_devices


@pytest.mark.unit
class TestEntityStateModel:
    """Test EntityState model functionality."""
    
    def test_entity_state_creation(self):
        """Test creating an entity state instance."""
        state = EntityState(
            device_id="device-123",
            state_type="temperature",
            state_value="22.5",
            source="sensor",
            user_id=None
        )
        
        assert state.device_id == "device-123"
        assert state.state_type == "temperature"
        assert state.state_value == "22.5"
        assert state.source == "sensor"
        assert state.user_id is None
    
    def test_entity_state_with_json(self):
        """Test entity state with JSON data."""
        extra_data = {"unit": "celsius", "precision": 0.1}
        state = EntityState(
            device_id="device-123",
            state_type="temperature",
            state_value="22.5",
            state_json=json.dumps(extra_data)
        )
        
        parsed_data = json.loads(state.state_json)
        assert parsed_data["unit"] == "celsius"
        assert parsed_data["precision"] == 0.1


@pytest.mark.unit
class TestEventModel:
    """Test Event model functionality."""
    
    def test_event_creation(self):
        """Test creating an event instance."""
        event = Event(
            event_type="device_added",
            entity_type="device",
            entity_id="device-123",
            description="Smart Light added to Living Room",
            source="user",
            user_id="user-456"
        )
        
        assert event.event_type == "device_added"
        assert event.entity_type == "device"
        assert event.entity_id == "device-123"
        assert event.description == "Smart Light added to Living Room"
        assert event.source == "user"
        assert event.user_id == "user-456"
    
    def test_event_with_data(self):
        """Test event with JSON data."""
        event_data = {
            "old_name": "Light 1",
            "new_name": "Living Room Light",
            "changed_by": "user-456"
        }
        
        event = Event(
            event_type="device_renamed",
            entity_type="device",
            entity_id="device-123",
            data_json=json.dumps(event_data)
        )
        
        parsed_data = json.loads(event.data_json)
        assert parsed_data["old_name"] == "Light 1"
        assert parsed_data["new_name"] == "Living Room Light"


@pytest.mark.unit
class TestConflictResolution:
    """Test conflict resolution model."""
    
    def test_conflict_resolution_creation(self):
        """Test creating a conflict resolution instance."""
        winner = {"id": "123", "name": "Winner", "updated_at": "2024-01-01T12:00:10Z"}
        loser = {"id": "123", "name": "Loser", "updated_at": "2024-01-01T12:00:00Z"}
        
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