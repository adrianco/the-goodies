#!/usr/bin/env python
"""
Test script to demonstrate shared MCP functionality between
FunkyGibbon (server) and Blowing-Off (client).

This shows how the same MCP tool implementations work both
server-side and client-side using the Entity model.
"""

import asyncio
import sys
import os
import pytest
import tempfile

# Add paths for imports (not needed with PYTHONPATH set correctly)

from blowingoff.client import BlowingOffClient


@pytest.mark.asyncio
async def test_local_mcp():
    """Test MCP functionality locally without server"""
    print("\n🔧 Testing Local MCP Functionality (Offline)")
    print("=" * 60)

    # Create client with local storage in temp directory
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    client = BlowingOffClient(db_path)

    # Clear any existing data
    client.clear_graph_data()

    # Create test entities using graph operations
    from inbetweenies.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType

    print("\n📝 Creating test graph data...")

    # Create a home entity
    home = Entity(
        entity_type=EntityType.HOME,
        name="Test Smart Home",
        content={
            "address": "123 Test Street",
            "is_primary": True
        },
        source_type=SourceType.MANUAL
    )
    stored_home = await client.graph_operations.store_entity(home)

    # Create rooms
    living_room = Entity(
        entity_type=EntityType.ROOM,
        name="Living Room",
        content={
            "floor": "1st",
            "area_sqft": 300
        },
        source_type=SourceType.MANUAL
    )
    bedroom = Entity(
        entity_type=EntityType.ROOM,
        name="Master Bedroom",
        content={
            "floor": "2nd",
            "area_sqft": 200
        },
        source_type=SourceType.MANUAL
    )
    stored_living = await client.graph_operations.store_entity(living_room)
    stored_bedroom = await client.graph_operations.store_entity(bedroom)

    # Create devices
    light = Entity(
        entity_type=EntityType.DEVICE,
        name="Smart Light",
        content={
            "manufacturer": "Philips",
            "model": "Hue Go",
            "capabilities": ["on_off", "brightness", "color"]
        },
        source_type=SourceType.MANUAL
    )
    thermostat = Entity(
        entity_type=EntityType.DEVICE,
        name="Smart Thermostat",
        content={
            "manufacturer": "Nest",
            "model": "Learning Thermostat",
            "capabilities": ["temperature", "humidity", "scheduling"]
        },
        source_type=SourceType.MANUAL
    )
    stored_light = await client.graph_operations.store_entity(light)
    stored_thermostat = await client.graph_operations.store_entity(thermostat)

    # Create relationships
    # Rooms in home
    await client.graph_operations.store_relationship(
        EntityRelationship(
            from_entity_id=stored_living.id,
            from_entity_version=stored_living.version,
            to_entity_id=stored_home.id,
            to_entity_version=stored_home.version,
            relationship_type=RelationshipType.LOCATED_IN
        )
    )
    await client.graph_operations.store_relationship(
        EntityRelationship(
            from_entity_id=stored_bedroom.id,
            from_entity_version=stored_bedroom.version,
            to_entity_id=stored_home.id,
            to_entity_version=stored_home.version,
            relationship_type=RelationshipType.LOCATED_IN
        )
    )

    # Devices in rooms
    await client.graph_operations.store_relationship(
        EntityRelationship(
            from_entity_id=stored_light.id,
            from_entity_version=stored_light.version,
            to_entity_id=stored_living.id,
            to_entity_version=stored_living.version,
            relationship_type=RelationshipType.LOCATED_IN
        )
    )
    await client.graph_operations.store_relationship(
        EntityRelationship(
            from_entity_id=stored_thermostat.id,
            from_entity_version=stored_thermostat.version,
            to_entity_id=stored_living.id,
            to_entity_version=stored_living.version,
            relationship_type=RelationshipType.LOCATED_IN
        )
    )

    print("✅ Created test entities and relationships")

    # Test MCP tools
    print("\n📋 Available MCP Tools:")
    tools = client.get_available_mcp_tools()
    for tool in tools:
        print(f"  - {tool}")

    # Test search functionality
    print("\n🔍 Testing MCP search tools...")

    # Search for rooms
    result = await client.execute_mcp_tool(
        "search_entities",
        query="room",
        entity_types=[EntityType.ROOM.value],
        limit=10
    )
    if result.get("success"):
        print(f"\nFound {result['result']['count']} rooms:")
        for item in result['result']['results']:
            print(f"  - {item['entity']['name']} (ID: {item['entity']['id']})")

    # Get devices in living room
    result = await client.execute_mcp_tool(
        "get_devices_in_room",
        room_id=stored_living.id
    )
    if result.get("success"):
        print(f"\nDevices in Living Room: {result['result']['count']}")
        for device in result['result']['devices']:
            print(f"  - {device['name']} ({device['content'].get('manufacturer', 'Unknown')})")

    # Search for specific devices
    result = await client.execute_mcp_tool(
        "search_entities",
        query="smart",
        entity_types=[EntityType.DEVICE.value],
        limit=5
    )
    if result.get("success"):
        print(f"\nFound {result['result']['count']} smart devices")

    print("\n✅ Local MCP test complete!")


