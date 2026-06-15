# FunkyGibbon Python Service - Detailed Architecture Specification

## Overview

FunkyGibbon is a Python-based backend service that provides centralized synchronization for The Goodies smart home system. It uses HomeKit-compatible models from the shared Inbetweenies package and implements a simple last-write-wins synchronization protocol. The current implementation uses SQLite for simplicity and focuses on single-home deployments.

## Service Architecture

```
funkygibbon/
├── pyproject.toml                    # Package configuration
├── setup.py                          # Alternative setup
├── requirements/
│   ├── base.txt                      # Core dependencies
│   ├── dev.txt                       # Development dependencies
│   └── prod.txt                      # Production dependencies
├── funkygibbon/
│   ├── __init__.py
│   ├── __main__.py                   # Entry point
│   ├── config.py                     # Configuration management
│   ├── models/                       # Uses Inbetweenies shared models
│   │   ├── __init__.py
│   │   └── base.py                   # Any server-specific extensions
│   ├── repositories/                 # Data access layer
│   │   ├── __init__.py
│   │   ├── base.py                   # Base repository
│   │   ├── home.py                   # Home repository
│   │   ├── room.py                   # Room repository
│   │   ├── accessory.py              # Accessory repository
│   │   └── user.py                   # User repository
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── base.py                   # Abstract storage interface
│   │   └── sqlite.py                 # SQLite implementation (current)
│   ├── sync/
│   │   ├── __init__.py
│   │   ├── engine.py                 # Simple last-write-wins sync
│   │   └── protocol.py               # Sync protocol handlers
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py                    # FastAPI application
│   │   ├── dependencies.py           # Dependency injection
│   │   ├── middleware/
│   │   │   ├── auth.py               # Authentication
│   │   │   ├── cors.py               # CORS handling
│   │   │   ├── logging.py            # Request logging
│   │   │   └── rate_limit.py         # Rate limiting
│   │   ├── routes/
│   │   │   ├── sync.py               # Inbetweenies endpoints
│   │   │   ├── entities.py           # Entity CRUD
│   │   │   ├── relationships.py      # Relationship management
│   │   │   ├── search.py             # Search endpoints
│   │   │   └── analytics.py          # Analytics endpoints
│   │   └── websocket/
│   │       ├── manager.py            # WebSocket connections
│   │       └── handlers.py           # Real-time updates
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── server.py                 # MCP server wrapper
│   │   ├── tools.py                  # Tool implementations
│   │   └── handlers.py               # Request handlers
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── aggregator.py             # Data aggregation
│   │   ├── reports.py                # Report generation
│   │   └── ml_insights.py            # ML-based insights
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── homekit_cloud.py         # HomeKit cloud sync
│   │   ├── google_home.py           # Google Home integration
│   │   ├── alexa.py                 # Alexa integration
│   │   └── ifttt.py                 # IFTTT webhooks
│   └── utils/
│       ├── __init__.py
│       ├── logging.py                # Structured logging
│       ├── metrics.py                # Prometheus metrics
│       ├── crypto.py                 # Encryption utilities
│       └── background.py             # Background tasks
├── tests/
│   ├── conftest.py                   # Pytest configuration
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── scripts/
│   ├── migrate.py                    # Database migrations
│   ├── seed.py                       # Seed data
│   └── benchmark.py                  # Performance testing
└── docker/
    ├── Dockerfile
    ├── docker-compose.yml
    └── .dockerignore
```

## Core Components

### 1. Data Models

#### Pydantic Models
```python
# funkygibbon/core/models.py
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator, root_validator
import uuid

class EntityType(str, Enum):
    """Entity types matching WildThing"""
    HOME = "home"
    ROOM = "room"
    DEVICE = "device"
    ACCESSORY = "accessory"
    SERVICE = "service"
    ZONE = "zone"
    DOOR = "door"
    WINDOW = "window"
    PROCEDURE = "procedure"
    MANUAL = "manual"
    NOTE = "note"
    SCHEDULE = "schedule"
    AUTOMATION = "automation"

class SourceType(str, Enum):
    """Source of entity data"""
    HOMEKIT = "homekit"
    MATTER = "matter"
    MANUAL = "manual"
    IMPORTED = "imported"
    GENERATED = "generated"
    GOOGLE_HOME = "google_home"
    ALEXA = "alexa"

class RelationshipType(str, Enum):
    """Relationship types between entities"""
    LOCATED_IN = "located_in"
    CONTROLS = "controls"
    CONNECTS_TO = "connects_to"
    PART_OF = "part_of"
    MANAGES = "manages"
    DOCUMENTED_BY = "documented_by"
    PROCEDURE_FOR = "procedure_for"
    TRIGGERED_BY = "triggered_by"
    DEPENDS_ON = "depends_on"

class HomeEntity(BaseModel):
    """Core entity model with versioning"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = Field(default_factory=lambda: generate_version())
    entity_type: EntityType
    parent_versions: List[str] = Field(default_factory=list)
    content: Dict[str, Any]
    user_id: str
    source_type: SourceType = SourceType.MANUAL
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None  # Soft delete
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
        use_enum_values = True
    
    @validator('content')
    def validate_content(cls, v, values):
        """Validate content based on entity type"""
        entity_type = values.get('entity_type')
        if entity_type == EntityType.DEVICE:
            if 'name' not in v:
                raise ValueError("Device entities must have a name")
        return v
    
    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
    
    @property
    def display_name(self) -> Optional[str]:
        return self.content.get('name')
    
    def update_content(self, key: str, value: Any) -> None:
        """Update content and modify timestamp"""
        self.content[key] = value
        self.last_modified = datetime.utcnow()

class EntityRelationship(BaseModel):
    """Relationship between entities"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_entity_id: str
    to_entity_id: str
    relationship_type: RelationshipType
    properties: Dict[str, Any] = Field(default_factory=dict)
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None
    
    @root_validator
    def validate_relationship(cls, values):
        """Ensure relationship makes sense"""
        from_id = values.get('from_entity_id')
        to_id = values.get('to_entity_id')
        if from_id == to_id:
            raise ValueError("Entity cannot have relationship with itself")
        return values

# Inbetweenies protocol models
class ChangeType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

class EntityChange(BaseModel):
    """Change record for sync protocol"""
    change_type: ChangeType
    entity_id: str
    entity_version: str
    entity_type: Optional[EntityType] = None
    content: Optional[Dict[str, Any]] = None
    timestamp: datetime
    parent_versions: List[str] = Field(default_factory=list)
    user_id: str
    device_id: str
    
    @validator('content')
    def validate_content_for_change_type(cls, v, values):
        change_type = values.get('change_type')
        if change_type in [ChangeType.CREATE, ChangeType.UPDATE] and v is None:
            raise ValueError(f"Content required for {change_type} changes")
        return v

class InbetweeniesRequest(BaseModel):
    """Sync request from client"""
    protocol_version: str = "inbetweenies-v1"
    device_id: str
    user_id: str
    vector_clock: Dict[str, str]
    changes: List[EntityChange]
    compression: Optional[str] = None  # gzip, zstd
    
    @validator('protocol_version')
    def validate_protocol_version(cls, v):
        if not v.startswith("inbetweenies-"):
            raise ValueError("Invalid protocol version")
        return v

class InbetweeniesResponse(BaseModel):
    """Sync response to client"""
    changes: List[EntityChange]
    vector_clock: Dict[str, str]
    conflicts: List[str] = Field(default_factory=list)
    next_sync_token: Optional[str] = None
    server_time: datetime = Field(default_factory=datetime.utcnow)

def generate_version() -> str:
    """Generate unique version string"""
    timestamp = datetime.utcnow().isoformat()
    random_suffix = str(uuid.uuid4())[:8]
    return f"{timestamp}-{random_suffix}"
```

