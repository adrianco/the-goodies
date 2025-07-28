"""
Integration tests for API endpoints.
"""

import json
from datetime import datetime, UTC

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.api.app import create_app
from funkygibbon.repositories import HouseRepository, RoomRepository, DeviceRepository


@pytest.mark.integration
@pytest.mark.asyncio
class TestHouseAPI:
    """Test house API endpoints."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app()
    
    async def test_create_house(self, app, async_client: AsyncClient):
        """Test creating a house via API."""
        response = await async_client.post(
            "/api/v1/houses/",
            params={
                "name": "API Test House",
                "address": "123 API St",
                "timezone": "UTC"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Test House"
        assert data["address"] == "123 API St"
        assert data["timezone"] == "UTC"
        assert "id" in data
        assert "sync_id" in data
    
    async def test_get_house(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test getting a house via API."""
        # Create house directly
        repo = HouseRepository()
        house = await repo.create(db_session, name="Get Test House")
        
        # Get via API
        response = await async_client.get(f"/api/v1/houses/{house.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == house.id
        assert data["name"] == "Get Test House"
    
    async def test_list_houses(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test listing houses via API."""
        # Create houses
        repo = HouseRepository()
        await repo.create(db_session, name="House A")
        await repo.create(db_session, name="House B")
        
        # List via API
        response = await async_client.get("/api/v1/houses/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        names = [h["name"] for h in data]
        assert "House A" in names
        assert "House B" in names
    
    async def test_update_house(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test updating a house via API."""
        # Create house
        repo = HouseRepository()
        house = await repo.create(db_session, name="Old Name")
        
        # Update via API
        response = await async_client.put(
            f"/api/v1/houses/{house.id}",
            params={"name": "New Name", "address": "456 New St"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["address"] == "456 New St"
        assert data["version"] == "2"
    
    async def test_delete_house(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test deleting a house via API."""
        # Create house
        repo = HouseRepository()
        house = await repo.create(db_session, name="To Delete")
        
        # Delete via API
        response = await async_client.delete(f"/api/v1/houses/{house.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["id"] == house.id
        
        # Verify it's gone
        response = await async_client.get(f"/api/v1/houses/{house.id}")
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestRoomAPI:
    """Test room API endpoints."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app()
    
    async def test_create_room(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test creating a room via API."""
        # Create house
        house_repo = HouseRepository()
        house = await house_repo.create(db_session, name="Test House")
        
        # Create room via API
        response = await async_client.post(
            "/api/v1/rooms/",
            params={
                "house_id": house.id,
                "name": "API Room",
                "room_type": "bedroom",
                "floor": 2
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Room"
        assert data["room_type"] == "bedroom"
        assert data["floor"] == 2
        assert data["house_id"] == house.id
        assert data["house_name"] == "Test House"
    
    async def test_list_rooms_by_house(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test listing rooms by house."""
        # Create house and rooms
        house_repo = HouseRepository()
        room_repo = RoomRepository()
        
        house = await house_repo.create(db_session, name="Test House")
        await room_repo.create_with_house_name(
            db_session, house.id, house.name, name="Room 1"
        )
        await room_repo.create_with_house_name(
            db_session, house.id, house.name, name="Room 2"
        )
        
        # List via API
        response = await async_client.get(
            "/api/v1/rooms/",
            params={"house_id": house.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [r["name"] for r in data]
        assert "Room 1" in names
        assert "Room 2" in names


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeviceAPI:
    """Test device API endpoints."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app()
    
    async def test_create_device(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test creating a device via API."""
        # Create house and room
        house_repo = HouseRepository()
        room_repo = RoomRepository()
        
        house = await house_repo.create(db_session, name="Test House")
        room = await room_repo.create_with_house_name(
            db_session, house.id, house.name, name="Test Room"
        )
        
        # Create device via API
        response = await async_client.post(
            "/api/v1/devices/",
            params={
                "room_id": room.id,
                "name": "API Device",
                "device_type": "sensor",
                "manufacturer": "Test Corp",
                "model": "T-1000"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Device"
        assert data["device_type"] == "sensor"
        assert data["manufacturer"] == "Test Corp"
        assert data["model"] == "T-1000"
        assert data["room_name"] == "Test Room"
        assert data["house_name"] == "Test House"
    
    async def test_update_device_state(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test updating device state via API."""
        # Create device
        house_repo = HouseRepository()
        room_repo = RoomRepository()
        device_repo = DeviceRepository()
        
        house = await house_repo.create(db_session, name="Test House")
        room = await room_repo.create_with_house_name(
            db_session, house.id, house.name, name="Test Room"
        )
        device = await device_repo.create_with_names(
            db_session,
            room_id=room.id,
            room_name=room.name,
            house_id=house.id,
            house_name=house.name,
            name="Test Device",
            device_type="light"
        )
        
        # Update state via API
        response = await async_client.put(
            f"/api/v1/devices/{device.id}/state",
            params={
                "state_type": "on_off",
                "state_value": "on"
            },
            json={"brightness": 75, "color": "warm"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == device.id
        assert data["state_type"] == "on_off"
        assert data["state_value"] == "on"
        assert "state_json" in data


@pytest.mark.integration
@pytest.mark.asyncio
class TestSyncAPI:
    """Test sync API endpoints."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app()
    
    async def test_sync_entities(self, app, async_client: AsyncClient):
        """Test syncing entities."""
        sync_request = {
            "houses": [
                {
                    "sync_id": "remote-house-1",
                    "name": "Remote House",
                    "address": "123 Remote St",
                    "timezone": "UTC",
                    "room_count": 0,
                    "device_count": 0,
                    "user_count": 0,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                    "version": "1",
                    "is_deleted": False
                }
            ],
            "rooms": [],
            "devices": [],
            "users": []
        }
        
        response = await async_client.post(
            "/api/v1/sync/",
            json=sync_request
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["synced"]["houses"] == 1
        assert len(data["conflicts"]) == 0
        assert "timestamp" in data
    
    async def test_get_changes_since(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test getting changes since timestamp."""
        # Create some entities
        house_repo = HouseRepository()
        
        # Create houses at different times
        await house_repo.create(db_session, name="Old House")
        await asyncio.sleep(0.1)
        
        checkpoint = datetime.now(UTC) - timedelta(seconds=1)
        await asyncio.sleep(0.1)
        
        await house_repo.create(db_session, name="New House 1")
        await house_repo.create(db_session, name="New House 2")
        
        # Get changes
        response = await async_client.get(
            "/api/v1/sync/changes",
            params={"since": checkpoint.isoformat()}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["changes"]["houses"]) >= 2
        
        house_names = [h["name"] for h in data["changes"]["houses"]]
        assert "New House 1" in house_names
        assert "New House 2" in house_names