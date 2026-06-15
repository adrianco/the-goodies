# Human Testing Guide for Blowing-Off Client

This guide provides step-by-step instructions for manually testing the Blowing-Off client to ensure it works correctly with the FunkyGibbon server.

## Prerequisites

- Python 3.10+ installed
- FunkyGibbon server running on localhost:8000
- Two terminal windows (one for server, one for client)

## Installation Steps

### Terminal 1: Start FunkyGibbon Server

```bash
cd /workspaces/the-goodies/funkygibbon
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH
python -m funkygibbon.main
```

Wait for the message: `INFO: Application startup complete.`

### Terminal 2: Install and Run Blowing-Off Client

```bash
cd /workspaces/the-goodies/blowing-off

# Set PYTHONPATH to find inbetweenies
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH

# Install dependencies
pip install -e ../inbetweenies  # Install inbetweenies package
pip install -e .                # Install blowing-off client

# Verify installation
blowingoff --version
```

## Testing Scenarios

### 1. Basic Connection Test

```bash
# Test server health check
blowingoff connect --server-url http://localhost:8000

# Expected output:
# ✅ Connected to server at http://localhost:8000
# Server status: healthy
```

### 2. Initialize Local Database

```bash
# Initialize the local SQLite database
blowingoff init

# Expected output:
# ✅ Local database initialized at ~/.blowingoff/local.db
```

### 3. Create Test Entities

```bash
# Create a home entity
blowingoff entity create --type home --name "Test Home" --content '{"is_primary": true}'

# Create a room entity
blowingoff entity create --type room --name "Living Room" --content '{"floor": 1}'

# Create a device entity
blowingoff entity create --type device --name "Smart Light" --content '{"manufacturer": "Test Corp"}'

# List all entities
blowingoff entity list

# Expected output: List of created entities with IDs and types
```

### 4. Test Synchronization

```bash
# Perform initial sync
blowingoff sync

# Expected output:
# 🔄 Starting sync...
# ↑ Pushing X local changes
# ↓ Pulling Y server changes
# ✅ Sync completed successfully

# Check sync status
blowingoff sync status

# Expected output: Sync statistics and last sync time
```

### 5. Test Conflict Resolution

```bash
# Create an entity
blowingoff entity create --type note --name "Test Note" --content '{"text": "Original"}'

# Sync to server
blowingoff sync

# Modify the same entity locally
blowingoff entity update <entity-id> --content '{"text": "Local change"}'

# Simulate server-side change (in another terminal or via API)
# Then sync again
blowingoff sync

# Expected output: Conflict detection and resolution using last-write-wins
```

### 6. Test MCP Tools

```bash
# List available MCP tools
blowingoff mcp list-tools

# Execute a tool (example: get home status)
blowingoff mcp execute get_home_status

# Expected output: JSON response with home status information
```

### 7. Test Offline Queue

```bash
# Stop the server (Ctrl+C in Terminal 1)

# Create entities while offline
blowingoff entity create --type note --name "Offline Note" --content '{"created": "offline"}'

# Try to sync (should queue changes)
blowingoff sync

# Expected output:
# ⚠️ Server unavailable, changes queued for later sync

# Restart server and sync
# (Start server again in Terminal 1)
blowingoff sync

# Expected output: Queued changes synced successfully
```

### 8. Test Graph Relationships

```bash
# Create entities
blowingoff entity create --type home --name "My Home" --content '{}'
blowingoff entity create --type room --name "Kitchen" --content '{}'

# Create relationship (use IDs from previous commands)
blowingoff relationship create <home-id> <room-id> --type located_in

# View entity with relationships
blowingoff entity show <entity-id> --include-relationships

# Expected output: Entity details with relationships
```

## Troubleshooting

### Common Issues

1. **ModuleNotFoundError: No module named 'inbetweenies'**
   - Solution: Ensure PYTHONPATH is set: `export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH`
   - Also run: `pip install -e ../inbetweenies`

2. **Connection refused on localhost:8000**
   - Solution: Ensure FunkyGibbon server is running in Terminal 1
   - Check server logs for any startup errors

3. **SQLAlchemy async errors**
   - Solution: Install greenlet: `pip install greenlet>=2.0.0`

4. **Command not found: blowingoff**
   - Solution: Reinstall with pip: `pip install -e .`
   - Or use python module directly: `python -m blowingoff.cli`

## Validation Checklist

- [ ] Client can connect to server
- [ ] Local database initializes correctly
- [ ] Entities can be created, read, updated, deleted
- [ ] Sync pushes local changes to server
- [ ] Sync pulls server changes to local
- [ ] Conflicts are detected and resolved
- [ ] Offline changes are queued
- [ ] MCP tools can be executed
- [ ] Graph relationships work correctly

## Clean Up

After testing, you can clean up the local database:

```bash
rm -rf ~/.blowingoff
```

## Notes

- The client uses SQLite for local storage at `~/.blowingoff/local.db`
- All entities use the graph-based model (Entity/EntityRelationship)
- Sync uses the Inbetweenies v2 protocol
- Conflicts are resolved using last-write-wins based on version timestamps