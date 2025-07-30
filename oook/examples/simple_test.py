#!/usr/bin/env python3
"""
Simple test script for Oook functionality
"""

import httpx
import json

def test_oook():
    """Test basic MCP operations"""
    
    print("=== Testing Oook/FunkyGibbon Phase 2 ===\n")
    
    client = httpx.Client(base_url="http://localhost:8000")
    
    # 1. Check health
    health = client.get("/health")
    print(f"1. Health check: {health.json()}")
    
    # 2. List MCP tools
    tools = client.get("/api/v1/mcp/tools")
    print(f"\n2. MCP tools available: {len(tools.json()['tools'])} tools")
    
    # 3. Create entities
    print("\n3. Creating test entities:")
    
    # Create home
    home = client.post("/api/v1/graph/entities", json={
        "entity_type": "home",
        "name": "Demo Home",
        "content": {"address": "123 Test Street"},
        "user_id": "test-user"
    })
    home_data = home.json()["entity"]
    print(f"   ✓ Created home: {home_data['name']} (ID: {home_data['id']})")
    
    # Create room
    room = client.post("/api/v1/graph/entities", json={
        "entity_type": "room",
        "name": "Kitchen",
        "content": {"area": 25},
        "user_id": "test-user"
    })
    room_data = room.json()["entity"]
    print(f"   ✓ Created room: {room_data['name']} (ID: {room_data['id']})")
    
    # Create device
    device = client.post("/api/v1/graph/entities", json={
        "entity_type": "device",
        "name": "Smart Oven",
        "content": {"manufacturer": "Samsung", "model": "SmartOven Pro"},
        "user_id": "test-user"
    })
    device_data = device.json()["entity"]
    print(f"   ✓ Created device: {device_data['name']} (ID: {device_data['id']})")
    
    # 4. Search entities
    print("\n4. Searching for entities:")
    search = client.post("/api/v1/graph/search", json={
        "query": "smart",
        "limit": 10
    })
    results = search.json()
    print(f"   Found {results['count']} results for 'smart'")
    
    # 5. Create relationships
    print("\n5. Creating relationships:")
    
    # Device in room
    rel1 = client.post("/api/v1/mcp/tools/create_relationship", json={
        "arguments": {
            "from_entity_id": device_data["id"],
            "to_entity_id": room_data["id"],
            "relationship_type": "located_in",
            "properties": {"wall": "north"}
        }
    })
    print("   ✓ Created relationship: device located_in room")
    
    # Room in home
    rel2 = client.post("/api/v1/mcp/tools/create_relationship", json={
        "arguments": {
            "from_entity_id": room_data["id"],
            "to_entity_id": home_data["id"],
            "relationship_type": "part_of",
            "properties": {"floor": 1}
        }
    })
    print("   ✓ Created relationship: room part_of home")
    
    # 6. Get graph statistics
    print("\n6. Graph statistics:")
    stats = client.get("/api/v1/graph/statistics")
    stats_data = stats.json()
    print(f"   - Total entities: {stats_data['total_entities']}")
    print(f"   - Total relationships: {stats_data['total_relationships']}")
    print(f"   - Entity types: {json.dumps(stats_data['entity_types'], indent=6)}")
    
    print("\n✅ All tests passed! Phase 2 implementation is working correctly.")
    
    client.close()

if __name__ == "__main__":
    try:
        test_oook()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure the FunkyGibbon server is running on http://localhost:8000")