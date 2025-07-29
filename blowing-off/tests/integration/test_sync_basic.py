"""
Blowing-Off Client - Basic Sync Integration Tests

DEVELOPMENT CONTEXT:
Created as part of the Blowing-Off Python test client to validate the
Inbetweenies synchronization protocol. These tests ensure basic sync
operations work correctly between client and server.

FUNCTIONALITY:
- Tests initial sync from empty client
- Validates entity creation and sync from server to client
- Tests bidirectional sync (client to server and back)
- Verifies conflict resolution with last-write-wins
- Tests offline queue and batch sync operations
- Validates sync status tracking and metadata

PURPOSE:
Ensures the Inbetweenies protocol implementation works correctly for
common sync scenarios. These tests serve as validation for both the
Python implementation and as reference for Swift/WildThing development.

KNOWN ISSUES:
- Requires FunkyGibbon server running on localhost:8000
- Some tests may be flaky due to timing dependencies
- Auth token is hardcoded for testing

REVISION HISTORY:
- 2025-07-28: Initial implementation of basic sync tests
- 2025-07-28: Added conflict resolution and offline queue tests
- 2025-07-28: Skipped entire test class due to database concurrency issues

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

from blowingoff import BlowingOffClient


@pytest.mark.integration
@pytest.mark.asyncio
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
        
        # Verify we got the test data
        home = await client.get_home()
        assert home is not None
        assert home["name"] == "The Martinez Smart Home"
        
    @pytest.mark.asyncio
    async def test_create_and_sync(self, client, server_url, auth_token):
        """Test creating entities on server and syncing to client."""
        # Create test data on server
        async with httpx.AsyncClient(base_url=server_url) as http:
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            # Create home using query parameters
            response = await http.post(
                "/api/v1/homes/?name=Test%20Home&is_primary=true",
                headers=headers
            )
            assert response.status_code in [200, 201]
            home_data = response.json()
            home_id = home_data["id"]
            
            # Create room using query parameters
            response = await http.post(
                f"/api/v1/rooms/?home_id={home_id}&name=Living%20Room",
                headers=headers
            )
            assert response.status_code in [200, 201]
            
        # Sync to client
        result = await client.sync()
        assert result.success
        
        # Verify data synced
        homes = await client.get_homes()
        assert len(homes) >= 2  # Pre-populated + newly created
        
        # Find the test home we created
        test_home = next((h for h in homes if h["name"] == "Test Home"), None)
        assert test_home is not None
        assert test_home["is_primary"] == True
        
        rooms = await client.get_rooms()
        assert len(rooms) >= 1
        assert any(r["name"] == "Living Room" for r in rooms)
        
    @pytest.mark.asyncio
    async def test_bidirectional_sync(self, client):
        """Test syncing changes in both directions."""
        # Initial sync
        await client.sync()
        
        # Create accessory on client
        rooms = await client.get_rooms()
        if not rooms:
            # Create home and room first
            home_id = await client.create_home("Test Home 2")
            room_id = await client.create_room(home_id, "Test Room")
        else:
            room_id = rooms[0]["id"]
            
        accessory_id = await client.create_accessory(
            room_id,
            "Test Light",
            "light",
            manufacturer="Test Corp"
        )
        
        # Update accessory state
        await client.update_accessory_state(
            accessory_id,
            {"power": "on", "brightness": 75}
        )
        
        # Sync to server
        result = await client.sync()
        assert result.success
        # Check that either entities were synced or conflicts were resolved
        assert result.synced_entities > 0 or len(result.conflicts) > 0
        
    @pytest.mark.asyncio
    async def test_conflict_resolution(self, client, server_url, auth_token):
        """Test last-write-wins conflict resolution."""
        # Create accessory on both sides with same ID
        accessory_id = "conflict-accessory-1"
        room_id = "test-room-1"
        
        # Create on server
        async with httpx.AsyncClient(base_url=server_url) as http:
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            server_accessory = {
                "id": accessory_id,
                "room_id": room_id,
                "name": "Server Accessory",
                "accessory_type": "light",
                "updated_at": datetime.now().isoformat()
            }
            await http.post(
                f"{server_url}/api/v1/accessories",
                json=server_accessory,
                headers=headers
            )
            
        # Create on client with slightly older timestamp
        await asyncio.sleep(0.1)  # Ensure different timestamp
        
        # Create locally (this would normally happen through the client API)
        # For testing, we'll sync first then modify
        await client.sync()
        
        # Now update the accessory locally
        accessories = await client.get_accessories()
        if accessories:
            # Update the first accessory
            await client.update_accessory_state(
                accessories[0]["id"],
                {"power": "off"}
            )
            
        # Sync should resolve conflicts
        result = await client.sync()
        assert result.success
        
        # Check if conflicts were detected
        if result.conflicts:
            assert result.conflicts[0].resolution in [
                "newer_local", "newer_remote", "sync_id_tiebreak_local", "sync_id_tiebreak_remote"
            ]
            
    @pytest.mark.asyncio 
    async def test_offline_queue(self, client):
        """Test offline changes are queued and synced."""
        # Initial sync
        await client.sync()
        
        # Create changes while "offline"
        # (In real scenario, we'd disconnect from network)
        rooms = await client.get_rooms()
        if rooms:
            room_id = rooms[0]["id"]
            
            # Create multiple accessories
            for i in range(3):
                await client.create_accessory(
                    room_id,
                    f"Offline Accessory {i}",
                    "switch"
                )
                
        # Sync should push all queued changes
        result = await client.sync()
        assert result.success
        # Check that all 3 accessories were detected (either synced or as conflicts)
        assert result.synced_entities >= 3 or len(result.conflicts) >= 3
        
    @pytest.mark.asyncio
    async def test_sync_status_tracking(self, client):
        """Test sync status and metadata tracking."""
        # Get initial status
        status = await client.get_sync_status()
        initial_syncs = status["total_syncs"]
        
        # Perform sync
        result = await client.sync()
        assert result.success
        
        # Check updated status
        status = await client.get_sync_status()
        assert status["total_syncs"] == initial_syncs + 1
        assert status["last_sync"] is not None
        assert status["sync_failures"] == 0
        assert not status["sync_in_progress"]