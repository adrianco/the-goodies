# FunkyGibbon - Simplified Smart Home Backend

A lightweight Python backend for The Goodies smart home knowledge graph system, designed for single-house deployments with SQLite storage and last-write-wins conflict resolution.

## Features

- **Simple Scale**: Designed for 1 house, ~300 entities, 3-5 users
- **SQLite Storage**: Single file database with optimizations
- **Last-Write-Wins**: Simple timestamp-based conflict resolution
- **REST API**: FastAPI-based endpoints for all entities
- **Type Safety**: Full Python 3.11+ type hints
- **Async/Await**: Modern async architecture throughout

## Quick Start

1. Install dependencies:
```bash
cd funkygibbon
pip install -r requirements.txt
# or with poetry
poetry install
```

2. Run the server:
```bash
python -m funkygibbon.main
# or
uvicorn funkygibbon.main:app --reload
```

3. Access the API:
- Root: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## API Endpoints

### Houses
- `POST /api/v1/houses` - Create house
- `GET /api/v1/houses/{id}` - Get house
- `GET /api/v1/houses` - List houses
- `PUT /api/v1/houses/{id}` - Update house
- `DELETE /api/v1/houses/{id}` - Delete house

### Rooms
- `POST /api/v1/rooms` - Create room
- `GET /api/v1/rooms/{id}` - Get room
- `GET /api/v1/rooms?house_id={id}` - List rooms
- `PUT /api/v1/rooms/{id}` - Update room
- `DELETE /api/v1/rooms/{id}` - Delete room

### Devices
- `POST /api/v1/devices` - Create device
- `GET /api/v1/devices/{id}` - Get device
- `GET /api/v1/devices?room_id={id}` - List devices
- `PUT /api/v1/devices/{id}` - Update device
- `PUT /api/v1/devices/{id}/state` - Update device state
- `DELETE /api/v1/devices/{id}` - Delete device

### Users
- `POST /api/v1/users` - Create user
- `GET /api/v1/users/{id}` - Get user
- `GET /api/v1/users?house_id={id}` - List users
- `PUT /api/v1/users/{id}` - Update user
- `DELETE /api/v1/users/{id}` - Delete user

### Sync
- `POST /api/v1/sync` - Sync entities with conflict resolution
- `GET /api/v1/sync/changes?since={timestamp}` - Get changes

## Configuration

Environment variables:
- `DATABASE_URL` - SQLite connection string (default: `sqlite+aiosqlite:///./funkygibbon.db`)
- `API_HOST` - API host (default: `0.0.0.0`)
- `API_PORT` - API port (default: `8000`)
- `SECRET_KEY` - Secret key for security
- `LOG_LEVEL` - Logging level (default: `INFO`)

## Testing

Run tests:
```bash
pytest tests/
# or specific test
python -m funkygibbon.tests.test_basic
```

## Architecture

```
funkygibbon/
├── models/          # SQLAlchemy models
├── repositories/    # Data access layer
├── api/            # FastAPI endpoints
├── services/       # Business logic (future)
├── cli/            # CLI interface (future)
└── tests/          # Test suite
```

## Conflict Resolution

Uses last-write-wins strategy:
1. Compare `updated_at` timestamps
2. Newer timestamp wins
3. If equal (within 1s), higher `sync_id` wins
4. All conflicts are logged for review

## Performance

Optimized for:
- 300 entities max
- Sub-second response times
- Concurrent read/write operations
- Batch sync operations

## Next Steps

1. Add CLI for management
2. Implement service layer
3. Add WebSocket support for real-time updates
4. Create Swift/WildThing integration
5. Add monitoring and metrics