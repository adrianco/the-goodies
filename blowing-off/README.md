# Blowing-Off: Python Test Client

Blowing-Off is a Python test client for The Goodies smart home system. It implements the same functionality as the eventual Swift/WildThing code, serving as a validation tool and reference implementation.

## Features

- **Local SQLite Storage**: Uses shared Inbetweenies models
- **Inbetweenies Protocol**: Full bidirectional sync implementation
- **Offline Support**: Queue changes and sync when reconnected
- **Conflict Resolution**: Last-write-wins with timestamp comparison
- **CLI Interface**: Command-line tools for testing and management
- **HomeKit Compatible**: Works with simplified HomeKit-style models

## Installation

```bash
# From the blowing-off directory
cd blowing-off
pip install -e .

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