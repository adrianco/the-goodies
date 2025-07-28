# FunkyGibbon Python Service - Detailed Development Steps

## Overview

FunkyGibbon is the Python backend service component of The Goodies project, providing centralized data synchronization, persistence, and coordination for the distributed smart home knowledge graph system.

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Poetry (for dependency management)
- Docker (for containerization)
- Basic knowledge of FastAPI, SQLAlchemy, and asyncio

## Step 1: Project Structure Setup

### 1.1 Initialize Python Project

```bash
cd FunkyGibbon
poetry init --name funkygibbon --python "^3.11"
```

### 1.2 Project Structure

```bash
mkdir -p funkygibbon/{core,storage,inbetweenies,api,mcp,tests}
mkdir -p funkygibbon/core/{models,entities,relationships}
mkdir -p funkygibbon/storage/{postgresql,redis_cache,migrations}
mkdir -p funkygibbon/api/{routes,middleware,dependencies}
mkdir -p funkygibbon/inbetweenies/{sync,conflict,vector_clock}
mkdir -p funkygibbon/tests/{unit,integration,e2e,fixtures}
touch funkygibbon/__init__.py
```

### 1.3 Configure Poetry Dependencies

```toml
# pyproject.toml
[tool.poetry]
name = "funkygibbon"
version = "1.0.0"
description = "Smart Home Knowledge Graph Backend Service"
authors = ["Your Name <email@example.com>"]
readme = "README.md"

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.109.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
pydantic = "^2.5.0"
sqlalchemy = "^2.0.0"
alembic = "^1.13.0"
asyncpg = "^0.29.0"
redis = "^5.0.0"
python-multipart = "^0.0.6"
python-jose = {extras = ["cryptography"], version = "^3.3.0"}
passlib = {extras = ["bcrypt"], version = "^1.7.4"}
python-dotenv = "^1.0.0"
httpx = "^0.26.0"
orjson = "^3.9.0"
pydantic-settings = "^2.1.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
pytest-asyncio = "^0.23.0"
pytest-cov = "^4.1.0"
black = "^24.1.0"
flake8 = "^7.0.0"
mypy = "^1.8.0"
pre-commit = "^3.6.0"
factory-boy = "^3.3.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.black]
line-length = 88
target-version = ['py311']

[tool.mypy]
python_version = "3.11"
disallow_untyped_defs = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
```

### 1.4 Install Dependencies

```bash
poetry install
poetry shell  # Activate virtual environment
```

## Step 2: Core Data Models

### 2.1 Base Models and Enums

```python
# funkygibbon/core/models.py
from enum import Enum
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from uuid import uuid4

class EntityType(str, Enum):
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
    MANUAL = "manual"
    HOMEKIT = "homekit"
    MATTER = "matter"
    IMPORTED = "imported"
    AUTOMATED = "automated"

class RelationshipType(str, Enum):
    LOCATED_IN = "located_in"
    CONTROLS = "controls"
    CONNECTS_TO = "connects_to"
    PART_OF = "part_of"
    MANAGES = "manages"
    DOCUMENTED_BY = "documented_by"
    PROCEDURE_FOR = "procedure_for"
    TRIGGERED_BY = "triggered_by"
    DEPENDS_ON = "depends_on"

class BaseEntity(BaseModel):
    """Base model for all entities"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    version: str
    entity_type: EntityType
    parent_versions: List[str] = Field(default_factory=list)
    content: Dict[str, Any] = Field(default_factory=dict)
    user_id: str
    source_type: SourceType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    
    @classmethod
    def generate_version(cls, device_id: str, sequence: int = 0) -> str:
        """Generate version string with format: timestamp-device-sequence"""
        timestamp = datetime.utcnow().isoformat()
        return f"{timestamp}-{device_id}-{sequence:03d}"
```

### 2.2 Entity Models

```python
# funkygibbon/core/entities.py
from typing import Optional, List
from .models import BaseEntity, EntityType, SourceType

class HomeEntity(BaseEntity):
    """Home entity model"""
    entity_type: EntityType = EntityType.HOME
    
    @property
    def name(self) -> str:
        return self.content.get("name", "")
    
    @name.setter
    def name(self, value: str):
        self.content["name"] = value
    
    @property
    def address(self) -> Optional[str]:
        return self.content.get("address")
    
    @address.setter
    def address(self, value: Optional[str]):
        self.content["address"] = value
    
    @property
    def is_primary(self) -> bool:
        return self.content.get("is_primary", False)

class RoomEntity(BaseEntity):
    """Room entity model"""
    entity_type: EntityType = EntityType.ROOM
    
    @property
    def name(self) -> str:
        return self.content.get("name", "")
    
    @property
    def home_id(self) -> Optional[str]:
        return self.content.get("home_id")
    
    @property
    def floor(self) -> Optional[int]:
        return self.content.get("floor")

class DeviceEntity(BaseEntity):
    """Device entity model"""
    entity_type: EntityType = EntityType.DEVICE
    
    @property
    def name(self) -> str:
        return self.content.get("name", "")
    
    @property
    def room_id(self) -> Optional[str]:
        return self.content.get("room_id")
    
    @property
    def manufacturer(self) -> Optional[str]:
        return self.content.get("manufacturer")
    
    @property
    def model(self) -> Optional[str]:
        return self.content.get("model")
    
    @property
    def capabilities(self) -> List[str]:
        return self.content.get("capabilities", [])
    
    @property
    def is_reachable(self) -> bool:
        return self.content.get("is_reachable", True)

# Factory function for creating entities
def create_entity(entity_type: EntityType, **kwargs) -> BaseEntity:
    """Factory function to create appropriate entity type"""
    entity_map = {
        EntityType.HOME: HomeEntity,
        EntityType.ROOM: RoomEntity,
        EntityType.DEVICE: DeviceEntity,
        # Add other entity types as implemented
    }
    
    entity_class = entity_map.get(entity_type, BaseEntity)
    return entity_class(entity_type=entity_type, **kwargs)
```

### 2.3 Relationship Models

```python
# funkygibbon/core/relationships.py
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from uuid import uuid4
from .models import RelationshipType

class EntityRelationship(BaseModel):
    """Model for relationships between entities"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    from_entity_id: str
    to_entity_id: str
    relationship_type: RelationshipType
    properties: Dict[str, Any] = Field(default_factory=dict)
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def reverse(self) -> "EntityRelationship":
        """Create reverse relationship"""
        reverse_type_map = {
            RelationshipType.LOCATED_IN: RelationshipType.CONTAINS,
            RelationshipType.CONTROLS: RelationshipType.CONTROLLED_BY,
            RelationshipType.PART_OF: RelationshipType.HAS_PART,
            # Add other reverse mappings
        }
        
        return EntityRelationship(
            from_entity_id=self.to_entity_id,
            to_entity_id=self.from_entity_id,
            relationship_type=reverse_type_map.get(
                self.relationship_type, 
                self.relationship_type
            ),
            properties=self.properties,
            user_id=self.user_id
        )
```

## Step 3: Database Layer

### 3.1 Database Configuration

```python
# funkygibbon/storage/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class DatabaseSettings(BaseSettings):
    # PostgreSQL settings
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "funkygibbon"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    
    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    # Connection pool settings
    db_pool_size: int = 20
    db_max_overflow: int = 40
    db_pool_timeout: int = 30
    
    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    class Config:
        env_file = ".env"

settings = DatabaseSettings()
```

### 3.2 SQLAlchemy Models

