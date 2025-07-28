# The Goodies - Comprehensive Implementation Guide

## Executive Summary

This guide provides a step-by-step approach to implementing The Goodies smart home knowledge graph system. The project consists of three main components:

1. **WildThing** - Swift Package for iOS/macOS client
2. **FunkyGibbon** - Python backend service
3. **Inbetweenies** - Bidirectional sync protocol

## Prerequisites

### Development Environment
- **macOS**: Xcode 15+ (for Swift development)
- **Python**: 3.11+ with virtual environment support
- **Node.js**: 18+ (for MCP tooling)
- **Git**: Version control
- **SQLite**: 3.35+ (usually pre-installed)
- **PostgreSQL**: 14+ (for backend)
- **Redis**: 7+ (for caching)

### Development Tools
```bash
# Install required tools
brew install python@3.11 postgresql@14 redis swift-format swiftlint
pip install poetry pre-commit black flake8 mypy
npm install -g @modelcontextprotocol/cli
```

## Phase 1: Project Setup (Week 1)

### Day 1-2: Repository and Environment Setup

1. **Clone and Initialize Repository**
```bash
git clone https://github.com/adrianco/the-goodies.git
cd the-goodies
git checkout -b development
```

2. **Setup Development Environment**
```bash
# Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Setup pre-commit hooks
pre-commit install

# Initialize Swift package
swift package init --type library --name WildThing
```

3. **Configure IDE**
- Open Xcode for Swift development
- Configure VS Code/PyCharm for Python
- Install recommended extensions

### Day 3-4: Database Setup

1. **PostgreSQL Setup**
```bash
# Start PostgreSQL
brew services start postgresql@14

# Create database
createdb funkygibbon_dev
createdb funkygibbon_test

# Apply migrations
alembic upgrade head
```

2. **Redis Setup**
```bash
# Start Redis
brew services start redis

# Test connection
redis-cli ping
```

3. **SQLite Schema Creation**
```sql
-- Create WildThing local database schema
-- See architecture/SYSTEM_ARCHITECTURE.md for full schema
```

### Day 5: CI/CD Pipeline

1. **GitHub Actions Setup**
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          swift test
          python -m pytest
```

2. **Code Quality Tools**
```bash
# Setup linting
echo "lint:
	swiftlint
	black .
	flake8 .
	mypy ." >> Makefile
```

## Phase 2: Core Data Models (Week 2)

### Day 6-7: WildThing Entity Models

1. **Create Base Entity Protocol**
```swift
// WildThing/Sources/Core/Protocols/WildThingEntity.swift
public protocol WildThingEntity: Codable, Identifiable {
    var id: String { get }
    var version: String { get }
    var entityType: EntityType { get }
    var parentVersions: [String] { get }
    var content: [String: Any] { get set }
    var userId: String { get }
    var sourceType: SourceType { get }
    var createdAt: Date { get }
    var lastModified: Date { get }
}
```

2. **Implement Concrete Entities**
```swift
// WildThing/Sources/Core/Models/HomeEntity.swift
public struct HomeEntity: WildThingEntity {
    public let id: String
    public let version: String
    public let entityType: EntityType = .home
    // ... implement all required properties
}
```

### Day 8-9: FunkyGibbon Models

1. **Create Pydantic Models**
```python
# funkygibbon/core/models.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, List

class HomeEntity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    version: str
    entity_type: EntityType
    parent_versions: List[str] = Field(default_factory=list)
    content: Dict[str, Any]
    user_id: str
    source_type: SourceType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
```

2. **Create Relationship Models**
```python
# funkygibbon/core/relationships.py
class EntityRelationship(BaseModel):
    id: str
    from_entity_id: str
    to_entity_id: str
    relationship_type: RelationshipType
    properties: Dict[str, Any] = Field(default_factory=dict)
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### Day 10: Model Validation and Testing

1. **Unit Tests for Models**
```swift
// WildThing/Tests/Unit/HomeEntityTests.swift
func testEntityCreation() {
    let entity = HomeEntity(
        content: ["name": "My Home"],
        userId: "test-user",
        sourceType: .manual
    )
    XCTAssertNotNil(entity.id)
    XCTAssertEqual(entity.entityType, .home)
}
```

2. **Integration Tests**
```python
# funkygibbon/tests/test_models.py
def test_entity_validation():
    entity = HomeEntity(
        version="v1",
        entity_type=EntityType.HOME,
        content={"name": "Test Home"},
        user_id="test-user",
        source_type=SourceType.MANUAL
    )
    assert entity.id is not None
```

