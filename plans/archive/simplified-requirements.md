<!--
The Goodies - Simplified Requirements Document

DEVELOPMENT CONTEXT:
Created after the initial project scope proved too ambitious. This document
captures the dramatically simplified requirements focusing on a single-house
deployment with pragmatic technical choices.

DOCUMENT PURPOSE:
Defines the current, realistic scope of The Goodies project after the pivot
from enterprise-scale to single-house deployment. This is the authoritative
source for what we're actually building.

REVISION HISTORY:
- 2024-01-15: Created to document simplified scope
- 2024-01-15: Reduced from 12-week to 4-week timeline
- 2024-01-15: Changed from PostgreSQL+Redis to SQLite only
- 2024-01-15: Simplified from vector clocks to last-write-wins

KEY DECISIONS:
- Single house only (no multi-tenancy)
- ~300 entities maximum
- SQLite for all storage
- Last-write-wins conflict resolution
- REST API only (no WebSockets)
-->

# The Goodies - Simplified Requirements Document

## Overview
This document presents a simplified approach to The Goodies smart home knowledge graph system, focusing on practical implementation for a single household with minimal complexity.

## Core Simplifications

### 1. Scale & Performance
- **Target**: Single house with ~200-300 entities maximum
- **Users**: 3-5 household members
- **Update Rate**: Low frequency (seconds, not milliseconds)
- **Sync Frequency**: On-demand with optional periodic background sync
- **Data Size**: <100MB total database size expected

### 2. Technology Stack
- **Database**: SQLite only (no PostgreSQL/Redis)
- **Backend**: Minimal Python FastAPI service
- **Frontend**: Swift package for iOS/macOS
- **Protocol**: Simplified JSON over HTTPS (no WebSockets)

### 3. Conflict Resolution
- **Strategy**: Last-write-wins with timestamps
- **No complex merging**: Simple timestamp comparison
- **User notification**: Show conflicts, don't auto-resolve complex ones
- **Version tracking**: Simple linear versioning, not full DAG

### 4. Data Model Simplification
- **Essential Entities Only**:
  - Home (1 per database)
  - Room (10-20 typical)
  - Device (50-100 typical)
  - User (3-5 typical)
  - Note (optional, 0-50)
- **Skip Complex Features**:
  - No procedures/manuals initially
  - No automation rules
  - No scheduling
  - No binary content (images/PDFs)

### 5. Sync Protocol Simplification
- **No vector clocks**: Use simple timestamps
- **No differential sync**: Full entity sync only
- **Batch size**: Small (10-50 entities per request)
- **No compression**: JSON is sufficient at this scale

## Minimal Viable Product (MVP)

### Phase 1: Core Storage (Week 1)
1. SQLite schema with basic entities
2. Simple CRUD operations
3. Basic relationship tracking
4. Python models with Pydantic

### Phase 2: Basic API (Week 2)
1. FastAPI with 5-10 endpoints
2. Simple authentication (API key)
3. JSON request/response
4. Basic error handling

### Phase 3: Swift Client (Week 3)
1. SQLite storage matching Python schema
2. Basic entity models
3. Simple HTTP client
4. Local CRUD operations

### Phase 4: Simple Sync (Week 4)
1. Timestamp-based change tracking
2. Full entity replacement on conflict
3. Manual sync trigger
4. Basic error recovery

## Deferred Features

### Not in MVP:
- MCP server implementation
- HomeKit integration
- Complex conflict resolution
- Binary content support
- Real-time sync
- Multi-home support
- Advanced search/query
- Performance optimization

### Future Considerations:
- Add features only when proven necessary
- Keep compatibility with simple model
- Maintain backward compatibility
- Focus on reliability over features

## Implementation Principles

### 1. Python First
- Start with Python backend
- Define data models in Python
- Generate Swift models from Python schemas
- Python drives the protocol

### 2. Keep It Simple
- No premature optimization
- No complex abstractions
- Direct SQL queries acceptable
- Minimal dependencies

### 3. User Experience
- Sync should "just work"
- Conflicts shown clearly
- No data loss ever
- Fast local operations

### 4. Testing Strategy
- Unit tests for models
- Integration tests for sync
- No complex test scenarios
- Focus on data integrity

## Example Simplified Models

### Python (Pydantic)
```python
class Device(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    room_id: str
    name: str
    device_type: str
    is_active: bool = True
    properties: Dict[str, Any] = {}
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str
```

### Swift
```swift
struct Device: Codable {
    let id: String
    let roomId: String
    var name: String
    let deviceType: String
    var isActive: Bool = true
    var properties: [String: Any] = [:]
    let updatedAt: Date
    let updatedBy: String
}
```

### SQLite Schema
```sql
CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    name TEXT NOT NULL,
    device_type TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    properties TEXT, -- JSON
    updated_at TIMESTAMP NOT NULL,
    updated_by TEXT NOT NULL,
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);

CREATE INDEX idx_devices_room ON devices(room_id);
CREATE INDEX idx_devices_updated ON devices(updated_at);
```

## API Endpoints (Minimal)

### Essential Only:
```
GET    /api/sync/changes?since={timestamp}
POST   /api/sync/upload
GET    /api/entities/{type}
GET    /api/entities/{type}/{id}
PUT    /api/entities/{type}/{id}
DELETE /api/entities/{type}/{id}
```

### Authentication:
- Simple bearer token
- No complex OAuth
- Token in header: `Authorization: Bearer {token}`

## Sync Flow (Simplified)

### Client Sync:
1. GET /api/sync/changes?since={last_sync_time}
2. Receive changed entities
3. Apply changes locally (last-write-wins)
4. POST /api/sync/upload with local changes
5. Update last_sync_time

### Server Logic:
1. Track updated_at for all entities
2. Return entities where updated_at > since
3. On upload, check timestamps
4. Apply if newer, reject if older
5. Return success/conflict status

## Success Criteria

### MVP Complete When:
1. Can sync 100 devices between 2 clients
2. Conflicts handled without data loss
3. Sync completes in <5 seconds
4. No crashes or data corruption
5. Basic CRUD operations work

### Non-Goals:
- High performance
- Real-time updates
- Complex queries
- Multiple homes
- Advanced features

## Development Approach

### Week 1: Python Backend
- SQLite database setup
- Basic models
- Simple API
- Manual testing

### Week 2: Swift Client
- Mirror Python models
- Local storage
- HTTP client
- Basic UI (optional)

### Week 3: Sync Implementation
- Change tracking
- Sync endpoints
- Conflict detection
- Testing

### Week 4: Integration & Polish
- End-to-end testing
- Bug fixes
- Documentation
- Simple example app

## Conclusion

This simplified approach reduces the original 12-week timeline to 4 weeks by:
- Eliminating complex features
- Using proven simple patterns
- Focusing on core functionality
- Deferring advanced capabilities

The result will be a working system that can be extended later if needed, but solves the immediate need for simple home data synchronization.