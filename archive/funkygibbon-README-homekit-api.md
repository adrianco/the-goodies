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

2. Populate the database and run the server:
```bash
# Option A: Run everything from project root (recommended)
cd ..  # go to project root
python funkygibbon/populate_db.py  # Creates DB in project root
python -m funkygibbon              # Uses DB in project root

# Option B: Move database after population
cd funkygibbon
python populate_db.py              # Creates DB in funkygibbon/
mv funkygibbon.db ..               # Move to project root
cd ..
python -m funkygibbon              # Uses DB in project root
```

3. Access the API:
- Root: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## API Endpoints

### Homes (HomeKit HMHome)
- `POST /api/v1/homes/` - Create home
- `GET /api/v1/homes/{id}` - Get home
- `GET /api/v1/homes/` - List homes
- `PUT /api/v1/homes/{id}` - Update home
- `DELETE /api/v1/homes/{id}` - Delete home

### Rooms (HomeKit HMRoom)
- `POST /api/v1/rooms/` - Create room
- `GET /api/v1/rooms/{id}` - Get room
- `GET /api/v1/rooms/?home_id={id}` - List rooms
- `PUT /api/v1/rooms/{id}` - Update room
- `DELETE /api/v1/rooms/{id}` - Delete room

### Accessories (HomeKit HMAccessory)
- `POST /api/v1/accessories/` - Create accessory
- `GET /api/v1/accessories/{id}` - Get accessory
- `GET /api/v1/accessories/?home_id={id}` - List accessories
- `PUT /api/v1/accessories/{id}` - Update accessory
- `DELETE /api/v1/accessories/{id}` - Delete accessory

### Services (HomeKit HMService)
- `POST /api/v1/services/` - Create service
- `GET /api/v1/services/{id}` - Get service
- `GET /api/v1/services/?accessory_id={id}` - List services
- `DELETE /api/v1/services/{id}` - Delete service

### Characteristics (HomeKit HMCharacteristic)
- `GET /api/v1/characteristics/{id}` - Get characteristic
- `PUT /api/v1/characteristics/{id}/value` - Update value

### Users (HomeKit HMUser)
- `POST /api/v1/users/` - Create user
- `GET /api/v1/users/{id}` - Get user
- `GET /api/v1/users/?home_id={id}` - List users
- `PUT /api/v1/users/{id}` - Update user
- `DELETE /api/v1/users/{id}` - Delete user

### Sync (Inbetweenies Protocol)
- `POST /api/v1/sync/request` - Request sync delta from server
- `POST /api/v1/sync/push` - Push changes to server
- `POST /api/v1/sync/ack` - Acknowledge sync completion

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
├── api/            # FastAPI endpoints
│   └── routers/    # API route handlers
├── repositories/   # Data access layer
├── sync/           # Sync protocol implementation
├── tests/          # Test suite
└── __main__.py     # Server entry point

inbetweenies/       # Shared models package
├── models/         # HomeKit-compatible SQLAlchemy models
├── sync/           # Sync protocol utilities
└── __init__.py
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