## Phase 3: Storage Implementation (Week 3)

### Day 11-12: SQLite Storage (WildThing)

1. **Implement Storage Protocol**
```swift
// WildThing/Sources/Storage/SQLiteStorage.swift
public class SQLiteStorage: WildThingStorage {
    private let db: SQLiteDatabase
    
    public func save(_ entity: any WildThingEntity) async throws {
        let sql = """
            INSERT OR REPLACE INTO entities 
            (id, version, entity_type, parent_versions, content, 
             user_id, source_type, created_at, last_modified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try await db.execute(sql, parameters: [...])
    }
}
```

2. **Implement Query Methods**
```swift
public func fetch(id: String) async throws -> (any WildThingEntity)? {
    // Implementation
}

public func fetchLatestVersion(id: String) async throws -> (any WildThingEntity)? {
    // Implementation
}
```

### Day 13-14: PostgreSQL Storage (FunkyGibbon)

1. **Create SQLAlchemy Models**
```python
# funkygibbon/storage/postgresql.py
from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class EntityDB(Base):
    __tablename__ = 'entities'
    
    id = Column(String, primary_key=True)
    version = Column(String, primary_key=True)
    entity_type = Column(String, nullable=False)
    parent_versions = Column(JSON, default=list)
    content = Column(JSON, nullable=False)
    user_id = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    last_modified = Column(DateTime, nullable=False)
```

2. **Implement Repository Pattern**
```python
class EntityRepository:
    def __init__(self, session: Session):
        self.session = session
    
    async def save(self, entity: HomeEntity) -> HomeEntity:
        db_entity = EntityDB(**entity.dict())
        self.session.add(db_entity)
        await self.session.commit()
        return entity
```

### Day 15: Caching Layer

1. **Redis Cache Implementation**
```python
# funkygibbon/storage/redis_cache.py
class RedisCache:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def get(self, key: str) -> Optional[Dict]:
        data = await self.redis.get(key)
        return json.loads(data) if data else None
    
    async def set(self, key: str, value: Dict, ttl: int = 3600):
        await self.redis.setex(key, ttl, json.dumps(value))
```

## Phase 4: Inbetweenies Protocol (Week 4)

### Day 16-17: Protocol Messages

1. **Define Message Structures (Swift)**
```swift
// WildThing/Sources/Inbetweenies/Messages.swift
public struct InbetweeniesRequest: Codable {
    let protocolVersion: String = "inbetweenies-v1"
    let deviceId: String
    let userId: String
    let sessionId: String
    let vectorClock: [String: String]
    let changes: [EntityChange]
    let compression: CompressionType
    let capabilities: [String]
    let metadata: RequestMetadata
}
```

2. **Define Message Structures (Python)**
```python
# funkygibbon/inbetweenies/messages.py
class InbetweeniesRequest(BaseModel):
    protocol_version: str = "inbetweenies-v1"
    device_id: str
    user_id: str
    session_id: str
    vector_clock: Dict[str, str]
    changes: List[EntityChange]
    compression: CompressionType
    capabilities: List[str]
    metadata: RequestMetadata
```

### Day 18-19: Sync Manager

1. **WildThing Sync Manager**
```swift
// WildThing/Sources/Inbetweenies/SyncManager.swift
public class SyncManager {
    private let storage: WildThingStorage
    private let networkService: NetworkService
    private var vectorClock: VectorClock
    
    public func sync() async throws {
        // 1. Collect local changes
        let changes = try await collectLocalChanges()
        
        // 2. Prepare sync request
        let request = InbetweeniesRequest(
            deviceId: deviceId,
            userId: userId,
            sessionId: UUID().uuidString,
            vectorClock: vectorClock.toDict(),
            changes: changes
        )
        
        // 3. Send to server
        let response = try await networkService.sync(request)
        
        // 4. Process response
        try await processResponse(response)
    }
}
```

2. **FunkyGibbon Sync Service**
```python
# funkygibbon/inbetweenies/sync_service.py
class SyncService:
    def __init__(self, storage: EntityRepository):
        self.storage = storage
        self.conflict_resolver = ConflictResolver()
    
    async def handle_sync(self, request: InbetweeniesRequest) -> InbetweeniesResponse:
        # 1. Validate request
        self._validate_request(request)
        
        # 2. Apply changes
        conflicts = await self._apply_changes(request.changes)
        
        # 3. Get changes for client
        client_changes = await self._get_changes_for_client(
            request.user_id,
            request.vector_clock,
            request.device_id
        )
        
        # 4. Update vector clock
        updated_clock = self._merge_vector_clocks(
            request.vector_clock,
            self.server_clock
        )
        
        return InbetweeniesResponse(
            vector_clock=updated_clock,
            changes=client_changes,
            conflicts=conflicts
        )
```

