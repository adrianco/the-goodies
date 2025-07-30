# 🏠 FunkyGibbon - Human Testing Guide

A step-by-step guide to get FunkyGibbon running with the new Phase 2 graph operations and MCP (Model Context Protocol) functionality.

## 📋 Prerequisites

- Python 3.11 or higher
- pip package manager
- curl (for testing API endpoints)

## 🚀 Quick Start Guide

Follow these steps in order:

### Step 1: Navigate to Project Root
```bash
cd /workspaces/the-goodies
pwd
# Should output: /workspaces/the-goodies
```

### Step 2: Set Up Virtual Environment (Recommended)
```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
source venv/bin/activate  # On Linux/Mac
# OR
venv\Scripts\activate     # On Windows

# You should see (venv) in your terminal prompt

# Set Python path to include project root (IMPORTANT!)
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH
```

### Step 3: Install Dependencies
```bash
# Install FunkyGibbon dependencies
cd funkygibbon
pip install -r requirements.txt
cd ..

# Install Oook CLI for testing MCP tools
cd oook
pip install -e .
cd ..

# Also install blowing-off dependencies if testing the client
cd blowing-off
pip install -e .
cd ..
```

### Step 4: Populate the Database with Test Data (Optional but Recommended)

Before starting the server, you can populate the database with comprehensive test data:

```bash
# Run the population script
cd /workspaces/the-goodies
python funkygibbon/populate_graph_db.py
```

This script creates:
- 1 Home (The Martinez Smart Home)
- 3 Zones (Ground Floor, Upper Floor, Outdoor Areas)
- 6 Rooms (Living Room, Kitchen, Dining Room, Master Bedroom, Home Office, Garage)
- 1 Door (Kitchen-Dining Door)
- 6 Devices (TV, Thermostat, Refrigerator, Oven, Lights, Doorbell)
- 2 Procedures (TV Setup, Thermostat Schedule)
- 1 Manual (TV User Manual)
- 2 Automations (Good Morning Routine, Movie Time Scene)
- 1 Schedule (Vacation Mode)
- 2 Notes (WiFi Configuration, HVAC Maintenance)
- 30+ Relationships connecting all entities

### Step 5: Start the FunkyGibbon Server
```bash
# From project root with PYTHONPATH set
export PYTHONPATH=/workspaces/the-goodies
python -m funkygibbon
```

Expected output:
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
DEBUG: Starting server with DATABASE_URL=sqlite+aiosqlite:///./funkygibbon.db
Database initialized
```

### Step 6: Test the Graph Operations API

Open a new terminal and run these commands:

#### Test Health Endpoint
```bash
curl http://localhost:8000/health
# Output: {"status":"healthy"}
```

#### Test Graph Statistics
```bash
curl http://localhost:8000/api/v1/graph/statistics
```

Expected output (if you ran the population script):
```json
{
  "total_entities": 25,
  "total_relationships": 35,
  "entity_types": {
    "home": 1,
    "room": 6,
    "device": 6,
    "zone": 3,
    "door": 1,
    "procedure": 2,
    "manual": 1,
    "note": 2,
    "schedule": 1,
    "automation": 2
  },
  "relationship_types": {
    "part_of": 9,
    "located_in": 11,
    "connects_to": 3,
    "monitors": 1,
    "procedure_for": 2,
    "documented_by": 3,
    "automates": 2,
    "controls": 2,
    "manages": 2
  },
  "average_degree": 2.80,
  "isolated_entities": 0
}
```

### Step 7: Use Oook CLI for Testing

The Oook CLI is a powerful tool for testing the MCP server and graph operations.

#### List Available MCP Tools
```bash
oook tools
```

This will show all 12 available MCP tools in a nice table format.

#### View Populated Data Statistics
```bash
oook stats
```

After running the population script, you should see:
```
Total Entities: 25
Total Relationships: 35
Average Degree: 2.80
Isolated Entities: 0

Entity Types:
  • home: 1
  • room: 6
  • device: 6
  • zone: 3
  • door: 1
  • procedure: 2
  • manual: 1
  • note: 2
  • schedule: 1
  • automation: 2
```

#### Search for Entities
```bash
# Search for all "smart" devices
oook search "smart"

# Search only in rooms
oook search "room" -t room

# Find specific entity
oook search "Living Room" -t room
```

#### Test Graph Operations
```bash
# Get devices in a specific room (use room ID from search)
oook execute get_devices_in_room -a room_id="<room-id>"

# Find path between entities
oook execute find_path -a from_entity_id="<device-id>" -a to_entity_id="<home-id>"

# Get entity details
oook execute get_entity_details -a entity_id="<entity-id>"
```

#### Create Additional Entities
```bash
# Create a new room
oook create room "Guest Bedroom" -c '{"area": 20, "floor": 2}'