```python
# funkygibbon/storage/postgresql/models.py
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

Base = declarative_base()

class EntityDB(Base):
    __tablename__ = "entities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version = Column(String, primary_key=True)
    entity_type = Column(String(50), nullable=False, index=True)
    parent_versions = Column(JSON, default=list)
    content = Column(JSON, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    source_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_modified = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    deleted_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('id', 'version', name='uq_entity_version'),
        Index('idx_entities_modified', 'last_modified'),
        Index('idx_entities_type_user', 'entity_type', 'user_id'),
    )

class RelationshipDB(Base):
    __tablename__ = "relationships"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    to_entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    relationship_type = Column(String(50), nullable=False, index=True)
    properties = Column(JSON, default=dict)
    user_id = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_relationships_from', 'from_entity_id'),
        Index('idx_relationships_to', 'to_entity_id'),
        Index('idx_relationships_type', 'relationship_type'),
    )

class VectorClockDB(Base):
    __tablename__ = "vector_clocks"
    
    user_id = Column(String, primary_key=True)
    device_id = Column(String, primary_key=True)
    clock_value = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class ConflictDB(Base):
    __tablename__ = "conflicts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    local_version = Column(String, nullable=False)
    remote_version = Column(String, nullable=False)
    conflict_type = Column(String(50), nullable=False)
    resolution_status = Column(String(50), default="pending")
    resolved_at = Column(DateTime)
    resolved_by = Column(String)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
```

### 3.3 Database Repository

```python
# funkygibbon/storage/postgresql/repository.py
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
import logging

from ...core.entities import BaseEntity, create_entity
from ...core.models import EntityType
from .models import EntityDB, RelationshipDB, VectorClockDB

logger = logging.getLogger(__name__)

class EntityRepository:
    """Repository for entity operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def save(self, entity: BaseEntity) -> BaseEntity:
        """Save or update an entity"""
        db_entity = EntityDB(
            id=entity.id,
            version=entity.version,
            entity_type=entity.entity_type.value,
            parent_versions=entity.parent_versions,
            content=entity.content,
            user_id=entity.user_id,
            source_type=entity.source_type.value,
            created_at=entity.created_at,
            last_modified=entity.last_modified
        )
        
        self.session.add(db_entity)
        await self.session.commit()
        await self.session.refresh(db_entity)
        
        logger.info(f"Saved entity {entity.id} version {entity.version}")
        return entity
    
    async def save_many(self, entities: List[BaseEntity]) -> List[BaseEntity]:
        """Bulk save entities"""
        db_entities = [
            EntityDB(
                id=entity.id,
                version=entity.version,
                entity_type=entity.entity_type.value,
                parent_versions=entity.parent_versions,
                content=entity.content,
                user_id=entity.user_id,
                source_type=entity.source_type.value,
                created_at=entity.created_at,
                last_modified=entity.last_modified
            )
            for entity in entities
        ]
        
        self.session.add_all(db_entities)
        await self.session.commit()
        
        logger.info(f"Saved {len(entities)} entities")
        return entities
    
    async def fetch_by_id(self, entity_id: str) -> Optional[BaseEntity]:
        """Fetch latest version of an entity"""
        result = await self.session.execute(
            select(EntityDB)
            .where(EntityDB.id == entity_id)
            .order_by(EntityDB.created_at.desc())
            .limit(1)
        )
        
        db_entity = result.scalar_one_or_none()
        if not db_entity:
            return None
        
        return self._db_to_entity(db_entity)
    
    async def fetch_by_version(self, entity_id: str, version: str) -> Optional[BaseEntity]:
        """Fetch specific version of an entity"""
        result = await self.session.execute(
            select(EntityDB)
            .where(and_(
                EntityDB.id == entity_id,
                EntityDB.version == version
            ))
        )
        
        db_entity = result.scalar_one_or_none()
        if not db_entity:
            return None
        
        return self._db_to_entity(db_entity)
    
    async def fetch_all_by_type(
        self, 
        entity_type: EntityType, 
        user_id: str,
        limit: int = 1000,
        offset: int = 0
    ) -> List[BaseEntity]:
        """Fetch all entities of a specific type"""
        result = await self.session.execute(
            select(EntityDB)
            .where(and_(
                EntityDB.entity_type == entity_type.value,
                EntityDB.user_id == user_id,
                EntityDB.deleted_at.is_(None)
            ))
            .order_by(EntityDB.last_modified.desc())
            .limit(limit)
            .offset(offset)
        )
        
        db_entities = result.scalars().all()
        return [self._db_to_entity(db_entity) for db_entity in db_entities]
    
    async def fetch_modified_since(
        self, 
        since: datetime, 
        user_id: str,
        limit: int = 1000
    ) -> List[BaseEntity]:
        """Fetch entities modified since a specific time"""
        result = await self.session.execute(
            select(EntityDB)
            .where(and_(
                EntityDB.user_id == user_id,
                EntityDB.last_modified > since
            ))
            .order_by(EntityDB.last_modified.asc())
            .limit(limit)
        )
        
        db_entities = result.scalars().all()
        return [self._db_to_entity(db_entity) for db_entity in db_entities]
    
    async def soft_delete(self, entity_id: str, version: str) -> bool:
        """Soft delete an entity"""
        result = await self.session.execute(
            select(EntityDB)
            .where(and_(
                EntityDB.id == entity_id,
                EntityDB.version == version
            ))
        )
        
        db_entity = result.scalar_one_or_none()
        if not db_entity:
            return False
        
        db_entity.deleted_at = datetime.utcnow()
        await self.session.commit()
        
        logger.info(f"Soft deleted entity {entity_id} version {version}")
        return True
    
    def _db_to_entity(self, db_entity: EntityDB) -> BaseEntity:
        """Convert database model to domain entity"""
        entity_type = EntityType(db_entity.entity_type)
        return create_entity(
            entity_type=entity_type,
            id=str(db_entity.id),
            version=db_entity.version,
            parent_versions=db_entity.parent_versions,
            content=db_entity.content,
            user_id=db_entity.user_id,
            source_type=db_entity.source_type,
            created_at=db_entity.created_at,
            last_modified=db_entity.last_modified
        )
```

### 3.4 Redis Cache