### 2. Storage Layer

#### PostgreSQL Storage Implementation
```python
# funkygibbon/storage/postgresql.py
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncpg
import json
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import UUID, JSONB
from contextlib import asynccontextmanager

from ..core.models import HomeEntity, EntityRelationship, EntityType
from ..core.exceptions import StorageError, EntityNotFound
from .base import StorageInterface

class PostgreSQLStorage(StorageInterface):
    """PostgreSQL storage implementation with connection pooling"""
    
    def __init__(self, database_url: str, pool_size: int = 20):
        self.database_url = database_url
        self.pool_size = pool_size
        self.pool: Optional[asyncpg.Pool] = None
        
    async def initialize(self):
        """Initialize connection pool"""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=5,
            max_size=self.pool_size,
            command_timeout=60,
            init=self._init_connection
        )
        
    async def _init_connection(self, conn):
        """Initialize each connection"""
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
        
    @asynccontextmanager
    async def acquire_connection(self):
        """Acquire connection from pool"""
        async with self.pool.acquire() as conn:
            yield conn
            
    async def store_entity(self, entity: HomeEntity) -> None:
        """Store entity with versioning"""
        async with self.acquire_connection() as conn:
            try:
                await conn.execute("""
                    INSERT INTO entities 
                    (id, version, entity_type, parent_versions, content, 
                     user_id, source_type, created_at, last_modified)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id, version) DO UPDATE SET
                        content = EXCLUDED.content,
                        last_modified = EXCLUDED.last_modified
                """, 
                    entity.id, entity.version, entity.entity_type.value,
                    json.dumps(entity.parent_versions), entity.content,
                    entity.user_id, entity.source_type.value,
                    entity.created_at, entity.last_modified
                )
                
                # Update latest version view
                await conn.execute("""
                    INSERT INTO entity_latest (id, version, entity_type, user_id)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (id) DO UPDATE SET
                        version = EXCLUDED.version,
                        updated_at = NOW()
                """, entity.id, entity.version, entity.entity_type.value, entity.user_id)
                
            except Exception as e:
                raise StorageError(f"Failed to store entity: {e}")
                
    async def get_entity(self, entity_id: str, version: Optional[str] = None) -> Optional[HomeEntity]:
        """Get entity by ID and optional version"""
        async with self.acquire_connection() as conn:
            if version:
                row = await conn.fetchrow("""
                    SELECT * FROM entities 
                    WHERE id = $1 AND version = $2 AND deleted_at IS NULL
                """, entity_id, version)
            else:
                # Get latest version
                row = await conn.fetchrow("""
                    SELECT e.* FROM entities e
                    JOIN entity_latest el ON e.id = el.id AND e.version = el.version
                    WHERE e.id = $1 AND e.deleted_at IS NULL
                """, entity_id)
                
            if not row:
                return None
                
            return self._row_to_entity(row)
            
    async def get_entities_by_type(
        self, 
        entity_type: EntityType, 
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[HomeEntity]:
        """Get entities by type with pagination"""
        async with self.acquire_connection() as conn:
            rows = await conn.fetch("""
                SELECT e.* FROM entities e
                JOIN entity_latest el ON e.id = el.id AND e.version = el.version
                WHERE e.entity_type = $1 AND e.user_id = $2 AND e.deleted_at IS NULL
                ORDER BY e.last_modified DESC
                LIMIT $3 OFFSET $4
            """, entity_type.value, user_id, limit, offset)
            
            return [self._row_to_entity(row) for row in rows]
            
    async def search_entities(
        self,
        query: str,
        user_id: str,
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 50
    ) -> List[HomeEntity]:
        """Full-text search across entities"""
        async with self.acquire_connection() as conn:
            # Use PostgreSQL full-text search
            type_filter = ""
            params = [query, user_id, limit]
            
            if entity_types:
                type_list = [t.value for t in entity_types]
                type_filter = f"AND entity_type = ANY($4)"
                params.append(type_list)
                
            rows = await conn.fetch(f"""
                SELECT e.* FROM entities e
                JOIN entity_latest el ON e.id = el.id AND e.version = el.version
                WHERE to_tsvector('english', e.content::text) @@ plainto_tsquery('english', $1)
                AND e.user_id = $2 
                AND e.deleted_at IS NULL
                {type_filter}
                ORDER BY ts_rank(to_tsvector('english', e.content::text), 
                                plainto_tsquery('english', $1)) DESC
                LIMIT $3
            """, *params)
            
            return [self._row_to_entity(row) for row in rows]
            
    async def get_changes_since(
        self,
        user_id: str,
        since: datetime,
        device_id: Optional[str] = None
    ) -> List[EntityChange]:
        """Get all changes since timestamp for sync"""
        async with self.acquire_connection() as conn:
            device_filter = ""
            params = [user_id, since]
            
            if device_id:
                device_filter = "AND device_id != $3"
                params.append(device_id)
                
            rows = await conn.fetch(f"""
                SELECT * FROM entity_changes
                WHERE user_id = $1 
                AND timestamp > $2
                {device_filter}
                ORDER BY timestamp ASC
            """, *params)
            
            return [self._row_to_change(row) for row in rows]
            
    async def store_relationship(self, relationship: EntityRelationship) -> None:
        """Store entity relationship"""
        async with self.acquire_connection() as conn:
            await conn.execute("""
                INSERT INTO relationships
                (id, from_entity_id, to_entity_id, relationship_type,
                 properties, user_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    properties = EXCLUDED.properties
            """,
                relationship.id, relationship.from_entity_id,
                relationship.to_entity_id, relationship.relationship_type.value,
                relationship.properties, relationship.user_id,
                relationship.created_at
            )
            
    async def get_relationships(
        self,
        entity_id: str,
        direction: str = "both"  # from, to, both
    ) -> List[EntityRelationship]:
        """Get relationships for entity"""
        async with self.acquire_connection() as conn:
            conditions = []
            
            if direction in ["from", "both"]:
                conditions.append("from_entity_id = $1")
            if direction in ["to", "both"]:
                conditions.append("to_entity_id = $1")
                
            where_clause = " OR ".join(conditions)
            
            rows = await conn.fetch(f"""
                SELECT * FROM relationships
                WHERE ({where_clause}) AND deleted_at IS NULL
                ORDER BY created_at DESC
            """, entity_id)
            
            return [self._row_to_relationship(row) for row in rows]
            
    async def find_path(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 10
    ) -> Optional[List[str]]:
        """Find shortest path between entities using recursive CTE"""
        async with self.acquire_connection() as conn:
            result = await conn.fetchrow("""
                WITH RECURSIVE path_search AS (
                    -- Base case: start from source
                    SELECT 
                        from_entity_id,
                        to_entity_id,
                        ARRAY[from_entity_id, to_entity_id] as path,
                        1 as depth
                    FROM relationships
                    WHERE from_entity_id = $1 AND deleted_at IS NULL
                    
                    UNION ALL
                    
                    -- Recursive case: follow relationships
                    SELECT 
                        r.from_entity_id,
                        r.to_entity_id,
                        ps.path || r.to_entity_id,
                        ps.depth + 1
                    FROM relationships r
                    JOIN path_search ps ON r.from_entity_id = ps.to_entity_id
                    WHERE NOT r.to_entity_id = ANY(ps.path)  -- Avoid cycles
                    AND ps.depth < $3
                    AND r.deleted_at IS NULL
                )
                SELECT path FROM path_search
                WHERE to_entity_id = $2
                ORDER BY depth ASC
                LIMIT 1
            """, from_entity_id, to_entity_id, max_depth)
            
            return result['path'] if result else None
            
    def _row_to_entity(self, row: asyncpg.Record) -> HomeEntity:
        """Convert database row to entity"""
        return HomeEntity(
            id=str(row['id']),
            version=row['version'],
            entity_type=EntityType(row['entity_type']),
            parent_versions=json.loads(row['parent_versions']),
            content=row['content'],
            user_id=row['user_id'],
            source_type=SourceType(row['source_type']),
            created_at=row['created_at'],
            last_modified=row['last_modified'],
            deleted_at=row.get('deleted_at')
        )
        
    def _row_to_relationship(self, row: asyncpg.Record) -> EntityRelationship:
        """Convert database row to relationship"""
        return EntityRelationship(
            id=str(row['id']),
            from_entity_id=str(row['from_entity_id']),
            to_entity_id=str(row['to_entity_id']),
            relationship_type=RelationshipType(row['relationship_type']),
            properties=row['properties'] or {},
            user_id=row['user_id'],
            created_at=row['created_at'],
            deleted_at=row.get('deleted_at')
        )

# Database schema
SCHEMA = """
-- Entities table with versioning
CREATE TABLE IF NOT EXISTS entities (
    id UUID NOT NULL,
    version TEXT NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    parent_versions JSONB DEFAULT '[]',
    content JSONB NOT NULL,
    user_id UUID NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_modified TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    PRIMARY KEY (id, version)
);

-- Latest version tracking
CREATE TABLE IF NOT EXISTS entity_latest (
    id UUID PRIMARY KEY,
    version TEXT NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    user_id UUID NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Relationships
CREATE TABLE IF NOT EXISTS relationships (
    id UUID PRIMARY KEY,
    from_entity_id UUID NOT NULL,
    to_entity_id UUID NOT NULL,
    relationship_type VARCHAR(50) NOT NULL,
    properties JSONB,
    user_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

-- Change tracking for sync
CREATE TABLE IF NOT EXISTS entity_changes (
    id BIGSERIAL PRIMARY KEY,
    change_type VARCHAR(20) NOT NULL,
    entity_id UUID NOT NULL,
    entity_version TEXT NOT NULL,
    entity_type VARCHAR(50),
    content JSONB,
    parent_versions JSONB DEFAULT '[]',
    user_id UUID NOT NULL,
    device_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Vector clocks for distributed sync
CREATE TABLE IF NOT EXISTS vector_clocks (
    user_id UUID NOT NULL,
    device_id TEXT NOT NULL,
    clock_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, device_id)
);

-- Conflict tracking
CREATE TABLE IF NOT EXISTS sync_conflicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    local_version TEXT NOT NULL,
    remote_version TEXT NOT NULL,
    conflict_type VARCHAR(50) NOT NULL,
    conflict_data JSONB,
    resolution_status VARCHAR(50) DEFAULT 'pending',
    resolved_at TIMESTAMPTZ,
    resolved_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices
CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entities_user ON entities(user_id);
CREATE INDEX idx_entities_modified ON entities(last_modified DESC);
CREATE INDEX idx_entities_content_gin ON entities USING gin(content);
CREATE INDEX idx_entities_fts ON entities USING gin(to_tsvector('english', content::text));

CREATE INDEX idx_relationships_from ON relationships(from_entity_id);
CREATE INDEX idx_relationships_to ON relationships(to_entity_id);
CREATE INDEX idx_relationships_type ON relationships(relationship_type);

CREATE INDEX idx_changes_user_time ON entity_changes(user_id, timestamp);
CREATE INDEX idx_changes_device ON entity_changes(device_id);

-- Triggers
CREATE OR REPLACE FUNCTION track_entity_changes() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO entity_changes (
            change_type, entity_id, entity_version, entity_type,
            content, parent_versions, user_id, device_id
        ) VALUES (
            'create', NEW.id, NEW.version, NEW.entity_type,
            NEW.content, NEW.parent_versions, NEW.user_id, 
            current_setting('app.device_id', true)
        );
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
            INSERT INTO entity_changes (
                change_type, entity_id, entity_version, entity_type,
                user_id, device_id
            ) VALUES (
                'delete', NEW.id, NEW.version, NEW.entity_type,
                NEW.user_id, current_setting('app.device_id', true)
            );
        ELSE
            INSERT INTO entity_changes (
                change_type, entity_id, entity_version, entity_type,
                content, parent_versions, user_id, device_id
            ) VALUES (
                'update', NEW.id, NEW.version, NEW.entity_type,
                NEW.content, NEW.parent_versions, NEW.user_id,
                current_setting('app.device_id', true)
            );
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER entity_changes_trigger
AFTER INSERT OR UPDATE ON entities
FOR EACH ROW EXECUTE FUNCTION track_entity_changes();
"""
```