# Create a new device
oook create device "Security Camera" -c '{"manufacturer": "Arlo", "model": "Pro 4", "capabilities": ["video", "motion", "night_vision"]}'
```

#### Create Relationships Between Entities
```bash
# First, get entity IDs from search results
# Then create relationships

# Example: Device located in room
oook execute create_relationship \
  -a from_entity_id="<device-id>" \
  -a to_entity_id="<room-id>" \
  -a relationship_type="located_in" \
  -a properties='{"position": "wall mounted"}'

# Example: Room part of home  
oook execute create_relationship \
  -a from_entity_id="<room-id>" \
  -a to_entity_id="<home-id>" \
  -a relationship_type="part_of"
```

### Step 8: Test with Example Script

Run the provided test script for additional testing:
```bash
cd oook
python examples/simple_test.py
```

This will create additional entities, relationships, and verify all functionality works correctly.

## 🔧 MCP Tools Reference

The following MCP tools are available:

1. **get_devices_in_room** - Find all devices in a specific room
2. **find_device_controls** - Get available controls for a device
3. **get_room_connections** - Find connections between rooms
4. **search_entities** - Full-text search across entities
5. **create_entity** - Create new entities in the graph
6. **create_relationship** - Link entities together
7. **find_path** - Find shortest path between entities
8. **get_entity_details** - Get comprehensive entity information
9. **find_similar_entities** - Find entities similar to a given one
10. **get_procedures_for_device** - Get procedures/manuals for devices
11. **get_automations_in_room** - Find automations affecting a room
12. **update_entity** - Update entity (creates new version)

## 📊 Entity Types

The system supports these entity types:
- HOME - Top-level container
- ROOM - Spaces within homes
- DEVICE - Smart devices and appliances
- ZONE - Logical groupings of rooms
- DOOR - Connections between rooms
- WINDOW - External connections
- PROCEDURE - Step-by-step instructions
- MANUAL - Device documentation
- NOTE - User annotations
- SCHEDULE - Time-based rules
- AUTOMATION - Event-based rules

## 🔗 Relationship Types

Valid relationships between entities:
- LOCATED_IN - Physical containment (device→room, room→home)
- CONTROLS - Control relationships (device→device, automation→device)
- CONNECTS_TO - Physical connections (room→room, door→room)
- PART_OF - Logical grouping (room→zone, zone→home)
- DOCUMENTED_BY - Documentation links (device→manual)
- PROCEDURE_FOR - Procedure associations
- TRIGGERED_BY - Event triggers
- MANAGES - Management relationships
- MONITORS - Monitoring relationships
- AUTOMATES - Automation targets

## 🎯 Interactive Mode

Oook provides an interactive mode for exploration:

```bash
oook interactive
```

In interactive mode, you can:
- Use arrow keys to navigate history
- Tab completion for commands
- Type 'help' for available commands
- Type 'exit' to quit

## 📋 Example Outputs

### Search Results Example
When you run `oook search "smart"`, you'll see output like:
```
Search Results for 'smart':

╭────────────────────────── The Martinez Smart Home ───────────────────────────╮
│ Name: The Martinez Smart Home                                                │
│ Type: home                                                                   │
│ ID: aeb2b8bb-dd32-4c99-ace6-08db0bf64d39                                     │
│ Score: 4.50                                                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
Highlights:
  • Name: The Martinez Smart Home
  • address: 456 Innovation Drive, Smart City, SC 90210...

Found 5 results
```

### Device Query Example
Running `oook execute get_devices_in_room -a room_id="cf6a0a08-2c10-4001-9d5b-76b8e34f6a0a"`:
```json
{
  "success": true,
  "result": {
    "room_id": "cf6a0a08-2c10-4001-9d5b-76b8e34f6a0a",
    "devices": [
      {
        "id": "f9fbbb53-8cda-4153-a5ce-b52ba2a48dd9",
        "name": "65\" Smart TV",
        "content": {
          "manufacturer": "Samsung",
          "model": "QN90A",
          "capabilities": ["power", "volume", "input", "apps"]
        }
      }
    ],
    "count": 3
  }
}
```

### Path Finding Example
Finding a path from a device to home shows the relationship chain:
```json
{
  "path": [
    {"id": "device-id", "name": "65\" Smart TV", "type": "device"},
    {"id": "room-id", "name": "Living Room", "type": "room"},
    {"id": "home-id", "name": "The Martinez Smart Home", "type": "home"}
  ],
  "length": 2,
  "found": true
}
```

## 🧪 Advanced Testing Scenarios

### Create a Complete Home Setup
```bash
# Create home
HOME_ID=$(oook create home "Test Home" -c '{"address": "456 Test Ave"}' | grep -o '"id": "[^"]*' | grep -o '[^"]*$')

