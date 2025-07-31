#!/usr/bin/env python3
"""
Interactive demo script for Oook CLI

This script demonstrates how to use Oook programmatically
for automated testing or integration scenarios.
"""

import json
import time
from oook.cli import MCPClient


def demo_mcp_operations():
    """Demonstrate various MCP operations"""
    
    # Initialize client
    client = MCPClient("http://localhost:8000")
    
    print("=== Oook Programmatic Demo ===\n")
    
    # 1. List available tools
    print("1. Available MCP Tools:")
    tools = client.list_tools()
    for tool in tools[:3]:  # Show first 3
        print(f"   - {tool['name']}: {tool.get('description', 'No description')}")
    print(f"   ... and {len(tools) - 3} more\n")
    
    # 2. Create some test entities
    print("2. Creating test entities:")
    
    entities = []
    
    # Create a home
    home = client.create_entity(
        entity_type="home",
        name="Smart Home Demo",
        content={"address": "456 Demo Lane", "floors": 2}
    )
    entities.append(home['entity'])
    print(f"   ✓ Created home: {home['entity']['name']} (ID: {home['entity']['id']})")
    
    # Create rooms
    living_room = client.create_entity(
        entity_type="room",
        name="Living Room",
        content={"area": 35, "floor": 1}
    )
    entities.append(living_room['entity'])
    print(f"   ✓ Created room: {living_room['entity']['name']} (ID: {living_room['entity']['id']})")
    
    kitchen = client.create_entity(
        entity_type="room",
        name="Kitchen",
        content={"area": 25, "floor": 1}
    )
    entities.append(kitchen['entity'])
    print(f"   ✓ Created room: {kitchen['entity']['name']} (ID: {kitchen['entity']['id']})")
    
    # Create devices
    light = client.create_entity(
        entity_type="device",
        name="Smart LED Bulb",
        content={
            "manufacturer": "Philips",
            "model": "Hue Go",
            "capabilities": ["dimming", "color", "scenes"]
        }
    )
    entities.append(light['entity'])
    print(f"   ✓ Created device: {light['entity']['name']} (ID: {light['entity']['id']})")
    
    sensor = client.create_entity(
        entity_type="device",
        name="Temperature Sensor",
        content={
            "manufacturer": "Aqara",
            "battery": 85,
            "current_temp": 22.5
        }
    )
    entities.append(sensor['entity'])
    print(f"   ✓ Created device: {sensor['entity']['name']} (ID: {sensor['entity']['id']})")
    
    # 3. Search for entities
    print("\n3. Searching for entities:")
    
    search_results = client.search_entities("smart")
    print(f"   Search for 'smart': Found {search_results['count']} results")
    for result in search_results['results'][:2]:
        print(f"     - {result['entity']['name']} (score: {result['score']:.2f})")
    
    # 4. Execute MCP tools
    print("\n4. Executing MCP tools:")
    
    # Create a relationship
    try:
        rel_result = client.execute_tool(
            "create_relationship",
            {
                "from_entity_id": light['entity']['id'],
                "to_entity_id": living_room['entity']['id'],
                "relationship_type": "located_in",
                "properties": {"position": "ceiling center"}
            }
        )
        print("   ✓ Created relationship: device located_in room")
    except Exception as e:
        print(f"   ✗ Failed to create relationship: {e}")
    
    # Get devices in room
    try:
        devices_result = client.execute_tool(
            "get_devices_in_room",
            {"room_id": living_room['entity']['id']}
        )
        print(f"   ✓ Found {devices_result['result']['count']} devices in {living_room['entity']['name']}")
    except Exception as e:
        print(f"   ✗ Failed to get devices: {e}")
    
    # 5. Get graph statistics
    print("\n5. Graph Statistics:")
    stats = client.get_graph_stats()
    print(f"   - Total entities: {stats['total_entities']}")
    print(f"   - Total relationships: {stats['total_relationships']}")
    print(f"   - Entity types: {json.dumps(stats.get('entity_types', {}), indent=6)}")
    
    # 6. Clean up (optional)
    print("\n6. Demo complete!")
    print(f"   Created {len(entities)} entities for testing")
    print("   Use 'oook interactive' to explore the graph further")
    
    return entities


def demo_advanced_queries(entities):
    """Demonstrate advanced query operations"""
    
    client = MCPClient("http://localhost:8000")
    
    print("\n=== Advanced Query Demo ===\n")
    
    # Find similar entities
    if entities:
        entity_id = entities[0]['id']
        try:
            similar = client.execute_tool(
                "find_similar_entities",
                {
                    "entity_id": entity_id,
                    "threshold": 0.5,
                    "limit": 5
                }
            )
            print(f"1. Similar entities to '{entities[0]['name']}':")
            for sim in similar.get('result', {}).get('similar_entities', []):
                print(f"   - {sim['entity']['name']} (score: {sim['score']:.2f})")
        except Exception as e:
            print(f"   Error finding similar entities: {e}")
    
    # Test path finding
    if len(entities) >= 2:
        try:
            path = client.execute_tool(
                "find_path",
                {
                    "from_entity_id": entities[0]['id'],
                    "to_entity_id": entities[1]['id'],
                    "max_depth": 5
                }
            )
            if path.get('result', {}).get('found'):
                print(f"\n2. Path from '{entities[0]['name']}' to '{entities[1]['name']}':")
                for step in path['result']['path']:
                    print(f"   → {step['name']} ({step['type']})")
            else:
                print(f"\n2. No path found between entities")
        except Exception as e:
            print(f"   Error finding path: {e}")


if __name__ == "__main__":
    try:
        # Run the demo
        entities = demo_mcp_operations()
        
        # Optional: Run advanced queries
        # demo_advanced_queries(entities)
        
    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure the FunkyGibbon server is running on http://localhost:8000")