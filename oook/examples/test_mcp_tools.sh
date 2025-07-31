#!/bin/bash
# Example script demonstrating Oook usage for testing MCP tools

echo "=== Oook MCP Tool Testing Examples ==="
echo

# Check if server is running
echo "1. Listing available MCP tools:"
oook tools

echo -e "\n2. Getting tool details:"
oook tool-info search_entities

echo -e "\n3. Creating test entities:"
# Create a home
oook execute create_entity -a entity_type=home -a name="Test Home" -a content='{"address": "123 Test St"}'

# Create rooms
oook execute create_entity -a entity_type=room -a name="Living Room" -a content='{"area": 30}'
oook execute create_entity -a entity_type=room -a name="Kitchen" -a content='{"area": 20}'

# Create devices
oook execute create_entity -a entity_type=device -a name="Smart Light" -a content='{"type": "bulb", "watts": 10}'
oook execute create_entity -a entity_type=device -a name="Motion Sensor" -a content='{"battery": 100}'

echo -e "\n4. Searching for entities:"
oook search "room"
oook search "smart" -t device

echo -e "\n5. Creating relationships:"
# You'll need to get actual IDs from the create commands above
# This is just an example format
# oook execute create_relationship -a from_entity_id="device-id" -a to_entity_id="room-id" -a relationship_type="located_in"

echo -e "\n6. Getting graph statistics:"
oook stats

echo -e "\n7. Testing complex queries:"
# Find similar entities
# oook execute find_similar_entities -a entity_id="entity-id" -a threshold=0.7

# Find path between entities
# oook execute find_path -a from_entity_id="id1" -a to_entity_id="id2"

echo -e "\nDone! Check the output above for results."