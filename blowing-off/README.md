# Blowing-Off: Python Client

Blowing-Off is the Python client for The Goodies smart home system — a reference
implementation of the inbetweenies-v2 protocol. The maintained port is
**KittenKong** (TypeScript, `rolandcanyon-cmd/the-goodies-typescript`); the
earlier Swift port (*WildThing*) is abandoned.

## Features

- **Local SQLite cache** of the Entity/Relationship knowledge graph (shared
  inbetweenies models)
- **Inbetweenies-v2 sync** — bidirectional, with a `server_time` delta watermark,
  the canonical conflict resolver (last-write-wins + version tiebreak), and
  tombstone deletes
- **MCP server** — exposes the 12 knowledge-graph tools to MCP clients
  (`python -m blowingoff.mcp.server`), mirroring KittenKong
- **CLI interface** for connecting, syncing, and running tools
- **Offline support** — queue changes and sync when reconnected

## Installation

```bash
# From the blowing-off directory
cd blowing-off

# Set PYTHONPATH to include parent directory for inbetweenies
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH

# Install dependencies
pip install -e ../inbetweenies  # Install inbetweenies package
pip install -e .                # Install blowing-off client

# This installs the 'blowingoff' command globally
```

## Quick Start

### 1. Connect to Server

```bash
blowing-off connect \
  --server-url http://localhost:8000 \
  --auth-token your-token-here
```

### 2. Sync Data

```bash
# Manual sync
blowing-off sync

# Background sync daemon
blowing-off sync-daemon --interval 30
```

## MCP Server

Blowing-Off also runs as a stdio **MCP server**, exposing the 12 knowledge-graph
tools (search_entities, get_entity_details, create_entity, update_entity,
create_relationship, get_devices_in_room, find_device_controls,
get_room_connections, find_path, find_similar_entities, get_procedures_for_device,
get_automations_in_room) to any MCP client. On startup it connects to FunkyGibbon,
syncs the graph into the local cache, and keeps it fresh in the background.

```bash
python -m blowingoff.mcp.server      # or the `blowingoff-mcp` console script
```

Configuration (environment): `FUNKYGIBBON_URL`, `FUNKYGIBBON_AUTH_TOKEN`
(preferred) or `FUNKYGIBBON_PASSWORD`, `SYNC_INTERVAL_SECONDS`, `BLOWINGOFF_DB`.
Example Claude Code `mcpServers` entry:

```json
"blowingoff": {
  "command": "python", "args": ["-m", "blowingoff.mcp.server"],
  "env": {"FUNKYGIBBON_URL": "http://localhost:8000", "FUNKYGIBBON_AUTH_TOKEN": "<token>"}
}
```

### 3. View Data

```bash
# Show home info
blowing-off home show

# List rooms
blowing-off room list

# List devices (accessories)
blowing-off device list

# Show device state
blowing-off device state device-123
```

### 4. Create Entities

```bash
# Create home
blowing-off home create \
  --name "My Home" \
  --primary

# Create room
blowing-off room create \
  --home-id home-1 \
  --name "Living Room"

# Create device (accessory)
blowing-off device create \
  --room-id room-123 \
  --name "Ceiling Light" \
  --type light \
  --manufacturer "Philips"
```

### 5. Update State

```bash
# Set device state
blowing-off device set-state device-123 '{"power": "on", "brightness": 80}'
```

## Python API

```python
from blowingoff.client import BlowingOffClient

# Initialize client
client = BlowingOffClient("my-home.db")
await client.connect("http://localhost:8000", "auth-token")

# Sync with server
result = await client.sync()
print(f"Synced {result.synced_entities} entities")

# Get data
home = await client.get_home()
rooms = await client.get_rooms()
devices = await client.get_devices()

# Update device state
await client.update_device_state(
    "device-123",
    {"power": "on", "brightness": 80}
)

# Start background sync
await client.start_background_sync(interval=30)
```

## Architecture

### Local Database Schema

The client uses the shared Inbetweenies models:
- Home, Room, Accessory, Service, Characteristic, User models
- HomeKit-compatible structure
- Sync metadata fields (sync_id, updated_at)

### Sync Process

1. **Fetch Server Changes**: Get all changes since last sync
2. **Apply Server Changes**: Update local database
3. **Push Local Changes**: Send pending changes to server
4. **Resolve Conflicts**: Handle any conflicts with last-write-wins
5. **Acknowledge Sync**: Confirm successful completion

### Conflict Resolution

- Compares `updated_at` timestamps
- Uses `sync_id` as tiebreaker within 1 second
- Deletes always win over updates
- All conflicts reported to client

## Testing

```bash
# Run unit tests
pytest blowing-off/tests/unit

# Run integration tests (requires server)
pytest blowing-off/tests/integration

# Run with coverage
pytest --cov=blowing_off blowing-off/tests
```

## Configuration

Connection info is stored in `.blowing-off.json`:

```json
{
  "server_url": "http://localhost:8000",
  "auth_token": "your-token",
  "client_id": "generated-uuid",
  "db_path": "blowing-off.db"
}
```

## Troubleshooting

### Sync Failures

Check sync status:
```bash
blowing-off status
```

View sync errors in the database:
```sql
SELECT * FROM sync_metadata;
```

### Database Issues

Reset local database:
```bash
rm blowing-off.db
blowing-off connect --server-url ... --auth-token ...
```

### Debug Mode

Enable SQL logging:
```python
client = BlowingOffClient(echo=True)
```

## Performance

- Sync latency: <500ms for typical home
- Memory usage: <50MB
- Supports 300+ entities
- Batch sync for efficiency

## Development

The client serves as a reference for Swift/WildThing implementation:
- Same data models and sync logic
- Similar API surface
- Comparable performance targets
- Identical conflict resolution