### Day 20: Conflict Resolution

1. **Implement Conflict Detection**
```python
# funkygibbon/inbetweenies/conflict_resolution.py
class ConflictResolver:
    def detect_conflict(self, local_entity, remote_change):
        if not local_entity:
            return None
        
        if local_entity.deleted and remote_change.change_type == "update":
            return Conflict(
                type=ConflictType.DELETE_UPDATE,
                local_version=local_entity.version,
                remote_version=remote_change.entity_version
            )
        
        # Check version lineage
        if local_entity.version not in remote_change.parent_versions:
            return Conflict(
                type=ConflictType.VERSION_MISMATCH,
                local_version=local_entity.version,
                remote_version=remote_change.entity_version
            )
        
        return None
```

## Phase 5: MCP Integration (Week 5)

### Day 21-22: WildThing MCP Server

1. **Implement MCP Server**
```swift
// WildThing/Sources/MCP/WildThingMCPServer.swift
public class WildThingMCPServer: MCPServer {
    private let storage: WildThingStorage
    private let homeGraph: HomeGraph
    
    public func registerTools() {
        // Register MCP tools
        register(tool: CreateEntityTool(storage: storage))
        register(tool: QueryGraphTool(graph: homeGraph))
        register(tool: UpdateEntityTool(storage: storage))
        register(tool: DeleteEntityTool(storage: storage))
    }
}
```

2. **Implement MCP Tools**
```swift
// WildThing/Sources/MCP/Tools/CreateEntityTool.swift
public class CreateEntityTool: MCPTool {
    public let name = "create_entity"
    public let description = "Create a new home graph entity"
    
    public func execute(parameters: [String: Any]) async throws -> MCPResponse {
        let entityType = EntityType(rawValue: parameters["type"] as! String)!
        let content = parameters["content"] as! [String: Any]
        
        let entity = createEntity(type: entityType, content: content)
        try await storage.save(entity)
        
        return MCPResponse(result: entity.toDict())
    }
}
```

### Day 23-24: FunkyGibbon MCP Integration

1. **Create MCP Wrapper**
```python
# funkygibbon/mcp/server.py
from mcp.server import MCPServer
from mcp.tool import Tool

class FunkyGibbonMCPServer(MCPServer):
    def __init__(self, storage, sync_service):
        self.storage = storage
        self.sync_service = sync_service
        self.register_tools()
    
    def register_tools(self):
        self.register(CreateEntityTool(self.storage))
        self.register(QueryEntitiesTool(self.storage))
        self.register(SyncNowTool(self.sync_service))
```

### Day 25: API Integration

1. **REST API Setup**
```python
# funkygibbon/api/main.py
from fastapi import FastAPI, Depends
from .routes import entities, sync, mcp

app = FastAPI(title="FunkyGibbon API")

# Include routers
app.include_router(entities.router, prefix="/api/entities")
app.include_router(sync.router, prefix="/api/sync")
app.include_router(mcp.router, prefix="/api/mcp")

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

## Phase 6: Testing & Validation (Week 6)

### Day 26-27: Unit Testing

1. **Swift Unit Tests**
```swift
// WildThing/Tests/Unit/SQLiteStorageTests.swift
class SQLiteStorageTests: XCTestCase {
    var storage: SQLiteStorage!
    
    override func setUp() {
        storage = SQLiteStorage(inMemory: true)
    }
    
    func testSaveAndFetch() async throws {
        let entity = HomeEntity(content: ["name": "Test"], userId: "test")
        try await storage.save(entity)
        
        let fetched = try await storage.fetch(id: entity.id)
        XCTAssertEqual(fetched?.id, entity.id)
    }
}
```

2. **Python Unit Tests**
```python
# funkygibbon/tests/unit/test_storage.py
@pytest.mark.asyncio
async def test_save_and_fetch():
    storage = EntityRepository(session)
    entity = HomeEntity(
        version="v1",
        entity_type=EntityType.HOME,
        content={"name": "Test"},
        user_id="test"
    )
    
    saved = await storage.save(entity)
    fetched = await storage.fetch(saved.id)
    assert fetched.id == saved.id