@pytest.mark.asyncio
async def test_graph_operations():
    """Test advanced graph operations"""
    print("\n🎯 Testing Advanced Graph Operations")
    print("=" * 60)

    # Create client with temp database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    client = BlowingOffClient(db_path)

    # Clear any existing data
    client.clear_graph_data()

    # Create a more complex graph
    from inbetweenies.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType

    print("\n📝 Creating complex graph structure...")

    # Create multiple homes
    home1 = await client.graph_operations.store_entity(
        Entity(
            entity_type=EntityType.HOME,
            name="Main House",
            content={"city": "San Francisco"},
            source_type=SourceType.MANUAL
        )
    )

    home2 = await client.graph_operations.store_entity(
        Entity(
            entity_type=EntityType.HOME,
            name="Vacation House",
            content={"city": "Lake Tahoe"},
            source_type=SourceType.MANUAL
        )
    )

    # Create users
    john = await client.graph_operations.store_entity(
        Entity(
            entity_type=EntityType.NOTE,
            name="John Doe",
            content={"role": "owner"},
            source_type=SourceType.MANUAL
        )
    )

    jane = await client.graph_operations.store_entity(
        Entity(
            entity_type=EntityType.NOTE,
            name="Jane Doe",
            content={"role": "admin"},
            source_type=SourceType.MANUAL
        )
    )

    # Create ownership relationships
    await client.graph_operations.store_relationship(
        EntityRelationship(
            from_entity_id=john.id,
            from_entity_version=john.version,
            to_entity_id=home1.id,
            to_entity_version=home1.version,
            relationship_type=RelationshipType.MANAGES
        )
    )

    await client.graph_operations.store_relationship(
        EntityRelationship(
            from_entity_id=jane.id,
            from_entity_version=jane.version,
            to_entity_id=home1.id,
            to_entity_version=home1.version,
            relationship_type=RelationshipType.MANAGES
        )
    )

    print("✅ Created complex graph structure")

    # Test graph traversal
    print("\n🗺️ Testing graph traversal...")

    # Find all homes managed by John
    result = await client.execute_mcp_tool(
        "get_related_entities",
        entity_id=john.id,
        relationship_type=RelationshipType.MANAGES.value,
        direction="outgoing"
    )
    if result.get("success"):
        print(f"\nHomes managed by John: {result['result']['count']}")
        for home in result['result']['entities']:
            print(f"  - {home['name']}")

    # Find all users managing the main house
    result = await client.execute_mcp_tool(
        "get_related_entities",
        entity_id=home1.id,
        relationship_type=RelationshipType.MANAGES.value,
        direction="incoming"
    )
    if result.get("success"):
        print(f"\nUsers managing Main House: {result['result']['count']}")
        for user in result['result']['entities']:
            print(f"  - {user['name']} ({user['content'].get('role', 'user')})")

    print("\n✅ Graph operations test complete!")

    # Cleanup
    await client.disconnect()


async def main():
    """Run all tests"""
    print("🧪 Testing Shared MCP Functionality")
    print("This demonstrates how MCP tools work both server-side and client-side")

    # Test 1: Local MCP functionality
    await test_local_mcp()

    print("\n" + "-" * 60 + "\n")

    # Test 2: Advanced graph operations
    await test_graph_operations()

    print("\n✨ All tests complete!")
    print("\nKey takeaways:")
    print("1. MCP tools work locally without server connection")
    print("2. Graph operations provide powerful entity and relationship management")
    print("3. Same tool implementations work on both server and client")
    print("4. Client can operate fully offline with local graph storage")


if __name__ == "__main__":
    asyncio.run(main())
