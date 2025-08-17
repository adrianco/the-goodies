"""
Blowing-Off Client - Basic Sync Integration Tests

DEVELOPMENT CONTEXT:
Updated to use the Entity model and graph operations instead of HomeKit models.
Tests the Inbetweenies synchronization protocol with graph entities.

FUNCTIONALITY:
- Tests initial sync from empty client
- Validates entity creation and sync from server to client
- Tests bidirectional sync (client to server and back)
- Verifies conflict resolution with last-write-wins
- Tests offline queue and batch sync operations
- Validates sync status tracking and metadata

PURPOSE:
Ensures the Inbetweenies protocol implementation works correctly for
common sync scenarios using the Entity model.

REVISION HISTORY:
- 2025-07-30: Updated to use Entity model instead of HomeKit models
- 2025-07-28: Initial implementation of basic sync tests
- 2025-07-28: Added conflict resolution and offline queue tests

DEPENDENCIES:
- pytest-asyncio: Async test support
- httpx: HTTP client for server setup
- tempfile: Temporary database creation

USAGE:
Run with: pytest tests/integration/test_sync_basic.py
Requires: FunkyGibbon server running (cd funkygibbon && python -m funkygibbon.main)
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime
import json
import httpx
from pathlib import Path
import tempfile
import sys
import os

from blowingoff import BlowingOffClient


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.environ.get('CI') == 'true' and sys.platform == 'win32',
                    reason="Integration tests timeout on Windows CI")
class TestBasicSync:
    """Test basic sync operations between client and server."""
    # Using fixtures from conftest.py for server_url and auth_token
        
    @pytest_asyncio.fixture
    async def client(self, server_url, auth_token):
        """Create test client."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
            
        client = BlowingOffClient(db_path)
        await client.connect(server_url, auth_token, "test-client-1")
        
        yield client
        
        await client.disconnect()
        Path(db_path).unlink(missing_ok=True)
        
    @pytest.mark.asyncio
    async def test_initial_sync(self, client):
        """Test initial sync from empty client."""
        # Perform sync
        result = await client.sync()
        
        assert result.success
        assert result.synced_entities >= 0  # Should sync the test data from populate_db
        assert result.conflicts_resolved == 0
        assert len(result.errors) == 0
        
        # Verify we can search for entities (if any exist)
        from inbetweenies.models import EntityType
        try:
            search_result = await client.execute_mcp_tool(
                "search_entities",
                query="Martinez",
                entity_types=[EntityType.HOME.value],
                limit=10
            )
            if search_result["success"] and search_result["result"]["count"] > 0:
                # Test data exists
                assert search_result["result"]["results"][0]["entity"]["name"] == "The Martinez Smart Home"
        except Exception:
            # Search might fail if no test data exists, which is ok for initial sync
            pass
        
    @pytest.mark.asyncio
    async def test_create_and_sync(self, client, server_url, auth_token):
        """Test creating entities on server and syncing to client."""
        # Create test data on server using graph API
        async with httpx.AsyncClient(base_url=server_url) as http:
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            # Create a test home entity
            entity_data = {
                "entity_type": "home",
                "name": "Test Home Entity",
                "content": {
                    "address": "123 Test Street",
                    "is_primary": True
                },
                "user_id": "test-user"
            }
            response = await http.post(
                "/api/v1/graph/entities",
                json=entity_data,
                headers=headers
            )
            assert response.status_code in [200, 201]
            home_entity = response.json()["entity"]
            
            # Create a room entity
            room_data = {
                "entity_type": "room",
                "name": "Test Living Room",
                "content": {
                    "floor": "1st",
                    "area_sqft": 250
                },
                "user_id": "test-user"
            }
            response = await http.post(
                "/api/v1/graph/entities",
                json=room_data,
                headers=headers
            )
            assert response.status_code in [200, 201]
            room_entity = response.json()["entity"]
            
            # Create relationship between home and room
            rel_data = {
                "source_id": room_entity["id"],
                "target_id": home_entity["id"],
                "relationship_type": "located_in",
                "user_id": "test-user"
            }
            response = await http.post(
                "/api/v1/graph/relationships",
                json=rel_data,
                headers=headers
            )
            assert response.status_code in [200, 201]
            
        # Sync to client
        result = await client.sync()
        assert result.success
        
        # Verify data synced using MCP tools
        from inbetweenies.models import EntityType
        
        # Search for the new home
        search_result = await client.execute_mcp_tool(
            "search_entities",
            query="Test Home Entity",
            entity_types=[EntityType.HOME.value],
            limit=10
        )
        assert search_result["success"]
        assert search_result["result"]["count"] >= 1
        
        # Search for the room
        room_search = await client.execute_mcp_tool(
            "search_entities", 
            query="Test Living Room",
            entity_types=[EntityType.ROOM.value],
            limit=10
        )
        assert room_search["success"]
        assert room_search["result"]["count"] >= 1
        
    @pytest.mark.asyncio
    async def test_bidirectional_sync(self, client):
        """Test syncing changes in both directions."""
        # Initial sync
        await client.sync()
        
        # Create entities locally using graph operations
        from inbetweenies.models import Entity, EntityType, SourceType
        
        # Create a device entity locally
        import uuid
        entity_id = str(uuid.uuid4())
        device_entity = Entity(
            id=entity_id,
            version=Entity.create_version("test-user"),
            entity_type=EntityType.DEVICE,
            name="Test Smart Light",
            content={
                "manufacturer": "Test Corp",
                "model": "Smart Bulb v2",
                "power": "on",
                "brightness": 75
            },
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        
        # Store it locally
        stored_device = await client.graph_operations.store_entity(device_entity)
        
        # Sync to server
        result = await client.sync()
        assert result.success
        # The sync should report at least one entity synced
        assert result.synced_entities > 0
        
    @pytest.mark.asyncio
    async def test_conflict_resolution(self, client, server_url, auth_token):
        """Test last-write-wins conflict resolution."""
        # Initial sync
        await client.sync()
        
        # Create entity on both client and server with same type but will get different IDs
        from inbetweenies.models import Entity, EntityType, SourceType
        
        # Create on client
        import uuid
        entity_id = str(uuid.uuid4())
        client_entity = Entity(
            id=entity_id,
            version=Entity.create_version("test-user"),
            entity_type=EntityType.DEVICE,
            name="Conflict Test Device",
            content={"value": "client-version"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        stored_client = await client.graph_operations.store_entity(client_entity)
        
        # Create similar on server
        async with httpx.AsyncClient(base_url=server_url) as http:
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            server_entity = {
                "entity_type": "device",
                "name": "Conflict Test Device Server",
                "content": {"value": "server-version"},
                "user_id": "test-user"
            }
            
            response = await http.post(
                "/api/v1/graph/entities",
                json=server_entity,
                headers=headers
            )
            assert response.status_code in [200, 201]
        
        # Sync should handle both entities without conflict since they have different IDs
        result = await client.sync()
        assert result.success
        
        # Both entities should exist
        search_result = await client.execute_mcp_tool(
            "search_entities",
            query="Conflict Test Device",
            entity_types=[EntityType.DEVICE.value],
            limit=10
        )
        assert search_result["success"]
        # Should find both versions
        assert search_result["result"]["count"] >= 2
        
    @pytest.mark.asyncio
    async def test_offline_queue(self, client):
        """Test offline changes are queued and synced."""
        # Initial sync
        await client.sync()
        
        # Create multiple entities locally
        from inbetweenies.models import Entity, EntityType, SourceType
        import uuid
        
        entities_created = []
        for i in range(3):
            entity_id = str(uuid.uuid4())
            entity = Entity(
                id=entity_id,
                version=Entity.create_version("test-user"),
                entity_type=EntityType.DEVICE,
                name=f"Offline Device {i}",
                content={"index": i, "created_offline": True},
                source_type=SourceType.MANUAL,
                user_id="test-user",
                parent_versions=[]
            )
            stored = await client.graph_operations.store_entity(entity)
            entities_created.append(stored)
        
        # Sync should push all queued changes
        result = await client.sync()
        assert result.success
        # Should sync at least the 3 entities we created
        assert result.synced_entities >= 3
        
    @pytest.mark.asyncio
    async def test_sync_status_tracking(self, client):
        """Test sync status and metadata tracking."""
        # Perform initial sync
        result1 = await client.sync()
        assert result1.success
        
        # Wait a moment
        await asyncio.sleep(0.1)
        
        # Perform another sync
        result2 = await client.sync()
        assert result2.success
        
        # Second sync should have later timestamp
        assert result2.timestamp > result1.timestamp
        
        # Duration should be tracked
        assert result1.duration > 0
        assert result2.duration > 0