```

### Day 28-29: Integration Testing

1. **End-to-End Sync Test**
```python
# funkygibbon/tests/e2e/test_sync_flow.py
@pytest.mark.asyncio
async def test_full_sync_flow():
    # 1. Create entities on client
    client_entity = create_test_entity()
    
    # 2. Prepare sync request
    request = create_sync_request([client_entity])
    
    # 3. Process sync
    response = await sync_service.handle_sync(request)
    
    # 4. Verify sync completed
    assert response.sync_status == "success"
    assert len(response.conflicts) == 0
```

### Day 30: Performance Testing

1. **Benchmark Tests**
```swift
// WildThing/Tests/Performance/PerformanceBenchmarks.swift
func testBulkInsertPerformance() {
    measure {
        let entities = (0..<1000).map { _ in
            HomeEntity(content: [:], userId: "test")
        }
        
        await storage.saveMany(entities)
    }
}
```

## Phase 7: Documentation & Deployment (Week 7)

### Day 31-32: API Documentation

1. **Generate OpenAPI Spec**
```python
# funkygibbon/api/docs.py
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="FunkyGibbon API",
        version="1.0.0",
        description="Smart Home Knowledge Graph API",
        routes=app.routes,
    )
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema
```

### Day 33-34: Deployment Configuration

1. **Docker Configuration**
```dockerfile
# Dockerfile.funkygibbon
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY funkygibbon/ ./funkygibbon/
CMD ["uvicorn", "funkygibbon.api.main:app", "--host", "0.0.0.0"]
```

2. **Kubernetes Manifests**
```yaml
# k8s/funkygibbon-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: funkygibbon
spec:
  replicas: 3
  selector:
    matchLabels:
      app: funkygibbon
  template:
    metadata:
      labels:
        app: funkygibbon
    spec:
      containers:
      - name: funkygibbon
        image: funkygibbon:latest
        ports:
        - containerPort: 8000
```

### Day 35: Final Integration

1. **Integration with c11s-ios-house**
```swift
// Integration point in iOS app
import WildThing

class HomeKitSyncManager {
    private let wildThing: WildThingMCPServer
    
    func syncWithHomeKit() async throws {
        let homes = await homeManager.homes
        for home in homes {
            let entity = convertToEntity(home)
            try await wildThing.createEntity(entity)
        }
    }
}
```

## Testing Checkpoints

### Checkpoint 1: Data Models (End of Week 2)
- [ ] All entity types defined and tested
- [ ] Serialization/deserialization working
- [ ] Validation rules implemented

### Checkpoint 2: Storage (End of Week 3)
- [ ] SQLite storage fully functional
- [ ] PostgreSQL storage operational
- [ ] Basic CRUD operations tested

### Checkpoint 3: Sync Protocol (End of Week 4)
- [ ] Sync request/response working
- [ ] Conflict detection functional
- [ ] Vector clock implementation tested

### Checkpoint 4: MCP Integration (End of Week 5)
- [ ] MCP tools registered and functional
- [ ] API endpoints tested
- [ ] Authentication working

### Checkpoint 5: Full System (End of Week 6)
- [ ] End-to-end sync working
- [ ] Performance benchmarks passing
- [ ] Security tests passing

## Troubleshooting Guide

### Common Issues

1. **SQLite Lock Errors**
   - Solution: Ensure single writer, use WAL mode
   ```swift
   db.execute("PRAGMA journal_mode = WAL")
   ```

2. **Sync Conflicts**
   - Solution: Implement proper vector clock comparison
   - Log all conflicts for debugging

3. **Performance Issues**
   - Solution: Add proper indexes
   - Implement connection pooling
   - Use Redis caching

4. **Network Timeouts**
   - Solution: Implement retry logic with exponential backoff
   - Use streaming for large datasets

## Next Steps

1. **Phase 8: Production Readiness**
   - Security hardening
   - Performance optimization
   - Monitoring setup

2. **Phase 9: Advanced Features**
   - Real-time sync
   - AI integration
   - HomeKit automation

3. **Phase 10: Scale Testing**
   - Load testing
   - Multi-region deployment
   - Disaster recovery

## Resources

- [Swift Package Manager Documentation](https://swift.org/package-manager/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [MCP Specification](https://modelcontextprotocol.org/)
- [SQLite Best Practices](https://www.sqlite.org/bestpractices.html)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)

## Support

- GitHub Issues: https://github.com/adrianco/the-goodies/issues
- Documentation: https://github.com/adrianco/the-goodies/wiki
- Community: TBD