# Create rooms
ROOM1_ID=$(oook create room "Living Room" -c '{"floor": 1}' | grep -o '"id": "[^"]*' | grep -o '[^"]*$')
ROOM2_ID=$(oook create room "Bedroom" -c '{"floor": 2}' | grep -o '"id": "[^"]*' | grep -o '[^"]*$')

# Create devices
DEVICE1_ID=$(oook create device "Smart Speaker" -c '{"brand": "Amazon"}' | grep -o '"id": "[^"]*' | grep -o '[^"]*$')
DEVICE2_ID=$(oook create device "Smart Bulb" -c '{"brand": "Philips"}' | grep -o '"id": "[^"]*' | grep -o '[^"]*$')

# Create relationships
oook execute create_relationship -a from_entity_id="$ROOM1_ID" -a to_entity_id="$HOME_ID" -a relationship_type="part_of"
oook execute create_relationship -a from_entity_id="$DEVICE1_ID" -a to_entity_id="$ROOM1_ID" -a relationship_type="located_in"
```

### Test Path Finding
```bash
# Find path between two entities
oook execute find_path -a from_entity_id="$DEVICE1_ID" -a to_entity_id="$HOME_ID"
```

### Test Entity Updates (Versioning)
```bash
# Update an entity (creates new version)
oook execute update_entity \
  -a entity_id="$DEVICE1_ID" \
  -a changes='{"name": "Alexa Echo Dot", "content": {"generation": "5th"}}' \
  -a user_id="test-user"
```

## 🔧 Troubleshooting

### Server Issues
```bash
# Check if port 8000 is already in use
lsof -i :8000

# Kill any existing FunkyGibbon processes
pkill -f "python -m funkygibbon"

# Check server logs
tail -f /tmp/funkygibbon.log
```

### Database Issues
```bash
# The SQLite database is created as funkygibbon.db
ls -la funkygibbon.db

# To reset the database
rm -f funkygibbon.db*
# Then restart the server
```

### Oook CLI Issues
```bash
# If oook command not found
python -m oook.cli --help

# Check server connection
oook tools  # Should list all MCP tools
```

## 📝 API Endpoints

### Graph Operations
- `GET /api/v1/graph/statistics` - Graph statistics
- `POST /api/v1/graph/entities` - Create entity
- `GET /api/v1/graph/entities/{id}` - Get entity
- `POST /api/v1/graph/relationships` - Create relationship
- `POST /api/v1/graph/search` - Search entities

### MCP Tools
- `GET /api/v1/mcp/tools` - List all tools
- `POST /api/v1/mcp/tools/{tool_name}` - Execute a tool

### Legacy HomeKit Endpoints (still available)
- `GET /api/v1/homes/` - List homes
- `GET /api/v1/rooms/` - List rooms
- `GET /api/v1/accessories/` - List accessories
- `GET /api/v1/users/` - List users

## 🌟 What's New in Phase 2

1. **Knowledge Graph**: Flexible entity-relationship model beyond HomeKit
2. **MCP Protocol**: Standardized tool interface for AI assistants
3. **Immutable Versioning**: Every change creates a new version
4. **Graph Operations**: Path finding, similarity search, subgraph extraction
5. **Full-Text Search**: Search across entity names and content
6. **Oook CLI**: Powerful testing tool for MCP operations
7. **Population Script**: Comprehensive test data generator (populate_graph_db.py)

## 🔄 Phase 3: Enhanced Sync Protocol

Phase 3 adds the enhanced Inbetweenies synchronization protocol with:

### Features
- **Full Entity & Relationship Sync**: Complete graph synchronization
- **Immutable Version History**: Track all changes with parent versions
- **Advanced Conflict Resolution**: Multiple strategies (merge, last-write-wins, manual)
- **Delta Synchronization**: Efficient partial updates
- **Vector Clocks**: Distributed state tracking

### Sync API Endpoints

#### Check Sync Status
```bash
curl "http://localhost:8000/api/v1/sync/status?device_id=my-device"
```

Response:
```json
{
  "device_id": "my-device",
  "last_sync": "2025-07-30T22:00:00Z",
  "protocol_version": "inbetweenies-v2"
}
```

#### Perform Full Sync
```bash
curl -X POST http://localhost:8000/api/v1/sync/ \
  -H "Content-Type: application/json" \
  -d '{
    "protocol_version": "inbetweenies-v2",
    "device_id": "my-device",
    "user_id": "test-user",
    "sync_type": "full",
    "vector_clock": {"clocks": {}},
    "changes": []
  }'
```

### Sync Client Usage (Python)

```python
from blowing_off.sync.client import EnhancedSyncClient, SyncType

# Initialize client
client = EnhancedSyncClient("http://localhost:8000", device_id="my-device")

# Perform full sync
progress = await client.full_sync()
print(f"Synced {progress.synced_entities} entities")