### 3. Inbetweenies Sync Service

#### Sync Protocol Implementation
```python
# funkygibbon/inbetweenies/sync_service.py
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
import asyncio
from collections import defaultdict

from ..core.models import (
    InbetweeniesRequest, InbetweeniesResponse,
    EntityChange, ChangeType, HomeEntity
)
from ..core.exceptions import ConflictError, SyncError
from ..storage.base import StorageInterface
from .vector_clock import VectorClock
from .conflict_resolution import ConflictResolver
from .compression import compress_data, decompress_data

class InbetweeniesServer:
    """Server-side implementation of Inbetweenies sync protocol"""
    
    def __init__(
        self,
        storage: StorageInterface,
        conflict_resolver: Optional[ConflictResolver] = None
    ):
        self.storage = storage
        self.conflict_resolver = conflict_resolver or ConflictResolver()
        self.active_syncs: Dict[str, datetime] = {}
        self.sync_lock = asyncio.Lock()
        
    async def handle_sync_request(
        self,
        request: InbetweeniesRequest
    ) -> InbetweeniesResponse:
        """Process sync request from client"""
        # Validate protocol version
        if not self._validate_protocol_version(request.protocol_version):
            raise SyncError(f"Unsupported protocol version: {request.protocol_version}")
            
        # Prevent concurrent syncs from same device
        sync_key = f"{request.user_id}:{request.device_id}"
        async with self.sync_lock:
            if sync_key in self.active_syncs:
                last_sync = self.active_syncs[sync_key]
                if datetime.utcnow() - last_sync < timedelta(seconds=5):
                    raise SyncError("Sync already in progress")
            self.active_syncs[sync_key] = datetime.utcnow()
            
        try:
            # Decompress if needed
            if request.compression:
                request = await self._decompress_request(request)
                
            # Process incoming changes
            conflicts = await self._apply_client_changes(request)
            
            # Get changes for client
            client_changes = await self._get_changes_for_client(request)
            
            # Update vector clock
            updated_clock = await self._update_vector_clock(
                request.user_id,
                request.device_id,
                request.vector_clock
            )
            
            # Build response
            response = InbetweeniesResponse(
                changes=client_changes,
                vector_clock=updated_clock,
                conflicts=[c.entity_id for c in conflicts],
                next_sync_token=self._generate_sync_token()
            )
            
            # Compress if requested
            if request.compression:
                response = await self._compress_response(response, request.compression)
                
            return response
            
        finally:
            # Clean up sync lock
            async with self.sync_lock:
                self.active_syncs.pop(sync_key, None)
                
    async def _apply_client_changes(
        self,
        request: InbetweeniesRequest
    ) -> List[ConflictInfo]:
        """Apply changes from client, detecting conflicts"""
        conflicts = []
        applied_changes = []
        
        for change in request.changes:
            try:
                # Check for conflicts before applying
                conflict = await self._check_conflict(change, request.user_id)
                if conflict:
                    conflicts.append(conflict)
                    continue
                    
                # Apply the change
                await self._apply_change(change, request.device_id)
                applied_changes.append(change)
                
            except Exception as e:
                # Log error but continue processing other changes
                print(f"Error applying change {change.entity_id}: {e}")
                
        # Batch commit if supported
        if hasattr(self.storage, 'commit'):
            await self.storage.commit()
            
        return conflicts
        
    async def _check_conflict(
        self,
        change: EntityChange,
        user_id: str
    ) -> Optional[ConflictInfo]:
        """Check if change conflicts with current state"""
        if change.change_type == ChangeType.CREATE:
            # Check if entity already exists
            existing = await self.storage.get_entity(change.entity_id)
            if existing:
                return ConflictInfo(
                    entity_id=change.entity_id,
                    conflict_type="already_exists",
                    local_version=existing.version,
                    remote_version=change.entity_version
                )
                
        elif change.change_type in [ChangeType.UPDATE, ChangeType.DELETE]:
            # Check version lineage
            existing = await self.storage.get_entity(change.entity_id)
            if not existing:
                return ConflictInfo(
                    entity_id=change.entity_id,
                    conflict_type="not_found",
                    local_version=None,
                    remote_version=change.entity_version
                )
                
            # Check if change is based on current version
            if existing.version not in change.parent_versions:
                # Potential conflict - check if changes are compatible
                if await self._are_changes_compatible(existing, change):
                    return None  # Auto-merge compatible changes
                    
                return ConflictInfo(
                    entity_id=change.entity_id,
                    conflict_type="version_conflict",
                    local_version=existing.version,
                    remote_version=change.entity_version,
                    resolution_hint=self._suggest_resolution(existing, change)
                )
                
        return None
        
    async def _are_changes_compatible(
        self,
        existing: HomeEntity,
        change: EntityChange
    ) -> bool:
        """Check if changes can be auto-merged"""
        if change.change_type == ChangeType.DELETE:
            return False  # Never auto-merge deletes
            
        # Check if changes affect different fields
        if not change.content:
            return True
            
        existing_keys = set(existing.content.keys())
        change_keys = set(change.content.keys())
        
        # If no overlap, changes are compatible
        if not existing_keys.intersection(change_keys):
            return True
            
        # Check if values are identical for overlapping keys
        for key in existing_keys.intersection(change_keys):
            if existing.content[key] != change.content[key]:
                return False
                
        return True
        
    async def _apply_change(
        self,
        change: EntityChange,
        device_id: str
    ) -> None:
        """Apply a single change to storage"""
        # Set device context for change tracking
        await self.storage.set_context('device_id', device_id)
        
        if change.change_type == ChangeType.CREATE:
            entity = HomeEntity(
                id=change.entity_id,
                version=change.entity_version,
                entity_type=change.entity_type,
                content=change.content or {},
                user_id=change.user_id,
                parent_versions=change.parent_versions
            )
            await self.storage.store_entity(entity)
            
        elif change.change_type == ChangeType.UPDATE:
            existing = await self.storage.get_entity(change.entity_id)
            if existing:
                # Merge changes
                updated_content = {**existing.content, **(change.content or {})}
                updated_entity = HomeEntity(
                    id=change.entity_id,
                    version=change.entity_version,
                    entity_type=existing.entity_type,
                    content=updated_content,
                    user_id=change.user_id,
                    parent_versions=[existing.version] + change.parent_versions
                )
                await self.storage.store_entity(updated_entity)
                
        elif change.change_type == ChangeType.DELETE:
            await self.storage.delete_entity(change.entity_id, soft=True)
            
    async def _get_changes_for_client(
        self,
        request: InbetweeniesRequest
    ) -> List[EntityChange]:
        """Get changes that client doesn't have"""
        # Parse vector clock
        client_clock = VectorClock.from_dict(request.vector_clock)
        
        # Get all changes since client's last sync
        all_changes = await self.storage.get_changes_since(
            user_id=request.user_id,
            since=client_clock.get_min_timestamp(),
            device_id=request.device_id  # Exclude changes from this device
        )
        
        # Filter changes based on vector clock
        filtered_changes = []
        for change in all_changes:
            change_clock = VectorClock.from_dict({change.device_id: change.entity_version})
            if not client_clock.has_seen(change_clock):
                filtered_changes.append(change)
                
        # Sort by timestamp to maintain causal ordering
        filtered_changes.sort(key=lambda c: c.timestamp)
        
        # Limit response size
        max_changes = 1000  # Configurable
        if len(filtered_changes) > max_changes:
            filtered_changes = filtered_changes[:max_changes]
            
        return filtered_changes
        
    async def _update_vector_clock(
        self,
        user_id: str,
        device_id: str,
        client_clock: Dict[str, str]
    ) -> Dict[str, str]:
        """Update and merge vector clocks"""
        # Get current server clock
        server_clock = await self.storage.get_vector_clock(user_id)
        
        # Merge with client clock
        merged_clock = VectorClock.from_dict(server_clock)
        merged_clock.merge(VectorClock.from_dict(client_clock))
        
        # Increment for this sync
        merged_clock.increment(device_id)
        
        # Persist updated clock
        await self.storage.update_vector_clock(user_id, merged_clock.to_dict())
        
        return merged_clock.to_dict()
        
    def _validate_protocol_version(self, version: str) -> bool:
        """Check if protocol version is supported"""
        supported_versions = ["inbetweenies-v1", "inbetweenies-v1.1"]
        return version in supported_versions
        
    def _generate_sync_token(self) -> str:
        """Generate token for incremental sync"""
        # Simple implementation - could be more sophisticated
        return datetime.utcnow().isoformat()
        
    def _suggest_resolution(
        self,
        existing: HomeEntity,
        change: EntityChange
    ) -> str:
        """Suggest conflict resolution strategy"""
        # Simple heuristic - could be ML-based
        if change.timestamp > existing.last_modified:
            return "accept_remote"  # Remote is newer
        else:
            return "keep_local"  # Local is newer

class ConflictInfo:
    """Information about a sync conflict"""
    def __init__(
        self,
        entity_id: str,
        conflict_type: str,
        local_version: Optional[str],
        remote_version: str,
        resolution_hint: Optional[str] = None
    ):
        self.entity_id = entity_id
        self.conflict_type = conflict_type
        self.local_version = local_version
        self.remote_version = remote_version
        self.resolution_hint = resolution_hint
```