```python
# funkygibbon/storage/redis_cache/cache.py
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import timedelta
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class RedisCache:
    """Redis cache for entities and sync data"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.default_ttl = timedelta(hours=1)
    
    async def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get entity from cache"""
        key = f"entity:{entity_id}"
        data = await self.redis.get(key)
        
        if data:
            logger.debug(f"Cache hit for entity {entity_id}")
            return json.loads(data)
        
        logger.debug(f"Cache miss for entity {entity_id}")
        return None
    
    async def set_entity(
        self, 
        entity_id: str, 
        entity_data: Dict[str, Any],
        ttl: Optional[timedelta] = None
    ) -> None:
        """Cache entity data"""
        key = f"entity:{entity_id}"
        ttl = ttl or self.default_ttl
        
        await self.redis.setex(
            key,
            ttl,
            json.dumps(entity_data)
        )
        logger.debug(f"Cached entity {entity_id}")
    
    async def delete_entity(self, entity_id: str) -> None:
        """Remove entity from cache"""
        key = f"entity:{entity_id}"
        await self.redis.delete(key)
        logger.debug(f"Deleted entity {entity_id} from cache")
    
    async def get_user_entities(self, user_id: str) -> List[str]:
        """Get list of cached entity IDs for user"""
        pattern = f"user:{user_id}:entities"
        data = await self.redis.get(pattern)
        
        if data:
            return json.loads(data)
        return []
    
    async def set_user_entities(
        self, 
        user_id: str, 
        entity_ids: List[str],
        ttl: Optional[timedelta] = None
    ) -> None:
        """Cache user's entity list"""
        key = f"user:{user_id}:entities"
        ttl = ttl or self.default_ttl
        
        await self.redis.setex(
            key,
            ttl,
            json.dumps(entity_ids)
        )
    
    async def get_vector_clock(self, user_id: str, device_id: str) -> Optional[str]:
        """Get vector clock value"""
        key = f"clock:{user_id}:{device_id}"
        return await self.redis.get(key)
    
    async def set_vector_clock(
        self, 
        user_id: str, 
        device_id: str, 
        clock_value: str
    ) -> None:
        """Set vector clock value"""
        key = f"clock:{user_id}:{device_id}"
        await self.redis.set(key, clock_value)
    
    async def acquire_sync_lock(
        self, 
        user_id: str, 
        device_id: str, 
        ttl: int = 300
    ) -> bool:
        """Acquire sync lock for user/device"""
        key = f"sync_lock:{user_id}:{device_id}"
        return await self.redis.set(key, "1", nx=True, ex=ttl)
    
    async def release_sync_lock(self, user_id: str, device_id: str) -> None:
        """Release sync lock"""
        key = f"sync_lock:{user_id}:{device_id}"
        await self.redis.delete(key)
```

## Step 4: Inbetweenies Sync Protocol

### 4.1 Sync Messages

```python
# funkygibbon/inbetweenies/messages.py
from enum import Enum
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class ChangeType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

class CompressionType(str, Enum):
    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"
    BROTLI = "brotli"

class SyncStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"

class ConflictType(str, Enum):
    VERSION_MISMATCH = "version_mismatch"
    CONTENT_CONFLICT = "content_conflict"
    DELETE_UPDATE = "delete_update"
    CYCLIC_RELATIONSHIP = "cyclic_relationship"

class ResolutionStrategy(str, Enum):
    ACCEPT_LOCAL = "accept_local"
    ACCEPT_SERVER = "accept_server"
    MERGE = "merge"
    MANUAL = "manual"

class EntityChange(BaseModel):
    change_type: ChangeType
    entity_id: str
    entity_version: str
    entity_type: Optional[str] = None
    parent_versions: List[str] = Field(default_factory=list)
    content: Optional[Dict[str, Any]] = None
    timestamp: datetime
    checksum: Optional[str] = None
    device_id: str
    user_id: str

class ConflictInfo(BaseModel):
    entity_id: str
    conflict_type: ConflictType
    local_version: str
    server_version: str
    resolution_hint: Optional[ResolutionStrategy] = None
    conflict_details: Optional[Dict[str, Any]] = None

class RequestMetadata(BaseModel):
    client_version: str
    platform: str
    sync_reason: str

class InbetweeniesRequest(BaseModel):
    protocol_version: str = "inbetweenies-v1"
    device_id: str
    user_id: str
    session_id: str
    vector_clock: Dict[str, str]
    changes: List[EntityChange]
    compression: CompressionType = CompressionType.NONE
    capabilities: List[str] = Field(default_factory=list)
    metadata: RequestMetadata

class RateLimitInfo(BaseModel):
    remaining: int
    reset_at: datetime

class InbetweeniesResponse(BaseModel):
    protocol_version: str = "inbetweenies-v1"
    server_time: datetime
    session_id: str
    vector_clock: Dict[str, str]
    changes: List[EntityChange]
    conflicts: List[ConflictInfo]
    next_sync_token: Optional[str] = None
    sync_status: SyncStatus
    server_capabilities: List[str] = Field(default_factory=list)
    rate_limit: Optional[RateLimitInfo] = None
```

### 4.2 Vector Clock Implementation

```python
# funkygibbon/inbetweenies/vector_clock.py
from datetime import datetime
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class VectorClock:
    """Vector clock for distributed synchronization"""
    
    def __init__(self, clocks: Optional[Dict[str, str]] = None):
        self.clocks = clocks or {}
    
    def increment(self, node_id: str) -> str:
        """Increment clock for node and return new version"""
        current = self.clocks.get(node_id, self._zero_version())
        timestamp, _, seq = self._parse_version(current)
        new_seq = int(seq) + 1
        new_timestamp = datetime.utcnow().isoformat()
        new_version = f"{new_timestamp}-{node_id}-{new_seq:03d}"
        self.clocks[node_id] = new_version
        return new_version
    
    def merge(self, other_clocks: Dict[str, str]) -> None:
        """Merge with another vector clock"""
        for node_id, version in other_clocks.items():
            if node_id not in self.clocks:
                self.clocks[node_id] = version
            else:
                # Keep the greater version
                if self._compare_versions(version, self.clocks[node_id]) > 0:
                    self.clocks[node_id] = version
    
    def happens_before(self, other: "VectorClock") -> bool:
        """Check if this clock happens before other"""
        for node_id, version in self.clocks.items():
            other_version = other.clocks.get(node_id, self._zero_version())
            if self._compare_versions(version, other_version) > 0:
                return False
        return True
    
    def are_concurrent(self, other: "VectorClock") -> bool:
        """Check if clocks are concurrent (no causal relationship)"""
        return not self.happens_before(other) and not other.happens_before(self)
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary"""
        return self.clocks.copy()
    
    @classmethod
    def from_dict(cls, clocks: Dict[str, str]) -> "VectorClock":
        """Create from dictionary"""
        return cls(clocks)
    
    def _zero_version(self) -> str:
        """Get zero version"""
        return "1970-01-01T00:00:00-unknown-000"
    
    def _parse_version(self, version: str) -> Tuple[str, str, str]:
        """Parse version string"""
        parts = version.split("-")
        if len(parts) < 3:
            return "", "", "000"
        
        # Handle ISO timestamp with timezone
        timestamp_parts = []
        node_id_index = len(parts) - 2
        
        for i in range(node_id_index):
            timestamp_parts.append(parts[i])
        
        timestamp = "-".join(timestamp_parts)
        node_id = parts[node_id_index]
        sequence = parts[-1]
        
        return timestamp, node_id, sequence
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare two version strings"""
        t1, _, s1 = self._parse_version(v1)
        t2, _, s2 = self._parse_version(v2)
        
        # Compare timestamps
        if t1 < t2:
            return -1
        if t1 > t2:
            return 1
        
        # Compare sequences
        seq1 = int(s1) if s1.isdigit() else 0
        seq2 = int(s2) if s2.isdigit() else 0
        
        if seq1 < seq2:
            return -1
        if seq1 > seq2:
            return 1
        
        return 0
```

### 4.3 Conflict Resolution

