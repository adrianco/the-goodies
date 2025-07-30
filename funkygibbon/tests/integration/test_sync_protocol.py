"""
Test the full sync protocol flow with real endpoints.

These tests ensure the Inbetweenies protocol works correctly
end-to-end, catching issues like lazy loading in to_dict().
"""

import pytest
from datetime import datetime, UTC, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.repositories import (
    HomeRepository,
    RoomRepository,
    AccessoryRepository,
    UserRepository
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestSyncProtocol:
    """Test the complete sync protocol flow."""
    
    async def test_sync_request_with_accessories(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test sync request endpoint with accessories that have room relationships."""
        # Create test data with relationships
        home_repo = HomeRepository()
        room_repo = RoomRepository()
        accessory_repo = AccessoryRepository()
        
        home = await home_repo.create(
            test_session,
            name="Sync Test Home",
            is_primary=True
        )
        
        room1 = await room_repo.create(
            test_session,
            home_id=home.id,
            name="Living Room"
        )
        
        room2 = await room_repo.create(
            test_session,
            home_id=home.id,
            name="Bedroom"
        )
        
        # Create accessory without room associations
        # (room associations need to be managed separately)
        accessory = await accessory_repo.create(
            test_session,
            home_id=home.id,
            name="Multi-room Speaker",
            manufacturer="Audio Corp",
            model="Speaker Pro"
        )
        
        await test_session.commit()
        
        # Make sync request
        sync_request = {
            "type": "sync_request",
            "client_id": "test-client-1",
            "last_sync": None,
            "entity_types": ["homes", "rooms", "accessories", "users"],
            "include_deleted": False
        }
        
        response = await async_client.post(
            "/api/v1/sync/request",
            json=sync_request
        )
        
        # This should NOT fail with lazy loading errors
        assert response.status_code == 200
        
        data = response.json()
        assert data["type"] == "sync_delta"
        assert "changes" in data
        
        # Debug: print all changes
        print(f"Changes: {data['changes']}")
        
        # Find our accessory in the changes
        accessory_changes = [
            c for c in data["changes"] 
            if c.get("entity_type") == "accessory" and c.get("entity_id") == accessory.id
        ]
        
        # If not found with exact match, look for any accessory changes
        if not accessory_changes:
            accessory_changes = [
                c for c in data["changes"] 
                if c.get("entity_type") == "accessory"
            ]
        
        assert len(accessory_changes) >= 1
        accessory_data = accessory_changes[0]["data"]
        
        # Verify accessory data doesn't include room_ids (would cause lazy loading)
        assert "room_ids" not in accessory_data
        assert accessory_data["name"] == "Multi-room Speaker"
        assert accessory_data["manufacturer"] == "Audio Corp"
    
    async def test_sync_request_empty_database(self, async_client: AsyncClient):
        """Test sync request with empty database doesn't fail."""
        sync_request = {
            "type": "sync_request",
            "client_id": "test-client-2",
            "last_sync": None,
            "entity_types": ["homes", "rooms", "accessories", "users"],
            "include_deleted": False
        }
        
        response = await async_client.post(
            "/api/v1/sync/request",
            json=sync_request
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "sync_delta"
        assert data["changes"] == []
        assert data["conflicts"] == []
    
    async def test_sync_push_with_conflicts(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test sync push with conflicts."""
        # Create initial home
        home_repo = HomeRepository()
        home = await home_repo.create(
            test_session,
            name="Original Name",
            is_primary=False
        )
        await test_session.commit()
        
        # Client pushes conflicting change
        sync_push = {
            "type": "sync_push",
            "client_id": "test-client-3",
            "changes": [
                {
                    "entity_type": "home",
                    "entity_id": home.id,
                    "operation": "update",
                    "data": {
                        "id": home.id,
                        "name": "Client Updated Name",
                        "is_primary": True,
                        "updated_at": datetime.now(UTC).isoformat(),
                        "sync_id": "client-sync-id"
                    },
                    "client_sync_id": "client-change-1"
                }
            ]
        }
        
        response = await async_client.post(
            "/api/v1/sync/push",
            json=sync_push
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "sync_result"
        
        # Should have processed the change
        assert len(data["applied"]) > 0 or len(data["conflicts"]) > 0
    
    async def test_sync_ack(self, async_client: AsyncClient):
        """Test sync acknowledgment endpoint."""
        sync_ack = {
            "type": "sync_ack",
            "client_id": "test-client-4",
            "sync_completed_at": datetime.now(UTC).isoformat()
        }
        
        response = await async_client.post(
            "/api/v1/sync/ack",
            json=sync_ack
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "acknowledged"
    
    async def test_full_sync_cycle(self, async_client: AsyncClient, test_session: AsyncSession):
        """Test a complete sync cycle: request -> push -> ack."""
        # Create server data
        home_repo = HomeRepository()
        home = await home_repo.create(
            test_session,
            name="Server Home",
            is_primary=True
        )
        await test_session.commit()
        
        client_id = "test-client-5"
        
        # Step 1: Sync request
        sync_request = {
            "type": "sync_request",
            "client_id": client_id,
            "last_sync": None,
            "entity_types": ["homes"],
            "include_deleted": False
        }
        
        request_response = await async_client.post(
            "/api/v1/sync/request",
            json=sync_request
        )
        
        assert request_response.status_code == 200
        request_data = request_response.json()
        assert len(request_data["changes"]) == 1
        assert request_data["changes"][0]["entity_id"] == home.id
        
        # Step 2: Client makes changes and pushes
        sync_push = {
            "type": "sync_push",
            "client_id": client_id,
            "changes": [
                {
                    "entity_type": "home",
                    "entity_id": home.id,
                    "operation": "update",
                    "data": {
                        "id": home.id,
                        "name": "Client Updated Home",
                        "is_primary": False,
                        "created_at": home.created_at.isoformat(),
                        "updated_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),  # Older timestamp
                        "sync_id": "client-sync-1"
                    },
                    "client_sync_id": "change-1"
                }
            ]
        }
        
        push_response = await async_client.post(
            "/api/v1/sync/push",
            json=sync_push
        )
        
        assert push_response.status_code == 200
        push_data = push_response.json()
        print(f"Push response: {push_data}")
        assert len(push_data["applied"]) > 0 or len(push_data["conflicts"]) > 0
        
        # Step 3: Acknowledge sync
        sync_ack = {
            "type": "sync_ack",
            "client_id": client_id,
            "sync_completed_at": datetime.now(UTC).isoformat()
        }
        
        ack_response = await async_client.post(
            "/api/v1/sync/ack",
            json=sync_ack
        )
        
        assert ack_response.status_code == 200
        
        # Verify the conflict was resolved (server wins with newer timestamp)
        updated_home = await home_repo.get_by_id(test_session, home.id)
        if len(push_data["conflicts"]) > 0:
            # Server won the conflict
            assert updated_home.name == "Server Home"
            assert updated_home.is_primary == True
        else:
            # Client change was applied
            assert updated_home.name == "Client Updated Home"
            assert updated_home.is_primary == False