### 4. FastAPI Application

#### API Setup and Routes
```python
# funkygibbon/api/app.py
from fastapi import FastAPI, Depends, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from prometheus_client import Counter, Histogram, generate_latest
import time

from .dependencies import get_storage, get_current_user, get_sync_service
from .middleware import RateLimitMiddleware, LoggingMiddleware, AuthMiddleware
from .routes import sync, entities, relationships, search, analytics
from .websocket.manager import WebSocketManager
from ..config import settings

# Metrics
request_count = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logging.info("Starting FunkyGibbon service")
    
    # Initialize storage
    storage = app.state.storage
    await storage.initialize()
    
    # Initialize WebSocket manager
    app.state.ws_manager = WebSocketManager()
    
    yield
    
    # Shutdown
    logging.info("Shutting down FunkyGibbon service")
    await storage.close()

app = FastAPI(
    title="FunkyGibbon API",
    description="Smart home knowledge graph synchronization service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware
app.add_middleware(RateLimitMiddleware, rate_limit=100, window=60)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware, public_paths=["/health", "/metrics"])

# Include routers
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(entities.router, prefix="/api/entities", tags=["entities"])
app.include_router(relationships.router, prefix="/api/relationships", tags=["relationships"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "funkygibbon",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type="text/plain")

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    storage = Depends(get_storage)
):
    """WebSocket endpoint for real-time updates"""
    manager = app.state.ws_manager
    await manager.connect(websocket, user_id)
    
    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_json()
            
            # Handle different message types
            if data["type"] == "subscribe":
                await manager.subscribe(user_id, data["entity_id"])
            elif data["type"] == "unsubscribe":
                await manager.unsubscribe(user_id, data["entity_id"])
                
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(user_id)

# Error handlers
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc), "type": "validation_error"}
    )

@app.exception_handler(EntityNotFound)
async def entity_not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": str(exc), "type": "not_found"}
    )

@app.exception_handler(ConflictError)
async def conflict_error_handler(request, exc):
    return JSONResponse(
        status_code=409,
        content={
            "error": str(exc),
            "type": "conflict",
            "conflict_id": exc.conflict_id
        }
    )
```