```python
# funkygibbon/inbetweenies/conflict_resolution.py
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from ..core.entities import BaseEntity
from .messages import ConflictInfo, ConflictType, ResolutionStrategy, EntityChange

logger = logging.getLogger(__name__)

class ConflictResolver:
    """Handles conflict detection and resolution"""
    
    def detect_conflict(
        self,
        local_entity: Optional[BaseEntity],
        remote_change: EntityChange
    ) -> Optional[ConflictInfo]:
        """Detect if there's a conflict between local and remote"""
        # No conflict for new entities
        if not local_entity:
            return None
        
        # Deleted locally but updated remotely
        if hasattr(local_entity, 'deleted_at') and local_entity.deleted_at and remote_change.change_type == ChangeType.UPDATE:
            return ConflictInfo(
                entity_id=local_entity.id,
                conflict_type=ConflictType.DELETE_UPDATE,
                local_version=local_entity.version,
                server_version=remote_change.entity_version
            )
        
        # Check version lineage
        if local_entity.version not in remote_change.parent_versions:
            # Versions have diverged
            return ConflictInfo(
                entity_id=local_entity.id,
                conflict_type=ConflictType.VERSION_MISMATCH,
                local_version=local_entity.version,
                server_version=remote_change.entity_version,
                conflict_details=self._analyze_content_differences(
                    local_entity.content,
                    remote_change.content or {}
                )
            )
        
        return None
    
    def resolve(
        self,
        conflict: ConflictInfo,
        local_entity: BaseEntity,
        remote_change: EntityChange,
        strategy: Optional[ResolutionStrategy] = None
    ) -> Optional[BaseEntity]:
        """Resolve conflict based on strategy"""
        if strategy == ResolutionStrategy.ACCEPT_LOCAL:
            return self._keep_local(local_entity, remote_change)
        
        elif strategy == ResolutionStrategy.ACCEPT_SERVER:
            return self._accept_remote(local_entity, remote_change)
        
        elif strategy == ResolutionStrategy.MERGE:
            return self._merge_changes(local_entity, remote_change, conflict)
        
        else:
            # Automatic resolution based on heuristics
            return self._auto_resolve(conflict, local_entity, remote_change)
    
    def _auto_resolve(
        self,
        conflict: ConflictInfo,
        local_entity: BaseEntity,
        remote_change: EntityChange
    ) -> Optional[BaseEntity]:
        """Automatic conflict resolution"""
        # Last-write-wins for simple conflicts
        if conflict.conflict_type == ConflictType.VERSION_MISMATCH:
            local_time = local_entity.last_modified
            remote_time = remote_change.timestamp
            
            if remote_time > local_time:
                logger.info(f"Auto-resolving conflict for {local_entity.id}: accepting server version")
                return self._accept_remote(local_entity, remote_change)
            else:
                logger.info(f"Auto-resolving conflict for {local_entity.id}: keeping local version")
                return self._keep_local(local_entity, remote_change)
        
        # Delete wins for delete-update conflicts
        elif conflict.conflict_type == ConflictType.DELETE_UPDATE:
            if hasattr(local_entity, 'deleted_at') and local_entity.deleted_at:
                logger.info(f"Auto-resolving conflict for {local_entity.id}: keeping local delete")
                return self._keep_local(local_entity, remote_change)
            else:
                logger.info(f"Auto-resolving conflict for {local_entity.id}: accepting server delete")
                return self._accept_remote(local_entity, remote_change)
        
        # Manual resolution required for complex conflicts
        logger.warning(f"Cannot auto-resolve conflict for {local_entity.id}")
        return None
    
    def _keep_local(
        self,
        local_entity: BaseEntity,
        remote_change: EntityChange
    ) -> BaseEntity:
        """Keep local version but update parent versions"""
        local_entity.parent_versions.append(remote_change.entity_version)
        return local_entity
    
    def _accept_remote(
        self,
        local_entity: BaseEntity,
        remote_change: EntityChange
    ) -> BaseEntity:
        """Accept remote version"""
        # Update local entity with remote data
        local_entity.version = remote_change.entity_version
        local_entity.parent_versions = remote_change.parent_versions
        if remote_change.content:
            local_entity.content = remote_change.content
        local_entity.last_modified = remote_change.timestamp
        return local_entity
    
    def _merge_changes(
        self,
        local_entity: BaseEntity,
        remote_change: EntityChange,
        conflict: ConflictInfo
    ) -> BaseEntity:
        """Three-way merge of changes"""
        merged_content = {}
        local_content = local_entity.content
        remote_content = remote_change.content or {}
        
        # Get all unique keys
        all_keys = set(local_content.keys()) | set(remote_content.keys())
        
        for key in all_keys:
            local_value = local_content.get(key)
            remote_value = remote_content.get(key)
            
            if local_value == remote_value:
                # No conflict for this field
                merged_content[key] = local_value
            elif key in remote_content and key not in local_content:
                # Remote added field
                merged_content[key] = remote_value
            elif key in local_content and key not in remote_content:
                # Local added field
                merged_content[key] = local_value
            else:
                # Both changed - use resolution strategy
                merged_content[key] = self._resolve_field_conflict(
                    key, local_value, remote_value
                )
        
        # Create merged entity
        local_entity.content = merged_content
        local_entity.parent_versions = [local_entity.version, remote_change.entity_version]
        local_entity.version = BaseEntity.generate_version("merge", 0)
        local_entity.last_modified = datetime.utcnow()
        
        return local_entity
    
    def _resolve_field_conflict(
        self,
        field: str,
        local_value: Any,
        remote_value: Any
    ) -> Any:
        """Resolve conflict for individual field"""
        # Special handling for specific fields
        if field == "name":
            # Prefer longer name (more descriptive)
            if len(str(remote_value)) > len(str(local_value)):
                return remote_value
            return local_value
        
        elif field in ["is_reachable", "is_active", "is_enabled"]:
            # Prefer "true" for availability fields
            return local_value or remote_value
        
        elif field == "capabilities":
            # Merge lists
            if isinstance(local_value, list) and isinstance(remote_value, list):
                return list(set(local_value + remote_value))
        
        # Default: last-write-wins (remote)
        return remote_value
    
    def _analyze_content_differences(
        self,
        local_content: Dict[str, Any],
        remote_content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze differences between content"""
        conflicting_fields = []
        local_values = {}
        server_values = {}
        
        all_keys = set(local_content.keys()) | set(remote_content.keys())
        
        for key in all_keys:
            local_val = local_content.get(key)
            remote_val = remote_content.get(key)
            
            if local_val != remote_val:
                conflicting_fields.append(key)
                if local_val is not None:
                    local_values[key] = local_val
                if remote_val is not None:
                    server_values[key] = remote_val
        
        return {
            "conflicting_fields": conflicting_fields,
            "local_values": local_values,
            "server_values": server_values
        }
```

### 4.4 Sync Service

