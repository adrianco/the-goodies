#!/usr/bin/env python
"""
Test script to demonstrate shared MCP functionality between
FunkyGibbon (server) and Blowing-Off (client).

This shows how the same MCP tool implementations work both
server-side and client-side.
"""

import asyncio
import sys
import os

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'blowing-off'))

from blowingoff.client import BlowingOffClient


async def test_local_mcp():
    """Test MCP functionality locally without server"""
    print("\n🔧 Testing Local MCP Functionality (Offline)")
    print("=" * 60)
    
    # Create client with local storage
    client = BlowingOffClient("test_shared_mcp.db")
    
    # Clear any existing data
    client.clear_graph_data()
    
    # Run the demo which creates sample data
    await client.demo_mcp_functionality()
    
    print("\n📋 Available MCP Tools:")
    tools = client.get_available_mcp_tools()
    for tool in tools:
        print(f"  - {tool}")
    
    print("\n✅ Local MCP test complete!")


async def test_homekit_to_graph_sync():
    """Test converting HomeKit data to graph format"""
    print("\n🏠 Testing HomeKit to Graph Conversion")
    print("=" * 60)
    
    # Create client
    client = BlowingOffClient("test_homekit_graph.db")
    
    # Connect to initialize database
    # Note: In a real scenario, this would connect to a real server
    # For testing, we just initialize the database
    try:
        await client.connect("http://localhost:8000", "test-token")
    except Exception as e:
        print(f"Note: Server connection failed (expected if server not running): {e}")
        print("Continuing with local testing...")
    
    # Create some test HomeKit data
    print("\n📝 Creating test HomeKit data...")
    
    # This would normally come from HomeKit sync, but for testing
    # we'll create some data directly
    async with client.session_factory() as session:
        from inbetweenies.models import Home, Room, Accessory
        
        # Create a home
        home = Home(
            id="test-home-1",
            name="Test Smart Home",
            is_primary=True
        )
        session.add(home)
        
        # Create rooms
        living_room = Room(
            id="living-room-1",
            home_id=home.id,
            name="Living Room"
        )
        bedroom = Room(
            id="bedroom-1", 
            home_id=home.id,
            name="Master Bedroom"
        )
        session.add(living_room)
        session.add(bedroom)
        
        # Create accessories
        light = Accessory(
            id="light-1",
            home_id=home.id,
            room_id=living_room.id,
            name="Smart Light",
            model="Hue Go",
            manufacturer="Philips"
        )
        thermostat = Accessory(
            id="thermostat-1",
            home_id=home.id,
            room_id=living_room.id,
            name="Smart Thermostat",
            model="Learning Thermostat",
            manufacturer="Nest"
        )
        session.add(light)
        session.add(thermostat)
        
        await session.commit()
    
    # Convert to graph format
    print("\n🔄 Converting HomeKit data to graph format...")
    entities, relationships = await client.sync_graph_from_homekit()
    print(f"✅ Created {entities} entities and {relationships} relationships")
    
    # Test MCP tools with the converted data
    print("\n🔍 Testing MCP tools with HomeKit data...")
    
    # Search for rooms
    result = await client.execute_mcp_tool(
        "search_entities",
        query="room",
        entity_types=["room"],
        limit=10
    )
    if result.get("success"):
        print(f"\nFound {result['result']['count']} rooms:")
        for item in result['result']['results']:
            print(f"  - {item['entity']['name']} (ID: {item['entity']['id']})")
    
    # Get devices in living room
    result = await client.execute_mcp_tool(
        "get_devices_in_room",
        room_id="living-room-1"
    )
    if result.get("success"):
        print(f"\nDevices in Living Room: {result['result']['count']}")
        for device in result['result']['devices']:
            print(f"  - {device['name']} ({device['content'].get('manufacturer', 'Unknown')})")
    
    # Search for specific devices
    result = await client.execute_mcp_tool(
        "search_entities",
        query="smart",
        entity_types=["device"],
        limit=5
    )
    if result.get("success"):
        print(f"\nFound {result['result']['count']} smart devices")
    
    print("\n✅ HomeKit to Graph conversion test complete!")
    
    # Cleanup
    await client.disconnect()


async def main():
    """Run all tests"""
    print("🧪 Testing Shared MCP Functionality")
    print("This demonstrates how MCP tools work both server-side and client-side")
    
    # Test 1: Local MCP functionality
    await test_local_mcp()
    
    print("\n" + "-" * 60 + "\n")
    
    # Test 2: HomeKit to Graph conversion
    await test_homekit_to_graph_sync()
    
    print("\n✨ All tests complete!")
    print("\nKey takeaways:")
    print("1. MCP tools work locally without server connection")
    print("2. HomeKit data can be converted to graph format for MCP usage")
    print("3. Same tool implementations work on both server and client")
    print("4. Client can operate fully offline with local graph storage")


if __name__ == "__main__":
    asyncio.run(main())