#### Sync API Routes
```python
# funkygibbon/api/routes/sync.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Optional

from ...core.models import InbetweeniesRequest, InbetweeniesResponse
from ...inbetweenies.sync_service import InbetweeniesServer
from ..dependencies import get_sync_service, get_current_user

router = APIRouter()

@router.post("/inbetweenies", response_model=InbetweeniesResponse)
async def sync_data(
    request: InbetweeniesRequest,
    background_tasks: BackgroundTasks,
    sync_service: InbetweeniesServer = Depends(get_sync_service),
    current_user = Depends(get_current_user)
):
    """
    Bidirectional sync using Inbetweenies protocol
    
    - Accepts changes from client
    - Returns changes client doesn't have
    - Handles conflict detection
    - Updates vector clocks
    """
    # Validate user matches request
    if request.user_id != current_user.id:
        raise HTTPException(403, "User ID mismatch")
        
    try:
        response = await sync_service.handle_sync_request(request)
        
        # Schedule background analytics
        background_tasks.add_task(
            track_sync_metrics,
            user_id=request.user_id,
            device_id=request.device_id,
            changes_up=len(request.changes),
            changes_down=len(response.changes),
            conflicts=len(response.conflicts)
        )
        
        return response
        
    except SyncError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.error(f"Sync error: {e}")
        raise HTTPException(500, "Sync failed")

@router.get("/status/{device_id}")
async def get_sync_status(
    device_id: str,
    current_user = Depends(get_current_user),
    storage = Depends(get_storage)
):
    """Get sync status for a device"""
    vector_clock = await storage.get_vector_clock(current_user.id)
    device_clock = vector_clock.get(device_id)
    
    if not device_clock:
        raise HTTPException(404, "Device not found")
        
    last_sync = await storage.get_last_sync_time(current_user.id, device_id)
    pending_changes = await storage.count_pending_changes(current_user.id, device_id)
    
    return {
        "device_id": device_id,
        "last_sync": last_sync,
        "vector_clock": device_clock,
        "pending_changes": pending_changes,
        "is_online": await check_device_online(device_id)
    }

@router.post("/force/{device_id}")
async def force_sync(
    device_id: str,
    direction: str = "both",  # up, down, both
    current_user = Depends(get_current_user),
    sync_service = Depends(get_sync_service)
):
    """Force sync for a specific device"""
    if direction not in ["up", "down", "both"]:
        raise HTTPException(400, "Invalid direction")
        
    # Trigger sync based on direction
    result = await sync_service.force_sync(
        user_id=current_user.id,
        device_id=device_id,
        direction=direction
    )
    
    return {
        "status": "completed",
        "changes_processed": result.changes_processed,
        "conflicts_resolved": result.conflicts_resolved
    }

async def track_sync_metrics(
    user_id: str,
    device_id: str,
    changes_up: int,
    changes_down: int,
    conflicts: int
):
    """Track sync metrics for analytics"""
    # Implementation depends on analytics backend
    pass
```