```python
# funkygibbon/inbetweenies/sync_service.py
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.entities import BaseEntity
from ..storage.postgresql.repository import EntityRepository
from ..storage.redis_cache.cache import RedisCache
from .messages import (
    InbetweeniesRequest, InbetweeniesResponse, EntityChange,
    ConflictInfo, SyncStatus, ChangeType
)
from .vector_clock import VectorClock
from .conflict_resolution import ConflictResolver

logger = logging.getLogger(__name__)

class SyncService:
    """Handles Inbetweenies protocol synchronization"""
    
    def __init__(
        self,
        db_session: AsyncSession,
        redis_cache: RedisCache
    ):
        self.repository = EntityRepository(db_session)
        self.cache = redis_cache
        self.conflict_resolver = ConflictResolver()
        self.server_clock = VectorClock()
    
    async def handle_sync(
        self,
        request: InbetweeniesRequest
    ) -> InbetweeniesResponse:
        """Process sync request and return response"""
        logger.info(f"Processing sync for user {request.user_id} device {request.device_id}")
        
        # Acquire sync lock
        lock_acquired = await self.cache.acquire_sync_lock(
            request.user_id,
            request.device_id
        )
        
        if not lock_acquired:
            logger.warning(f"Sync already in progress for {request.user_id}/{request.device_id}")
            return InbetweeniesResponse(
                server_time=datetime.utcnow(),
                session_id=request.session_id,
                vector_clock=request.vector_clock,
                changes=[],
                conflicts=[],
                sync_status=SyncStatus.FAILED,
                server_capabilities=["batch_1000", "compression_gzip"]
            )
        
        try:
            # Validate request
            self._validate_request(request)
            
            # Apply client changes
            conflicts = await self._apply_changes(request.changes)
            
            # Get changes for client
            client_changes = await self._get_changes_for_client(
                request.user_id,
                request.vector_clock,
                request.device_id
            )
            
            # Update vector clocks
            self.server_clock.merge(request.vector_clock)
            server_version = self.server_clock.increment("server")
            
            # Save vector clock
            await self._save_vector_clock(
                request.user_id,
                request.device_id,
                request.vector_clock
            )
            
            return InbetweeniesResponse(
                server_time=datetime.utcnow(),
                session_id=request.session_id,
                vector_clock=self.server_clock.to_dict(),
                changes=client_changes,
                conflicts=conflicts,
                sync_status=SyncStatus.SUCCESS if not conflicts else SyncStatus.PARTIAL,
                server_capabilities=["batch_1000", "compression_gzip", "streaming"],
                rate_limit=None  # TODO: Implement rate limiting
            )
            
        finally:
            # Release sync lock
            await self.cache.release_sync_lock(request.user_id, request.device_id)
    
    def _validate_request(self, request: InbetweeniesRequest) -> None:
        """Validate sync request"""
        if request.protocol_version != "inbetweenies-v1":
            raise ValueError(f"Unsupported protocol version: {request.protocol_version}")
        
        if len(request.changes) > 1000:
            raise ValueError(f"Too many changes: {len(request.changes)} (max 1000)")
    
    async def _apply_changes(
        self,
        changes: List[EntityChange]
    ) -> List[ConflictInfo]:
        """Apply changes from client"""
        conflicts = []
        
        for change in changes:
            try:
                conflict = await self._apply_single_change(change)
                if conflict:
                    conflicts.append(conflict)
            except Exception as e:
                logger.error(f"Error applying change {change.entity_id}: {e}")
                # Continue with other changes
        
        return conflicts
    
    async def _apply_single_change(
        self,
        change: EntityChange
    ) -> Optional[ConflictInfo]:
        """Apply a single change"""
        # Fetch current entity
        current_entity = await self.repository.fetch_by_id(change.entity_id)
        
        # Check for conflicts
        if current_entity:
            conflict = self.conflict_resolver.detect_conflict(current_entity, change)
            if conflict:
                return conflict
        
        # Apply change based on type
        if change.change_type == ChangeType.CREATE:
            if current_entity:
                # Entity already exists - conflict
                return ConflictInfo(
                    entity_id=change.entity_id,
                    conflict_type=ConflictType.VERSION_MISMATCH,
                    local_version="",
                    server_version=current_entity.version
                )
            
            # Create new entity
            entity = BaseEntity(
                id=change.entity_id,
                version=change.entity_version,
                entity_type=change.entity_type,
                parent_versions=change.parent_versions,
                content=change.content or {},
                user_id=change.user_id,
                source_type="sync",
                created_at=change.timestamp,
                last_modified=change.timestamp
            )
            await self.repository.save(entity)
            
        elif change.change_type == ChangeType.UPDATE:
            if not current_entity:
                # Entity doesn't exist - create it
                entity = BaseEntity(
                    id=change.entity_id,
                    version=change.entity_version,
                    entity_type=change.entity_type,
                    parent_versions=change.parent_versions,
                    content=change.content or {},
                    user_id=change.user_id,
                    source_type="sync",
                    created_at=change.timestamp,
                    last_modified=change.timestamp
                )
                await self.repository.save(entity)
            else:
                # Update existing entity
                current_entity.version = change.entity_version
                current_entity.parent_versions = change.parent_versions
                current_entity.content = change.content or current_entity.content
                current_entity.last_modified = change.timestamp
                await self.repository.save(current_entity)
        
        elif change.change_type == ChangeType.DELETE:
            if current_entity:
                await self.repository.soft_delete(
                    change.entity_id,
                    change.entity_version
                )
        
        # Clear cache
        await self.cache.delete_entity(change.entity_id)
        
        return None
    
    async def _get_changes_for_client(
        self,
        user_id: str,
        client_clock: Dict[str, str],
        device_id: str
    ) -> List[EntityChange]:
        """Get changes that client doesn't have"""
        # Get last sync time for this device
        last_sync = await self._get_last_sync_time(user_id, device_id)
        
        # Fetch modified entities
        entities = await self.repository.fetch_modified_since(
            last_sync or datetime.min,
            user_id
        )
        
        # Filter out changes client already has
        changes = []
        client_vc = VectorClock.from_dict(client_clock)
        
        for entity in entities:
            # Check if client has this version
            entity_device, entity_seq = self._parse_entity_version(entity.version)
            client_version = client_clock.get(entity_device, "")
            
            if not client_version or self._is_newer_version(entity.version, client_version):
                changes.append(EntityChange(
                    change_type=ChangeType.UPDATE,
                    entity_id=entity.id,
                    entity_version=entity.version,
                    entity_type=entity.entity_type.value,
                    parent_versions=entity.parent_versions,
                    content=entity.content,
                    timestamp=entity.last_modified,
                    device_id=entity_device,
                    user_id=entity.user_id
                ))
        
        return changes
    
    async def _save_vector_clock(
        self,
        user_id: str,
        device_id: str,
        clock: Dict[str, str]
    ) -> None:
        """Save vector clock state"""
        for node_id, version in clock.items():
            await self.cache.set_vector_clock(user_id, node_id, version)
    
    async def _get_last_sync_time(
        self,
        user_id: str,
        device_id: str
    ) -> Optional[datetime]:
        """Get last sync time for device"""
        # TODO: Implement last sync tracking
        return None
    
    def _parse_entity_version(self, version: str) -> tuple[str, int]:
        """Parse entity version to get device and sequence"""
        parts = version.split("-")
        if len(parts) >= 3:
            device_id = parts[-2]
            sequence = int(parts[-1]) if parts[-1].isdigit() else 0
            return device_id, sequence
        return "unknown", 0
    
    def _is_newer_version(self, v1: str, v2: str) -> bool:
        """Check if v1 is newer than v2"""
        # Simple comparison - can be enhanced
        return v1 > v2
```

## Step 5: API Layer

### 5.1 FastAPI Application

```python
# funkygibbon/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from .routes import entities, sync, mcp, health
from ..storage.config import settings
from ..storage.postgresql.database import Database
from ..storage.redis_cache.connection import RedisConnection

logger = logging.getLogger(__name__)

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting FunkyGibbon API")
    
    # Initialize database
    await Database.create_pool(settings.postgres_url)
    
    # Initialize Redis
    await RedisConnection.create_pool(settings.redis_url)
    
    yield
    
    # Shutdown
    logger.info("Shutting down FunkyGibbon API")
    await Database.close_pool()
    await RedisConnection.close_pool()

# Create FastAPI app
app = FastAPI(
    title="FunkyGibbon API",
    description="Smart Home Knowledge Graph Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(entities.router, prefix="/api/entities", tags=["entities"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])

# Root endpoint
@app.get("/")
async def root():
    return {
        "service": "FunkyGibbon",
        "version": "1.0.0",
        "status": "operational"
    }
```

