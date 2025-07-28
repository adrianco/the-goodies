# The Goodies - Quick Start Guide

Get up and running with The Goodies smart home knowledge graph system in under 30 minutes!

## Prerequisites Checklist

- [ ] macOS 13+ with Xcode 15+ (for Swift development)
- [ ] Python 3.11+ installed
- [ ] PostgreSQL 14+ installed and running
- [ ] Redis 7+ installed and running
- [ ] Node.js 18+ (for MCP tools)
- [ ] Git configured

## 🚀 5-Minute Setup

### 1. Clone and Setup (2 minutes)

```bash
# Clone the repository
git clone https://github.com/adrianco/the-goodies.git
cd the-goodies

# Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install MCP CLI
npm install -g @modelcontextprotocol/cli
```

### 2. Database Quick Setup (2 minutes)

```bash
# Start PostgreSQL and Redis
brew services start postgresql@14
brew services start redis

# Create databases
createdb funkygibbon_dev
createdb funkygibbon_test

# Quick test
psql funkygibbon_dev -c "SELECT 1;"
redis-cli ping
```

### 3. Install Dependencies (1 minute)

```bash
# Python dependencies
cd FunkyGibbon
pip install poetry
poetry install

# Swift dependencies
cd ../WildThing
swift package resolve
```

## 🏗️ Quick Development Start

### Option A: Full Stack Development (15 minutes)

#### 1. Start FunkyGibbon Backend

```bash
cd FunkyGibbon

# Run with Docker Compose (recommended)
docker-compose up

# OR run locally
poetry shell
alembic upgrade head
uvicorn funkygibbon.api.main:app --reload
```

Backend will be available at: http://localhost:8000
API docs at: http://localhost:8000/docs

#### 2. Build WildThing Swift Package

```bash
cd WildThing

# Build for current platform
swift build

# Run tests
swift test

# Build for iOS
xcodebuild -scheme WildThing -sdk iphoneos
```

#### 3. Test Basic Functionality

```bash
# Test API health
curl http://localhost:8000/health

# Create a test entity
curl -X POST http://localhost:8000/api/entities/ \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "home",
    "version": "v1",
    "content": {"name": "My Test Home"},
    "user_id": "test-user",
    "source_type": "manual"
  }'
```

### Option B: Backend Only (10 minutes)

```bash
cd FunkyGibbon

# Quick setup script
cat > quickstart.sh << 'EOF'
#!/bin/bash
poetry install
poetry run alembic upgrade head
poetry run python -m funkygibbon.scripts.seed_data
poetry run uvicorn funkygibbon.api.main:app --reload
EOF

chmod +x quickstart.sh
./quickstart.sh
```

### Option C: iOS/Swift Only (10 minutes)

```bash
cd WildThing

# Create test app
swift package init --type executable --name TestApp

# Add WildThing dependency
cat >> Package.swift << 'EOF'
dependencies: [
    .package(path: "../WildThing")
],
targets: [
    .executableTarget(
        name: "TestApp",
        dependencies: ["WildThing"])
]
EOF

# Run test app
swift run TestApp
```

## 📱 Integration Examples

### Swift/iOS Integration

```swift
// In your iOS app
import WildThing

// Initialize storage
let storage = try SQLiteStorage()

// Create MCP server
let mcpServer = WildThingMCPServer(storage: storage)

// Start server
Task {
    try await mcpServer.start()
}

// Create an entity
let home = HomeEntity(
    content: ["name": "My Smart Home"],
    userId: "user-123",
    sourceType: .manual
)

try await storage.save(home)
```

### Python Backend Usage

```python
# Quick entity creation
from funkygibbon.core.entities import HomeEntity
from funkygibbon.core.models import SourceType

# Create entity
home = HomeEntity(
    version="v1",
    content={"name": "My Home"},
    user_id="user-123",
    source_type=SourceType.MANUAL
)

# Use with FastAPI
@app.post("/quick-create")
async def quick_create():
    # Your logic here
    pass
```

### Sync Example

```bash
# Trigger sync from command line
curl -X POST http://localhost:8000/api/sync/ \
  -H "Content-Type: application/json" \
  -d '{
    "protocol_version": "inbetweenies-v1",
    "device_id": "test-device",
    "user_id": "test-user",
    "session_id": "test-session",
    "vector_clock": {},
    "changes": []
  }'
```

## 🧪 Quick Testing

### 1. Unit Tests (2 minutes)

```bash
# Python tests
cd FunkyGibbon
poetry run pytest tests/unit -v

# Swift tests
cd WildThing
swift test
```

### 2. Integration Test (3 minutes)

```bash
# Start test environment
docker-compose -f docker-compose.test.yml up -d

# Run integration tests
poetry run pytest tests/integration -v

# Cleanup
docker-compose -f docker-compose.test.yml down
```

