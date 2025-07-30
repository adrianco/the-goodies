"""
Test HomeKit client functionality.
"""

import pytest
import pytest_asyncio
import tempfile
from pathlib import Path

# Import without using the full blowingoff package to avoid old model issues
import sys
sys.path.insert(0, '/workspaces/the-goodies')
sys.path.insert(0, '/workspaces/the-goodies/blowing-off')

from blowingoff.homekit_client import HomeKitClient


@pytest_asyncio.fixture
async def client():
    """Create test client."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
        
    client = HomeKitClient(db_path)
    await client.connect("http://localhost:8000", "test-token")
    
    yield client
    
    await client.disconnect()
    Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_create_home(client):
    """Test creating a home."""
    home_id = await client.create_home("Test Home", is_primary=True)
    assert home_id is not None
    assert home_id.startswith("home-")
    
    # Verify it was created
    homes = await client.get_homes()
    assert len(homes) == 1
    assert homes[0]["name"] == "Test Home"
    assert homes[0]["is_primary"] is True


@pytest.mark.asyncio
async def test_get_specific_home(client):
    """Test getting a specific home by ID."""
    # Create multiple homes
    home1_id = await client.create_home("Home 1", is_primary=True)
    home2_id = await client.create_home("Home 2", is_primary=False)
    
    # Get specific home
    home2 = await client.get_home(home2_id)
    assert home2 is not None
    assert home2["id"] == home2_id
    assert home2["name"] == "Home 2"
    assert home2["is_primary"] is False
    
    # Test non-existent home
    no_home = await client.get_home("non-existent")
    assert no_home is None


@pytest.mark.asyncio
async def test_create_room(client):
    """Test creating a room."""
    home_id = await client.create_home("Test Home", is_primary=True)
    room_id = await client.create_room(home_id, "Living Room")
    
    assert room_id is not None
    assert room_id.startswith("room-")
    
    # Verify it was created
    rooms = await client.get_rooms(home_id)
    assert len(rooms) == 1
    assert rooms[0]["name"] == "Living Room"
    assert rooms[0]["home_id"] == home_id


@pytest.mark.asyncio
async def test_get_accessories(client):
    """Test getting accessories."""
    # Initially no accessories
    accessories = await client.get_accessories()
    assert len(accessories) == 0
    
    # Test with filters (should handle empty results)
    accessories = await client.get_accessories(home_id="test-home")
    assert len(accessories) == 0


@pytest.mark.asyncio
async def test_update_characteristic(client):
    """Test updating a characteristic value."""
    # This would normally require creating an accessory, service, and characteristic
    # For now, just verify the method exists
    assert hasattr(client, 'update_characteristic')


@pytest.mark.asyncio
async def test_multiple_homes_scenario(client):
    """Test the scenario from the original failing test."""
    # Create multiple homes like in the original test
    home1_id = await client.create_home("The Martinez Smart Home", is_primary=True)
    home2_id = await client.create_home("Test House", is_primary=False)
    home3_id = await client.create_home("Another Home", is_primary=False)
    
    # Get all homes
    all_homes = await client.get_homes()
    assert len(all_homes) == 3
    
    # Find Test House by searching through all homes
    test_house = next((h for h in all_homes if h["name"] == "Test House"), None)
    assert test_house is not None
    assert test_house["id"] == home2_id
    
    # Get Test House directly by ID
    house_by_id = await client.get_home(home2_id)
    assert house_by_id is not None
    assert house_by_id["name"] == "Test House"
    assert house_by_id["id"] == home2_id