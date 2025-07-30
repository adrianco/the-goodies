"""
Test HomeKit client sync functionality.
"""

import pytest
import pytest_asyncio
import asyncio
from pathlib import Path
import tempfile
import sys

# Add parent directory to path to import modules
sys.path.insert(0, '/workspaces/the-goodies')

from blowingoff.homekit_client import HomeKitClient


@pytest.mark.integration
@pytest.mark.asyncio
class TestHomeKitSync:
    """Test HomeKit client sync operations."""
    
    @pytest_asyncio.fixture
    async def client(self):
        """Create test client."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
            
        client = HomeKitClient(db_path)
        await client.connect("http://localhost:8000", "test-token")
        
        yield client
        
        await client.disconnect()
        Path(db_path).unlink(missing_ok=True)
        
    @pytest_asyncio.fixture
    async def populated_client(self, client):
        """Client with test data."""
        # Create test home
        home_id = await client.create_home("Test Home", is_primary=True)
        
        # Create test room
        room_id = await client.create_room(home_id, "Living Room")
        
        return client, home_id, room_id
        
    @pytest.mark.asyncio
    async def test_get_homes(self, populated_client):
        """Test getting all homes."""
        client, home_id, _ = populated_client
        
        homes = await client.get_homes()
        assert len(homes) == 1
        assert homes[0]["id"] == home_id
        assert homes[0]["name"] == "Test Home"
        assert homes[0]["is_primary"] is True
        
    @pytest.mark.asyncio
    async def test_get_specific_home(self, populated_client):
        """Test getting a specific home by ID."""
        client, home_id, _ = populated_client
        
        home = await client.get_home(home_id)
        assert home is not None
        assert home["id"] == home_id
        assert home["name"] == "Test Home"
        
        # Test non-existent home
        home = await client.get_home("non-existent-id")
        assert home is None
        
    @pytest.mark.asyncio
    async def test_get_rooms(self, populated_client):
        """Test getting rooms in a home."""
        client, home_id, room_id = populated_client
        
        rooms = await client.get_rooms(home_id)
        assert len(rooms) == 1
        assert rooms[0]["id"] == room_id
        assert rooms[0]["name"] == "Living Room"
        assert rooms[0]["home_id"] == home_id
        
    @pytest.mark.asyncio
    async def test_create_multiple_homes(self, client):
        """Test creating multiple homes."""
        home1_id = await client.create_home("Home 1", is_primary=True)
        home2_id = await client.create_home("Home 2", is_primary=False)
        
        homes = await client.get_homes()
        assert len(homes) == 2
        
        # Find homes by name
        home1 = next(h for h in homes if h["name"] == "Home 1")
        home2 = next(h for h in homes if h["name"] == "Home 2")
        
        assert home1["is_primary"] is True
        assert home2["is_primary"] is False
        
    @pytest.mark.asyncio
    async def test_homekit_data_structure(self, client):
        """Test full HomeKit data structure creation."""
        # Create home
        home_id = await client.create_home("Smart Home", is_primary=True)
        
        # Create rooms
        living_room_id = await client.create_room(home_id, "Living Room")
        bedroom_id = await client.create_room(home_id, "Bedroom")
        
        # Verify structure
        homes = await client.get_homes()
        assert len(homes) == 1
        
        rooms = await client.get_rooms(home_id)
        assert len(rooms) == 2
        assert any(r["name"] == "Living Room" for r in rooms)
        assert any(r["name"] == "Bedroom" for r in rooms)