### 5.2 Entity Routes

```python
# funkygibbon/api/routes/entities.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime

from ...core.entities import BaseEntity, HomeEntity, RoomEntity, DeviceEntity
from ...core.models import EntityType
from ..dependencies import get_db_session, get_redis_cache, get_current_user
from ...storage.postgresql.repository import EntityRepository

router = APIRouter()

@router.post("/", response_model=BaseEntity)
async def create_entity(
    entity: BaseEntity,
    db_session=Depends(get_db_session),
    cache=Depends(get_redis_cache),
    current_user=Depends(get_current_user)
):
    """Create a new entity"""
    # Set user ID from authenticated user
    entity.user_id = current_user.id
    
    # Save to database
    repository = EntityRepository(db_session)
    saved_entity = await repository.save(entity)
    
    # Cache entity
    await cache.set_entity(saved_entity.id, saved_entity.dict())
    
    return saved_entity

@router.get("/{entity_id}", response_model=BaseEntity)
async def get_entity(
    entity_id: str,
    db_session=Depends(get_db_session),
    cache=Depends(get_redis_cache),
    current_user=Depends(get_current_user)
):
    """Get entity by ID"""
    # Check cache first
    cached_data = await cache.get_entity(entity_id)
    if cached_data:
        return BaseEntity(**cached_data)
    
    # Fetch from database
    repository = EntityRepository(db_session)
    entity = await repository.fetch_by_id(entity_id)
    
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Verify user owns entity
    if entity.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Cache for next time
    await cache.set_entity(entity.id, entity.dict())
    
    return entity

@router.get("/", response_model=List[BaseEntity])
async def list_entities(
    entity_type: Optional[EntityType] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db_session=Depends(get_db_session),
    current_user=Depends(get_current_user)
):
    """List entities with optional filtering"""
    repository = EntityRepository(db_session)
    
    if entity_type:
        entities = await repository.fetch_all_by_type(
            entity_type,
            current_user.id,
            limit,
            offset
        )
    else:
        # Fetch all types
        entities = []
        for et in EntityType:
            type_entities = await repository.fetch_all_by_type(
                et,
                current_user.id,
                limit,
                offset
            )
            entities.extend(type_entities)
    
    return entities

@router.put("/{entity_id}", response_model=BaseEntity)
async def update_entity(
    entity_id: str,
    entity: BaseEntity,
    db_session=Depends(get_db_session),
    cache=Depends(get_redis_cache),
    current_user=Depends(get_current_user)
):
    """Update an entity"""
    repository = EntityRepository(db_session)
    
    # Fetch existing entity
    existing = await repository.fetch_by_id(entity_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Verify ownership
    if existing.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update entity
    entity.id = entity_id
    entity.user_id = current_user.id
    entity.parent_versions = [existing.version]
    entity.version = BaseEntity.generate_version("api", 0)
    entity.last_modified = datetime.utcnow()
    
    updated = await repository.save(entity)
    
    # Invalidate cache
    await cache.delete_entity(entity_id)
    
    return updated

@router.delete("/{entity_id}")
async def delete_entity(
    entity_id: str,
    db_session=Depends(get_db_session),
    cache=Depends(get_redis_cache),
    current_user=Depends(get_current_user)
):
    """Delete an entity (soft delete)"""
    repository = EntityRepository(db_session)
    
    # Fetch entity
    entity = await repository.fetch_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Verify ownership
    if entity.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Soft delete
    success = await repository.soft_delete(entity_id, entity.version)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete entity")
    
    # Remove from cache
    await cache.delete_entity(entity_id)
    
    return {"status": "deleted", "entity_id": entity_id}
```

### 5.3 Sync Routes

```python
# funkygibbon/api/routes/sync.py
from fastapi import APIRouter, Depends, HTTPException
import logging

from ...inbetweenies.messages import InbetweeniesRequest, InbetweeniesResponse
from ...inbetweenies.sync_service import SyncService
from ..dependencies import get_db_session, get_redis_cache, verify_device_auth

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=InbetweeniesResponse)
async def sync_data(
    request: InbetweeniesRequest,
    db_session=Depends(get_db_session),
    cache=Depends(get_redis_cache),
    device_auth=Depends(verify_device_auth)
):
    """Handle Inbetweenies sync request"""
    # Verify device authentication
    if request.device_id != device_auth.device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")
    
    if request.user_id != device_auth.user_id:
        raise HTTPException(status_code=403, detail="User ID mismatch")
    
    # Process sync
    sync_service = SyncService(db_session, cache)
    
    try:
        response = await sync_service.handle_sync(request)
        return response
    except ValueError as e:
        logger.error(f"Sync validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail="Sync failed")
```

### 5.4 MCP Routes

```python
# funkygibbon/api/routes/mcp.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import logging

from ...mcp.server import MCPServer
from ..dependencies import get_db_session, get_redis_cache, get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/execute")
async def execute_mcp_tool(
    tool_name: str,
    parameters: Dict[str, Any],
    db_session=Depends(get_db_session),
    cache=Depends(get_redis_cache),
    current_user=Depends(get_current_user)
):
    """Execute MCP tool"""
    mcp_server = MCPServer(db_session, cache)
    
    try:
        result = await mcp_server.execute_tool(
            tool_name,
            parameters,
            user_id=current_user.id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"MCP execution error: {e}")
        raise HTTPException(status_code=500, detail="Tool execution failed")

@router.get("/tools")
async def list_mcp_tools():
    """List available MCP tools"""
    return {
        "tools": [
            {
                "name": "create_entity",
                "description": "Create a new home graph entity",
                "parameters": {
                    "type": "Entity type (home, room, device, etc.)",
                    "content": "Entity content as JSON object"
                }
            },
            {
                "name": "query_graph",
                "description": "Query the home graph",
                "parameters": {
                    "query_type": "Type of query (find_rooms, find_devices, etc.)",
                    "parameters": "Query parameters"
                }
            },
            {
                "name": "update_entity",
                "description": "Update an existing entity",
                "parameters": {
                    "entity_id": "Entity ID to update",
                    "content": "Updated content"
                }
            },
            {
                "name": "sync_now",
                "description": "Trigger immediate sync",
                "parameters": {
                    "device_id": "Device ID requesting sync"
                }
            }
        ]
    }
```

## Step 6: MCP Server Implementation

### 6.1 MCP Server

