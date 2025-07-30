"""
Integration tests for API endpoints.

REVISION HISTORY:
- 2025-07-28: Fixed missing imports (asyncio, timedelta) for test functionality
- 2025-07-28: Fixed sync API tests to handle ISO datetime format strings
"""

import asyncio
import json
from datetime import datetime, timedelta, UTC

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.api.app import create_app
from funkygibbon.repositories import HomeRepository, RoomRepository, AccessoryRepository


@pytest.mark.integration
@pytest.mark.asyncio
class TestHomeAPI:
    """Test home API endpoints."""
    
    async def test_create_home(self, async_client: AsyncClient):
        """Test creating a home via API."""
        response = await async_client.post(
            "/api/v1/homes/",
            params={
                "name": "API Test Home",
                "is_primary": True
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Test Home"
        assert data["is_primary"] == True
        assert "id" in data
        assert "sync_id" in data
    
    async def test_get_home(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test getting a home via API."""
        # Create home directly
        repo = HomeRepository()
        home = await repo.create(test_session, name="Get Test Home")
        
        # Get via API
        response = await async_client.get(f"/api/v1/homes/{home.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == home.id
        assert data["name"] == "Get Test Home"
    
    async def test_list_homes(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test listing homes via API."""
        # Create homes
        repo = HomeRepository()
        await repo.create(test_session, name="House A")
        await repo.create(test_session, name="House B")
        
        # List via API
        response = await async_client.get("/api/v1/homes/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        names = [h["name"] for h in data]
        assert "House A" in names
        assert "House B" in names
    
    async def test_update_home(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test updating a home via API."""
        # Create home
        repo = HomeRepository()
        home = await repo.create(test_session, name="Old Name")
        
        # Update via API
        response = await async_client.put(
            f"/api/v1/homes/{home.id}",
            params={"name": "New Name", "is_primary": False}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["is_primary"] == False
    
    async def test_delete_home(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test deleting a home via API."""
        # Create home
        repo = HomeRepository()
        home = await repo.create(test_session, name="To Delete")
        
        # Delete via API
        response = await async_client.delete(f"/api/v1/homes/{home.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["id"] == home.id
        
        # Verify it's gone
        response = await async_client.get(f"/api/v1/homes/{home.id}")
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestRoomAPI:
    """Test room API endpoints."""
    
    async def test_create_room(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test creating a room via API."""
        # Create home
        home_repo = HomeRepository()
        home = await home_repo.create(test_session, name="Test House")
        
        # Create room via API
        response = await async_client.post(
            "/api/v1/rooms/",
            params={
                "home_id": home.id,
                "name": "API Room"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Room"
        assert data["home_id"] == home.id
    
    async def test_list_rooms_by_home(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test listing rooms by home."""
        # Create home and rooms
        home_repo = HomeRepository()
        room_repo = RoomRepository()
        
        home = await home_repo.create(test_session, name="Test House")
        await room_repo.create_with_home_name(
            test_session, home.id, home.name, name="Room 1"
        )
        await room_repo.create_with_home_name(
            test_session, home.id, home.name, name="Room 2"
        )
        
        # List via API
        response = await async_client.get(
            "/api/v1/rooms/",
            params={"home_id": home.id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [r["name"] for r in data]
        assert "Room 1" in names
        assert "Room 2" in names


@pytest.mark.integration
@pytest.mark.asyncio
class TestAccessoryAPI:
    """Test accessory API endpoints."""
    
    async def test_create_accessory(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test creating a accessory via API."""
        # Create home and room
        home_repo = HomeRepository()
        room_repo = RoomRepository()
        
        home = await home_repo.create(test_session, name="Test House")
        room = await room_repo.create_with_home_name(
            test_session, home.id, home.name, name="Test Room"
        )
        
        # Create accessory via API
        response = await async_client.post(
            "/api/v1/accessories/",
            params={
                "home_id": home.id,
                "name": "API Accessory",
                "manufacturer": "Test Corp",
                "model": "T-1000",
                "room_ids": [room.id]
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Accessory"
        assert data["manufacturer"] == "Test Corp"
        assert data["model"] == "T-1000"
        assert data["home_id"] == home.id
    


@pytest.mark.integration
@pytest.mark.asyncio
class TestSyncAPI:
    """Test sync API endpoints."""
    
    async def test_sync_entities(self, async_client: AsyncClient):
        """Test syncing entities."""
        sync_request = {
            "homes": [
                {
                    "sync_id": "remote-home-1",
                    "name": "Remote House",
                    "is_primary": True,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat()
                }
            ],
            "rooms": [],
            "accessories": [],
            "users": []
        }
        
        response = await async_client.post(
            "/api/v1/sync/",
            json=sync_request
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["synced"]["homes"] == 1
        assert len(data["conflicts"]) == 0
        assert "timestamp" in data
    
    async def test_get_changes_since(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test getting changes since timestamp."""
        # Create some entities
        home_repo = HomeRepository()
        
        # Create homes at different times
        await home_repo.create(test_session, name="Old House")
        await asyncio.sleep(0.1)
        
        checkpoint = datetime.now(UTC) - timedelta(seconds=1)
        await asyncio.sleep(0.1)
        
        await home_repo.create(test_session, name="New House 1")
        await home_repo.create(test_session, name="New House 2")
        
        # Get changes
        response = await async_client.get(
            "/api/v1/sync/changes",
            params={"since": checkpoint.isoformat()}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["changes"]["homes"]) >= 2
        
        home_names = [h["name"] for h in data["changes"]["homes"]]
        assert "New House 1" in home_names
        assert "New House 2" in home_names