### 5. Real-time Updates

#### WebSocket Manager
```python
# funkygibbon/api/websocket/manager.py
from typing import Dict, Set, List
from fastapi import WebSocket
import json
import asyncio
from collections import defaultdict

class WebSocketManager:
    """Manage WebSocket connections for real-time updates"""
    
    def __init__(self):
        # User ID -> WebSocket connection
        self.connections: Dict[str, WebSocket] = {}
        
        # Entity ID -> Set of user IDs subscribed
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)
        
        # Lock for thread safety
        self.lock = asyncio.Lock()
        
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept new WebSocket connection"""
        await websocket.accept()
        async with self.lock:
            self.connections[user_id] = websocket
            
        # Send initial connection confirmation
        await self.send_message(user_id, {
            "type": "connected",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    async def disconnect(self, user_id: str):
        """Handle disconnection"""
        async with self.lock:
            # Remove connection
            self.connections.pop(user_id, None)
            
            # Remove all subscriptions
            for entity_id, subscribers in self.subscriptions.items():
                subscribers.discard(user_id)
                
    async def subscribe(self, user_id: str, entity_id: str):
        """Subscribe user to entity updates"""
        async with self.lock:
            self.subscriptions[entity_id].add(user_id)
            
        await self.send_message(user_id, {
            "type": "subscribed",
            "entity_id": entity_id
        })
        
    async def unsubscribe(self, user_id: str, entity_id: str):
        """Unsubscribe user from entity updates"""
        async with self.lock:
            self.subscriptions[entity_id].discard(user_id)
            
        await self.send_message(user_id, {
            "type": "unsubscribed",
            "entity_id": entity_id
        })
        
    async def broadcast_entity_change(
        self,
        entity_id: str,
        change_type: str,
        entity_data: dict
    ):
        """Broadcast entity change to subscribed users"""
        async with self.lock:
            subscribers = self.subscriptions.get(entity_id, set()).copy()
            
        message = {
            "type": "entity_change",
            "change_type": change_type,
            "entity_id": entity_id,
            "data": entity_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to all subscribers
        tasks = []
        for user_id in subscribers:
            if user_id in self.connections:
                tasks.append(self.send_message(user_id, message))
                
        await asyncio.gather(*tasks, return_exceptions=True)
        
    async def send_message(self, user_id: str, message: dict):
        """Send message to specific user"""
        websocket = self.connections.get(user_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                # Connection might be closed
                await self.disconnect(user_id)
                
    async def broadcast_to_all(self, message: dict):
        """Broadcast message to all connected users"""
        tasks = []
        for user_id in list(self.connections.keys()):
            tasks.append(self.send_message(user_id, message))
            
        await asyncio.gather(*tasks, return_exceptions=True)

# Integration with storage events
class StorageEventHandler:
    """Handle storage events and trigger WebSocket updates"""
    
    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager
        
    async def on_entity_created(self, entity: HomeEntity):
        """Handle entity creation"""
        await self.ws_manager.broadcast_entity_change(
            entity_id=entity.id,
            change_type="created",
            entity_data=entity.dict()
        )
        
    async def on_entity_updated(self, entity: HomeEntity):
        """Handle entity update"""
        await self.ws_manager.broadcast_entity_change(
            entity_id=entity.id,
            change_type="updated",
            entity_data=entity.dict()
        )
        
    async def on_entity_deleted(self, entity_id: str):
        """Handle entity deletion"""
        await self.ws_manager.broadcast_entity_change(
            entity_id=entity_id,
            change_type="deleted",
            entity_data={"id": entity_id}
        )
```

### 6. Analytics and Reporting