# Delta sync with filtering
from datetime import datetime, timedelta
since = datetime.now() - timedelta(hours=1)
progress = await client.sync_entities(since=since)

# Handle conflicts
await client.resolve_conflicts(strategy=ConflictStrategy.MERGE)
```

### Version Management

The system maintains complete version history:

```python
# Every change creates a new version
entity.version = "2025-07-30T22:00:00.000000Z-user123"

# Track parent versions for merge history
entity.parent_versions = ["v1", "v2"]  # This entity merges v1 and v2
```

### Conflict Resolution Strategies

1. **Last Write Wins**: Most recent update wins
2. **Merge**: Intelligently merge non-conflicting changes
3. **Manual**: Queue for user resolution
4. **Client/Server Wins**: Force one side to win
5. **Custom**: Entity-type specific rules

### Testing Sync

A test script is provided to demonstrate sync functionality:

```bash
cd /workspaces/the-goodies
python funkygibbon/examples/test_sync.py
```

This demonstrates:
- Full and delta sync
- Creating and syncing entities
- Conflict generation and resolution
- Vector clock updates

### 🚀 New: Shared MCP and Graph Functionality

Phase 3 now includes shared code between FunkyGibbon (server) and Blowing-Off (client) for graph operations and MCP tools.

#### Server-Side (FunkyGibbon)

The server now uses shared abstractions from the `inbetweenies` package:

```python
# FunkyGibbon uses SQLGraphOperations for database-backed graph operations
from funkygibbon.repositories.graph_impl import SQLGraphOperations

# MCP tools work the same as before, but now use shared implementation
curl -X POST http://localhost:8000/api/v1/mcp/tools/get_devices_in_room \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"room_id": "living-room-123"}}'
```

#### Client-Side (Blowing-Off)

The client now has local MCP functionality that works offline:

```python
from blowingoff.client import BlowingOffClient

# Initialize client
client = BlowingOffClient("test.db")
await client.connect("http://localhost:8000", "auth-token")

# Sync HomeKit data to local graph
entities, relationships = await client.sync_graph_from_homekit()
print(f"Synced {entities} entities and {relationships} relationships")

# Execute MCP tools locally (works offline!)
result = await client.execute_mcp_tool(
    "get_devices_in_room",
    room_id="living-room-123"
)
print(f"Devices in room: {result}")

# Search entities locally
result = await client.execute_mcp_tool(
    "search_entities",
    query="light",
    entity_types=["device"],
    limit=5
)
print(f"Found {result['result']['count']} lights")

# Create relationships locally
result = await client.execute_mcp_tool(
    "create_relationship",
    from_entity_id="device-123",
    to_entity_id="room-456",
    relationship_type="located_in",
    user_id="local-user"
)

# Demo MCP functionality
await client.demo_mcp_functionality()
```

#### Testing Shared Functionality

1. **Test server MCP tools work as before**:
```bash
cd /workspaces/the-goodies
# Run the populate script first
cd funkygibbon && python populate_graph_db.py && cd ..

# Start server
cd funkygibbon && python -m uvicorn api.app:app --reload

# Test MCP tools
oook execute get_devices_in_room -a room_id="living-room-1"
```

2. **Test client local MCP functionality**:
```python
# In a Python script or interactive session
import asyncio
from blowingoff.client import BlowingOffClient

async def test_local_mcp():
    client = BlowingOffClient("test_local.db")
    
    # Demo creates sample data and tests tools
    await client.demo_mcp_functionality()
    
    # List available tools
    tools = client.get_available_mcp_tools()
    print(f"Available tools: {tools}")

asyncio.run(test_local_mcp())
```

3. **Test sync between server and client graph data**:
```python
# This requires both server running and client connected
async def test_graph_sync():
    client = BlowingOffClient("test_sync.db")
    await client.connect("http://localhost:8000", "test-token")
    
    # Sync HomeKit data to graph format
    entities, rels = await client.sync_graph_from_homekit()
    print(f"Converted {entities} HomeKit entities to graph format")
    
    # Now MCP tools work with HomeKit data
    result = await client.execute_mcp_tool(
        "search_entities",
        query="room"
    )
    print(f"Found rooms: {result}")

asyncio.run(test_graph_sync())
```

#### Benefits of Shared Code

1. **No duplication**: Server and client use the same MCP tool implementations
2. **Offline capability**: Client can use MCP tools without server connection
3. **Consistent behavior**: Same results whether online or offline
4. **Easy testing**: Can test MCP functionality without full server setup
5. **Future Swift implementation**: The abstract interfaces guide the Swift/WildThing implementation

## 🔄 Cleaning Up

When you're done testing:

```bash
# Stop the FunkyGibbon server (Ctrl+C)

# Deactivate virtual environment
deactivate

# Clean up databases
rm -f funkygibbon.db*

# Optional: Remove virtual environment
rm -rf venv
```

Happy testing! 🎉