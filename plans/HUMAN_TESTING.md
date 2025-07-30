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

### Step 4: Start the FunkyGibbon Server
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

### Step 5: Test the Graph Operations API

Open a new terminal and run these commands:

#### Test Health Endpoint
```bash
curl http://localhost:8000/health
# Output: {"status":"healthy"}
```

#### Test Graph Statistics (empty initially)
```bash
curl http://localhost:8000/api/v1/graph/statistics
```

Expected output:
```json
{
  "total_entities": 0,
  "total_relationships": 0,
  "entity_types": {},
  "relationship_types": {},
  "average_degree": 0.0,
  "isolated_entities": 0
}
```

### Step 6: Use Oook CLI for Testing

The Oook CLI is a powerful tool for testing the MCP server and graph operations.

#### List Available MCP Tools
```bash
oook tools
```

This will show all 12 available MCP tools in a nice table format.

#### Create Test Entities
```bash
# Create a home
oook create home "Smart Home Demo" -c '{"address": "123 Demo Street", "timezone": "America/Los_Angeles"}'

# Create rooms
oook create room "Living Room" -c '{"area": 35, "floor": 1}'
oook create room "Kitchen" -c '{"area": 25, "floor": 1}'

# Create devices
oook create device "Smart TV" -c '{"manufacturer": "Samsung", "model": "QN90A", "capabilities": ["power", "volume", "input"]}'
oook create device "Smart Light" -c '{"manufacturer": "Philips", "model": "Hue Go", "capabilities": ["power", "brightness", "color"]}'
```

#### Search Entities
```bash
# Search for all entities with "smart" in the name
oook search "smart"

# Search only devices
oook search "light" -t device
```

#### Execute MCP Tools
```bash
# First, get entity IDs from previous commands
# Then create relationships

# Example: Device located in room
oook execute create_relationship \
  -a from_entity_id="<device-id>" \
  -a to_entity_id="<room-id>" \
  -a relationship_type="located_in" \
  -a properties='{"position": "wall mounted"}'
```

#### View Graph Statistics
```bash
oook stats
```

### Step 7: Test with Example Script

Run the provided test script:
```bash
cd oook
python examples/simple_test.py
```

This will create entities, relationships, and verify all functionality works correctly.

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