#### Analytics Service
```python
# funkygibbon/analytics/aggregator.py
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio

from ..storage.base import StorageInterface
from ..core.models import EntityType

class AnalyticsAggregator:
    """Aggregate data for analytics and insights"""
    
    def __init__(self, storage: StorageInterface):
        self.storage = storage
        
    async def get_usage_stats(
        self,
        user_id: str,
        period: timedelta = timedelta(days=30)
    ) -> Dict[str, Any]:
        """Get usage statistics for user"""
        end_time = datetime.utcnow()
        start_time = end_time - period
        
        # Get entity counts by type
        entity_counts = {}
        for entity_type in EntityType:
            count = await self.storage.count_entities(
                user_id=user_id,
                entity_type=entity_type
            )
            entity_counts[entity_type.value] = count
            
        # Get activity timeline
        changes = await self.storage.get_changes_in_period(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time
        )
        
        # Aggregate by day
        daily_activity = defaultdict(int)
        for change in changes:
            day = change.timestamp.date()
            daily_activity[day] += 1
            
        # Get most active devices
        device_activity = defaultdict(int)
        for change in changes:
            if change.entity_type == EntityType.DEVICE:
                device_activity[change.entity_id] += 1
                
        top_devices = sorted(
            device_activity.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "entity_counts": entity_counts,
            "total_entities": sum(entity_counts.values()),
            "daily_activity": [
                {"date": day.isoformat(), "count": count}
                for day, count in sorted(daily_activity.items())
            ],
            "top_devices": [
                {"device_id": device_id, "activity_count": count}
                for device_id, count in top_devices
            ],
            "sync_stats": await self._get_sync_stats(user_id, period)
        }
        
    async def get_energy_insights(
        self,
        user_id: str,
        period: timedelta = timedelta(days=7)
    ) -> Dict[str, Any]:
        """Analyze energy usage patterns"""
        # Get all devices with energy monitoring
        devices = await self.storage.get_entities_with_capability(
            user_id=user_id,
            capability="power_monitoring"
        )
        
        insights = {
            "total_consumption": 0,
            "device_breakdown": [],
            "peak_hours": [],
            "recommendations": []
        }
        
        for device in devices:
            # Get power readings
            readings = await self.storage.get_device_readings(
                device_id=device.id,
                metric="power",
                period=period
            )
            
            if readings:
                consumption = sum(r.value for r in readings)
                insights["total_consumption"] += consumption
                insights["device_breakdown"].append({
                    "device_id": device.id,
                    "device_name": device.display_name,
                    "consumption": consumption,
                    "percentage": 0  # Calculate later
                })
                
        # Calculate percentages
        if insights["total_consumption"] > 0:
            for item in insights["device_breakdown"]:
                item["percentage"] = (
                    item["consumption"] / insights["total_consumption"] * 100
                )
                
        # Sort by consumption
        insights["device_breakdown"].sort(
            key=lambda x: x["consumption"],
            reverse=True
        )
        
        # Generate recommendations
        insights["recommendations"] = self._generate_energy_recommendations(insights)
        
        return insights
        
    async def get_automation_suggestions(
        self,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Suggest automations based on usage patterns"""
        suggestions = []
        
        # Analyze device usage patterns
        patterns = await self._analyze_usage_patterns(user_id)
        
        # Suggest time-based automations
        for pattern in patterns:
            if pattern["confidence"] > 0.8:
                suggestions.append({
                    "type": "schedule",
                    "description": f"Turn {pattern['action']} {pattern['device_name']} at {pattern['time']}",
                    "confidence": pattern["confidence"],
                    "devices": [pattern["device_id"]],
                    "trigger": {
                        "type": "time",
                        "time": pattern["time"]
                    },
                    "action": {
                        "type": pattern["action"],
                        "device_id": pattern["device_id"]
                    }
                })
                
        # Suggest presence-based automations
        if await self._has_presence_sensors(user_id):
            suggestions.extend(await self._suggest_presence_automations(user_id))
            
        # Suggest energy-saving automations
        suggestions.extend(await self._suggest_energy_automations(user_id))
        
        return sorted(suggestions, key=lambda x: x["confidence"], reverse=True)
        
    def _generate_energy_recommendations(
        self,
        insights: Dict[str, Any]
    ) -> List[str]:
        """Generate energy saving recommendations"""
        recommendations = []
        
        # High consumption devices
        if insights["device_breakdown"]:
            top_device = insights["device_breakdown"][0]
            if top_device["percentage"] > 30:
                recommendations.append(
                    f"Consider upgrading {top_device['device_name']} to a more "
                    f"energy-efficient model (currently {top_device['percentage']:.1f}% "
                    f"of total consumption)"
                )
                
        # Peak usage times
        if insights.get("peak_hours"):
            recommendations.append(
                "Shift high-power activities outside peak hours to save on "
                "electricity costs"
            )
            
        return recommendations
```

### 7. Security and Authentication

#### Authentication Middleware
```python
# funkygibbon/api/middleware/auth.py
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional

from ...config import settings

class AuthMiddleware:
    """JWT-based authentication middleware"""
    
    def __init__(self, public_paths: List[str] = None):
        self.public_paths = public_paths or []
        self.security = HTTPBearer()
        
    async def __call__(self, request: Request, call_next):
        # Skip auth for public paths
        if request.url.path in self.public_paths:
            return await call_next(request)
            
        # Extract token
        try:
            credentials: HTTPAuthorizationCredentials = await self.security(request)
            token = credentials.credentials
        except:
            raise HTTPException(401, "Missing authorization header")
            
        # Verify token
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )
            
            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp) < datetime.utcnow():
                raise HTTPException(401, "Token expired")
                
            # Add user info to request
            request.state.user_id = payload.get("sub")
            request.state.user_role = payload.get("role", "user")
            
        except JWTError:
            raise HTTPException(401, "Invalid token")
            
        response = await call_next(request)
        return response

class RateLimitMiddleware:
    """Rate limiting middleware using sliding window"""
    
    def __init__(self, rate_limit: int = 100, window: int = 60):
        self.rate_limit = rate_limit
        self.window = window
        self.requests = defaultdict(deque)
        
    async def __call__(self, request: Request, call_next):
        # Get client identifier
        client_id = request.client.host
        if hasattr(request.state, "user_id"):
            client_id = request.state.user_id
            
        # Check rate limit
        now = time.time()
        requests = self.requests[client_id]
        
        # Remove old requests
        while requests and requests[0] < now - self.window:
            requests.popleft()
            
        # Check limit
        if len(requests) >= self.rate_limit:
            raise HTTPException(429, "Rate limit exceeded")
            
        # Add current request
        requests.append(now)
        
        # Add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(self.rate_limit - len(requests))
        response.headers["X-RateLimit-Reset"] = str(int(now + self.window))
        
        return response
```

### 8. Background Tasks