```python
# funkygibbon/mcp/server.py
from typing import Dict, Any, Optional
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.entities import create_entity
from ..core.models import EntityType
from ..storage.postgresql.repository import EntityRepository
from ..storage.redis_cache.cache import RedisCache

logger = logging.getLogger(__name__)

class MCPServer:
    """MCP server implementation for FunkyGibbon"""
    
    def __init__(self, db_session: AsyncSession, cache: RedisCache):
        self.repository = EntityRepository(db_session)
        self.cache = cache
        self.tools = self._register_tools()
    
    def _register_tools(self) -> Dict[str, callable]:
        """Register available MCP tools"""
        return {
            "create_entity": self.create_entity,
            "query_graph": self.query_graph,
            "update_entity": self.update_entity,
            "delete_entity": self.delete_entity,
            "sync_now": self.sync_now,
        }
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Execute MCP tool"""
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        tool_func = self.tools[tool_name]
        return await tool_func(parameters, user_id)
    
    async def create_entity(
        self,
        parameters: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Create a new entity"""
        entity_type = EntityType(parameters["type"])
        content = parameters.get("content", {})
        
        entity = create_entity(
            entity_type=entity_type,
            content=content,
            user_id=user_id,
            source_type="mcp"
        )
        
        saved = await self.repository.save(entity)
        
        return {
            "id": saved.id,
            "version": saved.version,
            "type": saved.entity_type.value,
            "created": saved.created_at.isoformat()
        }
    
    async def query_graph(
        self,
        parameters: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Query the home graph"""
        query_type = parameters["query_type"]
        query_params = parameters.get("parameters", {})
        
        if query_type == "find_rooms":
            home_id = query_params.get("home_id")
            rooms = await self.repository.fetch_all_by_type(
                EntityType.ROOM,
                user_id
            )
            
            if home_id:
                rooms = [r for r in rooms if r.home_id == home_id]
            
            return {
                "rooms": [r.dict() for r in rooms],
                "count": len(rooms)
            }
        
        elif query_type == "find_devices":
            room_id = query_params.get("room_id")
            devices = await self.repository.fetch_all_by_type(
                EntityType.DEVICE,
                user_id
            )
            
            if room_id:
                devices = [d for d in devices if d.room_id == room_id]
            
            return {
                "devices": [d.dict() for d in devices],
                "count": len(devices)
            }
        
        else:
            raise ValueError(f"Unknown query type: {query_type}")
    
    async def update_entity(
        self,
        parameters: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Update an existing entity"""
        entity_id = parameters["entity_id"]
        content = parameters["content"]
        
        # Fetch existing entity
        entity = await self.repository.fetch_by_id(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        if entity.user_id != user_id:
            raise ValueError("Access denied")
        
        # Update content
        entity.content.update(content)
        entity.parent_versions = [entity.version]
        entity.version = BaseEntity.generate_version("mcp", 0)
        entity.last_modified = datetime.utcnow()
        
        saved = await self.repository.save(entity)
        
        # Clear cache
        await self.cache.delete_entity(entity_id)
        
        return {
            "id": saved.id,
            "version": saved.version,
            "updated": saved.last_modified.isoformat()
        }
    
    async def delete_entity(
        self,
        parameters: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Delete an entity"""
        entity_id = parameters["entity_id"]
        
        # Fetch entity
        entity = await self.repository.fetch_by_id(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        
        if entity.user_id != user_id:
            raise ValueError("Access denied")
        
        # Soft delete
        success = await self.repository.soft_delete(entity_id, entity.version)
        
        if not success:
            raise ValueError("Failed to delete entity")
        
        # Clear cache
        await self.cache.delete_entity(entity_id)
        
        return {
            "status": "deleted",
            "entity_id": entity_id
        }
    
    async def sync_now(
        self,
        parameters: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Trigger immediate sync"""
        device_id = parameters["device_id"]
        
        # This would typically trigger a push notification or WebSocket message
        # to the device to start syncing
        logger.info(f"Sync requested for device {device_id}")
        
        return {
            "status": "sync_triggered",
            "device_id": device_id,
            "user_id": user_id
        }
```

## Step 7: Testing

### 7.1 Unit Tests

```python
# funkygibbon/tests/unit/test_models.py
import pytest
from datetime import datetime

from funkygibbon.core.models import EntityType, SourceType
from funkygibbon.core.entities import HomeEntity, RoomEntity, DeviceEntity

class TestEntities:
    def test_home_entity_creation(self):
        home = HomeEntity(
            version="v1",
            content={"name": "My Home", "address": "123 Main St"},
            user_id="user-123",
            source_type=SourceType.MANUAL
        )
        
        assert home.id is not None
        assert home.entity_type == EntityType.HOME
        assert home.name == "My Home"
        assert home.address == "123 Main St"
    
    def test_room_entity_properties(self):
        room = RoomEntity(
            version="v1",
            content={
                "name": "Living Room",
                "home_id": "home-123",
                "floor": 1
            },
            user_id="user-123",
            source_type=SourceType.HOMEKIT
        )
        
        assert room.entity_type == EntityType.ROOM
        assert room.home_id == "home-123"
        assert room.floor == 1
    
    def test_device_entity_capabilities(self):
        device = DeviceEntity(
            version="v1",
            content={
                "name": "Smart Light",
                "capabilities": ["on_off", "dimming", "color"]
            },
            user_id="user-123",
            source_type=SourceType.MATTER
        )
        
        assert device.entity_type == EntityType.DEVICE
        assert len(device.capabilities) == 3
        assert "dimming" in device.capabilities
    
    def test_version_generation(self):
        version = HomeEntity.generate_version("test-device", 42)
        assert "test-device" in version
        assert "-042" in version
```

### 7.2 Integration Tests

```python
# funkygibbon/tests/integration/test_sync.py
import pytest
from datetime import datetime

from funkygibbon.inbetweenies.messages import (
    InbetweeniesRequest, EntityChange, ChangeType,
    RequestMetadata, CompressionType
)
from funkygibbon.inbetweenies.sync_service import SyncService

@pytest.mark.asyncio
class TestSyncService:
    async def test_sync_new_entity(self, db_session, redis_cache):
        sync_service = SyncService(db_session, redis_cache)
        
        # Create sync request with new entity
        change = EntityChange(
            change_type=ChangeType.CREATE,
            entity_id="entity-123",
            entity_version="2024-01-01T00:00:00-device1-001",
            entity_type="home",
            parent_versions=[],
            content={"name": "Test Home"},
            timestamp=datetime.utcnow(),
            device_id="device1",
            user_id="user-123"
        )
        
        request = InbetweeniesRequest(
            device_id="device1",
            user_id="user-123",
            session_id="session-123",
            vector_clock={"device1": "2024-01-01T00:00:00-device1-001"},
            changes=[change],
            compression=CompressionType.NONE,
            capabilities=["batch_1000"],
            metadata=RequestMetadata(
                client_version="1.0.0",
                platform="iOS",
                sync_reason="manual"
            )
        )
        
        # Process sync
        response = await sync_service.handle_sync(request)
        
        assert response.sync_status == SyncStatus.SUCCESS
        assert len(response.conflicts) == 0
        assert "server" in response.vector_clock
    
    async def test_sync_conflict_detection(self, db_session, redis_cache):
        sync_service = SyncService(db_session, redis_cache)
        
        # Create entity in database first
        existing = HomeEntity(
            id="entity-123",
            version="2024-01-01T00:00:00-server-001",
            content={"name": "Server Home"},
            user_id="user-123",
            source_type=SourceType.MANUAL
        )
        
        repository = EntityRepository(db_session)
        await repository.save(existing)
        
        # Create conflicting change
        change = EntityChange(
            change_type=ChangeType.UPDATE,
            entity_id="entity-123",
            entity_version="2024-01-01T00:00:00-device1-001",
            parent_versions=[],  # Missing server version
            content={"name": "Device Home"},
            timestamp=datetime.utcnow(),
            device_id="device1",
            user_id="user-123"
        )
        
        request = InbetweeniesRequest(
            device_id="device1",
            user_id="user-123",
            session_id="session-123",
            vector_clock={"device1": "2024-01-01T00:00:00-device1-001"},
            changes=[change],
            compression=CompressionType.NONE,
            capabilities=["batch_1000"],
            metadata=RequestMetadata(
                client_version="1.0.0",
                platform="iOS",
                sync_reason="manual"
            )
        )
        
        # Process sync
        response = await sync_service.handle_sync(request)
        
        assert response.sync_status == SyncStatus.PARTIAL
        assert len(response.conflicts) == 1
        assert response.conflicts[0].conflict_type == ConflictType.VERSION_MISMATCH
```