### 3. End-to-End Test (5 minutes)

Create a test script:

```python
# test_e2e.py
import asyncio
import httpx

async def test_full_flow():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Create entity
        create_resp = await client.post("/api/entities/", json={
            "entity_type": "home",
            "version": "v1",
            "content": {"name": "Test Home"},
            "user_id": "test-user",
            "source_type": "manual"
        })
        print(f"Created: {create_resp.json()}")
        
        # 2. Sync
        sync_resp = await client.post("/api/sync/", json={
            "protocol_version": "inbetweenies-v1",
            "device_id": "test-device",
            "user_id": "test-user",
            "session_id": "test-session",
            "vector_clock": {},
            "changes": []
        })
        print(f"Synced: {sync_resp.json()}")

asyncio.run(test_full_flow())
```

## 🔧 Common Quick Fixes

### PostgreSQL Connection Issues

```bash
# Check PostgreSQL is running
pg_isready

# Reset password if needed
psql postgres -c "ALTER USER postgres PASSWORD 'postgres';"
```

### Redis Connection Issues

```bash
# Check Redis is running
redis-cli ping

# Clear Redis if needed
redis-cli FLUSHALL
```

### Swift Build Issues

```bash
# Clean build
swift package clean
swift build

# Reset package cache
rm -rf .build
swift package resolve
```

### Python Import Issues

```bash
# Reinstall dependencies
poetry install --no-cache

# Check Python version
python --version  # Should be 3.11+
```

## 📚 Quick Reference

### API Endpoints

- `GET /health` - Health check
- `POST /api/entities/` - Create entity
- `GET /api/entities/{id}` - Get entity
- `PUT /api/entities/{id}` - Update entity
- `DELETE /api/entities/{id}` - Delete entity
- `POST /api/sync/` - Sync data
- `GET /api/mcp/tools` - List MCP tools

### Entity Types

- `home` - Home entity
- `room` - Room entity
- `device` - Device entity
- `accessory` - Accessory entity
- `service` - Service entity
- `automation` - Automation entity

### MCP Tools

- `create_entity` - Create new entity
- `query_graph` - Query home graph
- `update_entity` - Update entity
- `delete_entity` - Delete entity
- `sync_now` - Trigger sync

## 🚦 Next Steps

1. **Explore the API**: Visit http://localhost:8000/docs
2. **Read Architecture**: See `/architecture/SYSTEM_ARCHITECTURE.md`
3. **Try Examples**: Check `/examples` directory
4. **Join Development**: See `CONTRIBUTING.md`

## 🆘 Quick Help

### Get Help

```bash
# API documentation
open http://localhost:8000/docs

# Check logs
docker-compose logs -f funkygibbon

# Database console
psql funkygibbon_dev

# Redis console
redis-cli
```

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with verbose output
uvicorn funkygibbon.api.main:app --reload --log-level debug
```

### Reset Everything

```bash
# Stop all services
docker-compose down -v

# Clean databases
dropdb funkygibbon_dev
createdb funkygibbon_dev

# Clear Redis
redis-cli FLUSHALL

# Restart
docker-compose up
```

## 🎯 Quick Wins

### 1. Create Your First Home (1 minute)

```python
# create_home.py
import requests

response = requests.post("http://localhost:8000/api/entities/", json={
    "entity_type": "home",
    "version": "v1",
    "content": {
        "name": "My Smart Home",
        "address": "123 Main St"
    },
    "user_id": "demo-user",
    "source_type": "manual"
})

print(f"Created home: {response.json()}")
```

### 2. Import from HomeKit (5 minutes)

```swift
// In iOS app with WildThing
import HomeKit

let bridge = HomeKitBridge(storage: storage)
try await bridge.importHomes()
print("HomeKit import complete!")
```

### 3. Setup Basic Automation (3 minutes)

```python
# Create automation entity
automation = {
    "entity_type": "automation",
    "version": "v1",
    "content": {
        "name": "Sunset Lights",
        "trigger": "sunset",
        "actions": ["turn_on_lights"]
    },
    "user_id": "demo-user",
    "source_type": "manual"
}

response = requests.post("http://localhost:8000/api/entities/", json=automation)
```

## 🎉 Congratulations!

You now have The Goodies running! Here's what you can do:

- ✅ Create and manage smart home entities
- ✅ Sync between devices
- ✅ Query your home graph
- ✅ Integrate with HomeKit
- ✅ Use MCP tools for AI integration

For detailed implementation, see:
- [Implementation Guide](implementation-guide.md)
- [WildThing Development](wildthing-development-steps.md)
- [FunkyGibbon Development](funkygibbon-development-steps.md)

Happy coding! 🚀