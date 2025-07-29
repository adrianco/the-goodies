# Blowing-Off: Python Test Client

Blowing-Off is a Python test client for The Goodies smart home system. It implements the same functionality as the eventual Swift/WildThing code, serving as a validation tool and reference implementation.

## Features

- **Local SQLite Storage**: Mirror of server-side schema with sync metadata
- **Inbetweenies Protocol**: Full bidirectional sync implementation
- **Offline Support**: Queue changes and sync when reconnected
- **Conflict Resolution**: Last-write-wins with timestamp comparison
- **CLI Interface**: Command-line tools for testing and management
- **Observable Pattern**: Register callbacks for state changes

## Installation

```bash
cd blowing-off
pip install -e .
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

### 3. View Data

```bash
# Show house info
blowing-off house show

# List rooms
blowing-off room list

# List devices
blowing-off device list

# Show device state
blowing-off device state device-123
```

### 4. Create Entities

```bash
# Create room
blowing-off room create \
  --house-id house-1 \
  --name "Living Room" \
  --floor 0 \
  --type living_room

# Create device  
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
from blowing_off import BlowingOffClient

# Initialize client
client = BlowingOffClient("my-home.db")
await client.connect("http://localhost:8000", "auth-token")

# Sync with server
result = await client.sync()
print(f"Synced {result.synced_entities} entities")

# Get data
house = await client.get_house()
rooms = await client.get_rooms()
devices = await client.get_devices()

# Update device state
await client.update_device_state(
    "device-123",
    {"power": "on", "brightness": 80}
)

# Register observer
async def on_change(event_type, data):
    print(f"Change: {event_type} - {data}")
    
await client.observe_changes(on_change)

# Start background sync
await client.start_background_sync(interval=30)
```

## Architecture

### Local Database Schema

The client maintains a local SQLite database with:
- All entity tables (houses, rooms, devices, users, states, events)
- Sync metadata tracking (timestamps, status, conflicts)
- Local change tracking for offline support

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