### 7.3 End-to-End Tests

```python
# funkygibbon/tests/e2e/test_sync_flow.py
import pytest
import httpx
from datetime import datetime

@pytest.mark.asyncio
class TestE2ESyncFlow:
    async def test_full_sync_flow(self, test_client):
        # 1. Create entity via API
        create_response = await test_client.post(
            "/api/entities/",
            json={
                "entity_type": "home",
                "content": {"name": "Test Home"},
                "version": "v1",
                "user_id": "test-user",
                "source_type": "manual"
            }
        )
        assert create_response.status_code == 200
        entity = create_response.json()
        
        # 2. Prepare sync request
        sync_request = {
            "protocol_version": "inbetweenies-v1",
            "device_id": "test-device",
            "user_id": "test-user",
            "session_id": "test-session",
            "vector_clock": {},
            "changes": [],
            "compression": "none",
            "capabilities": ["batch_1000"],
            "metadata": {
                "client_version": "1.0.0",
                "platform": "test",
                "sync_reason": "manual"
            }
        }
        
        # 3. Perform sync
        sync_response = await test_client.post(
            "/api/sync/",
            json=sync_request
        )
        assert sync_response.status_code == 200
        sync_data = sync_response.json()
        
        # 4. Verify sync response
        assert sync_data["sync_status"] == "success"
        assert len(sync_data["changes"]) >= 1
        
        # Find our created entity in changes
        entity_change = next(
            (c for c in sync_data["changes"] if c["entity_id"] == entity["id"]),
            None
        )
        assert entity_change is not None
        assert entity_change["content"]["name"] == "Test Home"
```

## Step 8: Deployment

### 8.1 Docker Configuration

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Copy application code
COPY funkygibbon/ ./funkygibbon/
COPY alembic.ini ./

# Create non-root user
RUN useradd -m -u 1000 funkygibbon \
    && chown -R funkygibbon:funkygibbon /app

USER funkygibbon

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "funkygibbon.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 8.2 Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:14-alpine
    environment:
      POSTGRES_DB: funkygibbon
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  funkygibbon:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_DB: funkygibbon
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      REDIS_HOST: redis
      REDIS_PORT: 6379
    ports:
      - "8000:8000"
    volumes:
      - ./funkygibbon:/app/funkygibbon
    command: >
      sh -c "
        alembic upgrade head &&
        uvicorn funkygibbon.api.main:app --host 0.0.0.0 --port 8000 --reload
      "

volumes:
  postgres_data:
  redis_data:
```

### 8.3 Production Configuration

```python
# funkygibbon/config/production.py
import os
from pydantic_settings import BaseSettings

class ProductionSettings(BaseSettings):
    # Database
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "funkygibbon")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD")
    
    # Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str = os.getenv("REDIS_PASSWORD")
    
    # Security
    secret_key: str = os.getenv("SECRET_KEY")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # API
    api_v1_prefix: str = "/api/v1"
    allowed_hosts: list = ["*"]
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    class Config:
        env_file = ".env.production"
```

## Step 9: Monitoring and Logging

### 9.1 Logging Configuration

```python
# funkygibbon/utils/logging.py
import logging
import sys
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if hasattr(record, "user_id"):
            log_obj["user_id"] = record.user_id
        
        if hasattr(record, "device_id"):
            log_obj["device_id"] = record.device_id
        
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_obj)

def setup_logging(log_level="INFO", log_file=None):
    """Setup application logging"""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)
```

### 9.2 Health Checks

```python
# funkygibbon/api/routes/health.py
from fastapi import APIRouter, Depends
from datetime import datetime
import psutil
import os

from ..dependencies import get_db_session, get_redis_cache

router = APIRouter()

@router.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@router.get("/health/detailed")
async def detailed_health(
    db_session=Depends(get_db_session),
    cache=Depends(get_redis_cache)
):
    """Detailed health check"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "checks": {}
    }
    
    # Database check
    try:
        await db_session.execute("SELECT 1")
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Redis check
    try:
        await cache.redis.ping()
        health_status["checks"]["redis"] = "healthy"
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # System resources
    health_status["system"] = {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent
    }
    
    return health_status
```

## Step 10: Performance Optimization

### 10.1 Database Optimization

```sql
-- migrations/optimize_indexes.sql

-- Composite indexes for common queries
CREATE INDEX idx_entities_user_type_modified 
ON entities(user_id, entity_type, last_modified DESC);

CREATE INDEX idx_entities_user_modified 
ON entities(user_id, last_modified DESC) 
WHERE deleted_at IS NULL;

-- Partial index for active entities
CREATE INDEX idx_entities_active 
ON entities(id, version) 
WHERE deleted_at IS NULL;

-- JSONB indexes for content queries
CREATE INDEX idx_entities_content_name 
ON entities((content->>'name')) 
WHERE entity_type IN ('home', 'room', 'device');

-- Optimize vector clock queries
CREATE INDEX idx_vector_clocks_user_device 
ON vector_clocks(user_id, device_id, updated_at DESC);

-- Analyze tables for query planner
ANALYZE entities;
ANALYZE relationships;
ANALYZE vector_clocks;
```

### 10.2 Caching Strategy

```python
# funkygibbon/utils/caching.py
from functools import wraps
from typing import Optional, Callable
import hashlib
import json

def cache_result(
    ttl: int = 3600,
    key_prefix: str = "cache",
    include_user: bool = True
):
    """Decorator for caching function results"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key_parts = [key_prefix, func.__name__]
            
            if include_user and "user_id" in kwargs:
                cache_key_parts.append(kwargs["user_id"])
            
            # Hash arguments for cache key
            arg_hash = hashlib.md5(
                json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True).encode()
            ).hexdigest()
            cache_key_parts.append(arg_hash)
            
            cache_key = ":".join(cache_key_parts)
            
            # Check cache
            cache = kwargs.get("cache")
            if cache:
                cached = await cache.redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            if cache and result is not None:
                await cache.redis.setex(
                    cache_key,
                    ttl,
                    json.dumps(result, default=str)
                )
            
            return result
        
        return wrapper
    return decorator
```

## Troubleshooting Guide

### Common Issues

1. **Connection Pool Exhaustion**
   ```python
   # Increase pool size in settings
   db_pool_size = 50
   db_max_overflow = 100
   ```

2. **Sync Timeouts**
   ```python
   # Implement streaming for large syncs
   # Add batch processing
   # Increase timeout values
   ```

3. **Memory Leaks**
   ```python
   # Use weak references
   # Implement proper cleanup
   # Monitor with memory profiler
   ```

4. **Redis Connection Issues**
   ```python
   # Implement retry logic
   # Use connection pooling
   # Add circuit breaker pattern
   ```

## Next Steps

1. **Implement remaining entity types**
2. **Add WebSocket support for real-time sync**
3. **Implement end-to-end encryption**
4. **Add GraphQL API option**
5. **Create admin dashboard**
6. **Add analytics and metrics**
7. **Implement rate limiting**
8. **Add multi-tenancy support**

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/)
- [Redis Python Client](https://redis-py.readthedocs.io/)
- [Alembic Migration Guide](https://alembic.sqlalchemy.org/)
- [Pydantic V2 Documentation](https://docs.pydantic.dev/)