#### Task Queue
```python
# funkygibbon/utils/background.py
from typing import Callable, Any, Dict
import asyncio
from datetime import datetime, timedelta
import pickle
from redis import asyncio as aioredis

class TaskQueue:
    """Redis-based task queue for background processing"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis = None
        self.workers = []
        self.running = False
        
    async def initialize(self):
        """Initialize Redis connection"""
        self.redis = await aioredis.from_url(self.redis_url)
        
    async def enqueue(
        self,
        task_name: str,
        args: tuple = (),
        kwargs: dict = None,
        delay: Optional[timedelta] = None
    ):
        """Add task to queue"""
        task = {
            "id": str(uuid.uuid4()),
            "name": task_name,
            "args": args,
            "kwargs": kwargs or {},
            "created_at": datetime.utcnow().isoformat(),
            "attempts": 0
        }
        
        # Schedule delayed task
        if delay:
            execute_at = datetime.utcnow() + delay
            await self.redis.zadd(
                "delayed_tasks",
                {pickle.dumps(task): execute_at.timestamp()}
            )
        else:
            # Add to immediate queue
            await self.redis.lpush("task_queue", pickle.dumps(task))
            
    async def process_tasks(self, task_handlers: Dict[str, Callable]):
        """Process tasks from queue"""
        self.running = True
        
        while self.running:
            # Check for delayed tasks
            await self._process_delayed_tasks()
            
            # Get next task
            task_data = await self.redis.brpop("task_queue", timeout=1)
            if not task_data:
                continue
                
            _, task_bytes = task_data
            task = pickle.loads(task_bytes)
            
            # Find handler
            handler = task_handlers.get(task["name"])
            if not handler:
                print(f"No handler for task: {task['name']}")
                continue
                
            # Execute task
            try:
                await handler(*task["args"], **task["kwargs"])
            except Exception as e:
                print(f"Task failed: {e}")
                
                # Retry logic
                task["attempts"] += 1
                if task["attempts"] < 3:
                    # Re-queue with delay
                    await self.enqueue(
                        task["name"],
                        task["args"],
                        task["kwargs"],
                        delay=timedelta(seconds=60 * task["attempts"])
                    )
                    
    async def _process_delayed_tasks(self):
        """Move delayed tasks to main queue"""
        now = datetime.utcnow().timestamp()
        
        # Get tasks ready to execute
        tasks = await self.redis.zrangebyscore(
            "delayed_tasks",
            0,
            now,
            withscores=False
        )
        
        for task_bytes in tasks:
            # Move to main queue
            await self.redis.lpush("task_queue", task_bytes)
            await self.redis.zrem("delayed_tasks", task_bytes)

# Background task handlers
async def cleanup_old_changes(days: int = 90):
    """Clean up old change records"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    # Implementation depends on storage
    
async def generate_analytics_report(user_id: str, period: str):
    """Generate and email analytics report"""
    # Implementation
    
async def sync_with_external_service(entity_id: str, service: str):
    """Sync entity with external service"""
    # Implementation
```

## Testing Strategy

### Unit Tests
```python
# tests/unit/test_models.py
import pytest
from funkygibbon.core.models import HomeEntity, EntityType

class TestHomeEntity:
    def test_create_entity(self):
        entity = HomeEntity(
            entity_type=EntityType.DEVICE,
            content={"name": "Test Device"},
            user_id="test-user"
        )
        
        assert entity.entity_type == EntityType.DEVICE
        assert entity.display_name == "Test Device"
        assert entity.is_deleted is False
        
    def test_update_content(self):
        entity = HomeEntity(
            entity_type=EntityType.DEVICE,
            content={"name": "Test"},
            user_id="test-user"
        )
        
        original_modified = entity.last_modified
        entity.update_content("status", "online")
        
        assert entity.content["status"] == "online"
        assert entity.last_modified > original_modified
```

### Integration Tests
```python
# tests/integration/test_sync.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_sync_flow(async_client: AsyncClient, auth_headers):
    # Create entity
    create_response = await async_client.post(
        "/api/entities",
        json={
            "entity_type": "device",
            "content": {"name": "Test Device"}
        },
        headers=auth_headers
    )
    assert create_response.status_code == 201
    entity = create_response.json()
    
    # Sync request
    sync_request = {
        "protocol_version": "inbetweenies-v1",
        "device_id": "test-device",
        "user_id": "test-user",
        "vector_clock": {},
        "changes": [
            {
                "change_type": "update",
                "entity_id": entity["id"],
                "entity_version": "v2",
                "content": {"status": "online"},
                "timestamp": datetime.utcnow().isoformat(),
                "parent_versions": [entity["version"]],
                "user_id": "test-user",
                "device_id": "test-device"
            }
        ]
    }
    
    sync_response = await async_client.post(
        "/api/sync/inbetweenies",
        json=sync_request,
        headers=auth_headers
    )
    
    assert sync_response.status_code == 200
    result = sync_response.json()
    assert "vector_clock" in result
    assert len(result["conflicts"]) == 0
```

## Deployment

### Docker Configuration
```dockerfile
# docker/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/prod.txt .
RUN pip install --no-cache-dir -r prod.txt

# Copy application
COPY funkygibbon/ ./funkygibbon/
COPY scripts/ ./scripts/

# Run as non-root
RUN useradd -m -u 1000 funkygibbon
USER funkygibbon

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health').raise_for_status()"

EXPOSE 8000

CMD ["uvicorn", "funkygibbon.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose
```yaml
# docker/docker-compose.yml
version: '3.8'

services:
  funkygibbon:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/funkygibbon
      - REDIS_URL=redis://redis:6379
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on:
      - db
      - redis
    volumes:
      - ./logs:/app/logs
      
  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=funkygibbon
    volumes:
      - postgres_data:/var/lib/postgresql/data
      
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
      
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - funkygibbon

volumes:
  postgres_data:
  redis_data:
```

## Production Considerations

### Performance Optimization

1. **Database Optimization**
   - Connection pooling
   - Query optimization with EXPLAIN ANALYZE
   - Proper indexing strategy
   - Partitioning for large tables

2. **Caching Strategy**
   - Redis for frequently accessed data
   - HTTP caching headers
   - Query result caching
   - CDN for static assets

3. **Async Processing**
   - Background task queue
   - Async I/O throughout
   - WebSocket for real-time updates
   - Batch processing for bulk operations

### Monitoring and Observability

1. **Metrics Collection**
   - Prometheus metrics
   - Custom business metrics
   - Performance tracking
   - Error rate monitoring

2. **Logging**
   - Structured JSON logging
   - Log aggregation with ELK
   - Correlation IDs
   - Error tracking with Sentry

3. **Tracing**
   - OpenTelemetry integration
   - Distributed tracing
   - Performance profiling
   - Request flow visualization

### Security Hardening

1. **API Security**
   - Rate limiting
   - Input validation
   - SQL injection prevention
   - XSS protection

2. **Data Protection**
   - Encryption at rest
   - TLS for all connections
   - Secure password hashing
   - API key rotation

3. **Access Control**
   - JWT with short expiry
   - Role-based permissions
   - API key scoping
   - Audit logging

## Conclusion

FunkyGibbon provides a robust, scalable backend for the WildThing ecosystem. Its architecture supports:

- High-performance sync with conflict resolution
- Real-time updates via WebSocket
- Comprehensive analytics and insights
- Enterprise-grade security
- Horizontal scalability
- Third-party integrations

The service is designed to grow with user needs while maintaining reliability and performance.