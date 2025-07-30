#!/usr/bin/env python3
"""
Test that the original failing test case is now fixed.

The issue was that get_house() was returning the first house instead of 
searching by ID when needed.
"""

import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

sys.path.insert(0, '/workspaces/the-goodies')

from inbetweenies.models import Base, Home
from blowingoff.homekit_client import HomeKitClient


async def test_get_house_fix():
    """Test that get_house() works correctly with HomeKit models."""
    # Create client
    client = HomeKitClient("test_fix.db")
    await client.connect("http://localhost:8000", "test-token")
    
    # Create multiple homes
    home1_id = await client.create_home("First Home", is_primary=True)
    home2_id = await client.create_home("Test House", is_primary=False)
    home3_id = await client.create_home("Another Home", is_primary=False)
    
    print("Created homes:")
    print(f"  - {home1_id}: First Home")
    print(f"  - {home2_id}: Test House")
    print(f"  - {home3_id}: Another Home")
    
    # Test 1: Get all homes
    all_homes = await client.get_homes()
    print(f"\nTotal homes: {len(all_homes)}")
    for home in all_homes:
        print(f"  - {home['id']}: {home['name']} (primary: {home['is_primary']})")
    
    # Test 2: Get specific home by ID
    test_home = await client.get_home(home2_id)
    assert test_home is not None, "Should find Test House by ID"
    assert test_home['name'] == "Test House", f"Expected 'Test House', got '{test_home['name']}'"
    print(f"\n✅ Found 'Test House' by ID: {home2_id}")
    
    # Test 3: Search for home by name
    all_homes = await client.get_homes()
    test_house = next((h for h in all_homes if h['name'] == "Test House"), None)
    assert test_house is not None, "Should find Test House by searching"
    assert test_house['id'] == home2_id, "Should have correct ID"
    print(f"✅ Found 'Test House' by searching: ID = {test_house['id']}")
    
    # Clean up
    await client.disconnect()
    print("\n✅ All tests passed! The issue is fixed.")


if __name__ == "__main__":
    asyncio.run(test_get_house_fix())