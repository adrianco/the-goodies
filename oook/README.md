# Oook - FunkyGibbon MCP Server CLI

A command-line interface for testing and interacting with the FunkyGibbon MCP (Model Context Protocol) server. Oook provides direct access to MCP tools and graph operations for development and testing purposes.

## Features

- 🔧 Execute MCP tools directly from the command line
- 🔍 Search entities in the knowledge graph
- 📊 View graph statistics and relationships
- 🎯 Interactive mode for exploration
- 🎨 Rich terminal output with syntax highlighting

## Installation

```bash
cd oook
pip install -e .
```

Or install dependencies directly:

```bash
pip install click httpx rich
```

## Usage

### Basic Commands

#### List all available MCP tools
```bash
oook tools
```

#### Get detailed information about a specific tool
```bash
oook tool-info search_entities
```

#### Execute a tool
```bash
# Simple arguments
oook execute search_entities -a query="smart light"

# Multiple arguments
oook execute create_entity -a entity_type=device -a name="Smart Bulb" -a content='{"brightness": 100}'

# JSON arguments
oook execute get_devices_in_room --json-args '{"room_id": "abc123"}'
```

#### Search for entities
```bash
# Basic search
oook search "smart light"

# Filter by entity type
oook search "light" -t device -t automation

# Limit results
oook search "sensor" -l 5
```

#### Create a new entity
```bash
# Simple entity
oook create device "Smart Switch"

# Entity with content
oook create room "Living Room" -c '{"area": 30, "floor": 1}'
```

#### Get entity details
```bash
oook get <entity-id>
```

#### View graph statistics
```bash
oook stats
```

### Interactive Mode

Start an interactive session for exploring the graph:

```bash
oook interactive
```

In interactive mode, you can use these commands:
- `tools` - List all MCP tools
- `tool <name>` - Show tool details
- `exec <tool> <args>` - Execute a tool
- `search <query>` - Search entities
- `get <id>` - Get entity by ID
- `stats` - Show graph statistics
- `exit` - Exit interactive mode

### Server Configuration

By default, Oook connects to `http://localhost:8000`. To use a different server:

```bash
oook --server-url http://example.com:8080 search "device"
```

## Examples

### Device Management

```bash
# Find all devices in a room
oook execute get_devices_in_room -a room_id="living-room-123"

# Create a new device
oook create device "Motion Sensor" -c '{"battery": 100, "sensitivity": "high"}'

# Find device controls
oook execute find_device_controls -a device_id="device-456"
```

### Relationships

```bash
# Create a relationship between entities
oook execute create_relationship \
  -a from_entity_id="device-123" \
  -a to_entity_id="room-456" \
  -a relationship_type="located_in"

# Find path between entities
oook execute find_path \
  -a from_entity_id="device-123" \
  -a to_entity_id="device-789"
```

### Procedures and Documentation

```bash
# Get procedures for a device
oook execute get_procedures_for_device -a device_id="device-123"

# Create a procedure
oook create procedure "Reset Smart Bulb" \
  -c '{"steps": ["Turn off power", "Wait 5 seconds", "Turn on power"]}'
```

## Output Format

Oook uses Rich for beautiful terminal output:
- 🎨 Syntax highlighting for JSON responses
- 📊 Tables for structured data
- 🎯 Colored output for better readability
- 📦 Panels for entity information

## Development

To run Oook in development mode:

```bash
python -m oook.cli --help
```

## Error Handling

Oook provides clear error messages:
- HTTP errors show status codes and response details
- JSON parsing errors highlight the issue
- Connection errors suggest checking the server URL

## Tips

1. Use tab completion (if configured in your shell) for command names
2. Pipe output to `jq` for additional JSON processing
3. Use the interactive mode for exploratory testing
4. Check `oook tools` to discover available operations

## License

MIT License - see LICENSE file for details