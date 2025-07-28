# FunkyGibbon Python Implementation Plan

## Overview

FunkyGibbon is the Python backend service for The Goodies smart home knowledge graph system. It provides centralized synchronization, conflict resolution, and cloud-based features for the WildThing ecosystem.

## Technology Stack

- **Python 3.11+** with type hints throughout
- **SQLAlchemy 2.0** for database ORM (async)
- **FastAPI** for REST API with async support
- **Click** for CLI interface
- **pytest** for testing framework
- **SQLite** as primary database (with optional PostgreSQL for production)
- **Redis** for caching (optional)
- **Pydantic 2.x** for data validation
- **httpx** for async HTTP client
- **asyncio** for async/await patterns

## Project Structure

```
FunkyGibbon/
├── pyproject.toml              # Modern Python packaging
├── README.md                   # Project documentation
├── requirements/
│   ├── base.txt               # Core dependencies
│   ├── dev.txt               # Development dependencies
│   └── test.txt              # Testing dependencies
├── funkygibbon/
│   ├── __init__.py
│   ├── __main__.py           # Entry point for python -m funkygibbon
│   ├── config.py             # Configuration management
│   ├── models/               # SQLAlchemy models & Pydantic schemas
│   │   ├── __init__.py
│   │   ├── entity.py         # HomeEntity model
│   │   ├── relationship.py   # EntityRelationship model
│   │   ├── sync.py          # Sync-related models
│   │   └── schemas.py       # Pydantic schemas
│   ├── repositories/         # Data access layer
│   │   ├── __init__.py
│   │   ├── base.py          # Base repository pattern
│   │   ├── entity.py        # Entity repository
│   │   ├── relationship.py  # Relationship repository
│   │   └── sync.py          # Sync repository
│   ├── services/            # Business logic layer
│   │   ├── __init__.py
│   │   ├── entity.py        # Entity management
│   │   ├── sync.py          # Inbetweenies sync service
│   │   ├── conflict.py      # Conflict resolution
│   │   └── vector_clock.py  # Vector clock implementation
│   ├── api/                 # FastAPI application
│   │   ├── __init__.py
│   │   ├── app.py           # FastAPI app setup
│   │   ├── deps.py          # Dependency injection
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── entities.py  # Entity endpoints
│   │   │   ├── sync.py      # Sync endpoints
│   │   │   └── health.py    # Health check
│   │   └── middleware.py    # Custom middleware
│   ├── cli/                 # Click CLI
│   │   ├── __init__.py
│   │   ├── main.py          # CLI entry point
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   ├── serve.py     # Server commands
│   │   │   ├── db.py        # Database commands
│   │   │   └── sync.py      # Sync commands
│   │   └── utils.py         # CLI utilities
│   └── utils/               # Shared utilities
│       ├── __init__.py
│       ├── logging.py       # Logging setup
│       ├── db.py           # Database utilities
│       └── time.py         # Time utilities
├── tests/                   # Test suite
│   ├── __init__.py
│   ├── conftest.py         # pytest fixtures
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── e2e/               # End-to-end tests
├── scripts/                # Utility scripts
│   ├── setup_db.py        # Database setup
│   └── seed_data.py       # Seed test data
└── docker/                 # Docker configuration
    ├── Dockerfile
    └── docker-compose.yml
```

## Core Components

### 1. Models Layer (SQLAlchemy + Pydantic)

```python
# models/entity.py
from sqlalchemy import Column, String, JSON, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum as PyEnum

Base = declarative_base()

class EntityType(str, PyEnum):
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

class HomeEntity(Base):
    __tablename__ = "entities"
    
    id = Column(String, primary_key=True)
    version = Column(String, primary_key=True)
    entity_type = Column(Enum(EntityType), nullable=False)
    parent_versions = Column(JSON, default=list)
    content = Column(JSON, nullable=False)
    user_id = Column(String, nullable=False)
    source_type = Column(String, default="manual")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

# Pydantic schema
class HomeEntitySchema(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = Field(default_factory=generate_version)
    entity_type: EntityType
    parent_versions: List[str] = Field(default_factory=list)
    content: Dict[str, Any]
    user_id: str
    source_type: str = "manual"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
```

### 2. Repository Layer (Data Access)

```python
# repositories/base.py
from typing import Generic, TypeVar, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

T = TypeVar("T")

class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model
    
    async def get(self, **kwargs) -> Optional[T]:
        stmt = select(self.model).filter_by(**kwargs)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_all(self, **kwargs) -> List[T]:
        stmt = select(self.model).filter_by(**kwargs)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def create(self, **kwargs) -> T:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance
    
    async def update(self, instance: T, **kwargs) -> T:
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance
    
    async def delete(self, instance: T) -> None:
        await self.session.delete(instance)
        await self.session.commit()
```

### 3. Service Layer (Business Logic)

```python
# services/sync.py
from typing import List, Dict, Any, Optional
from datetime import datetime
from ..models.sync import InbetweeniesRequest, InbetweeniesResponse
from ..repositories.entity import EntityRepository
from ..repositories.sync import SyncRepository
from .vector_clock import VectorClock
from .conflict import ConflictResolver

class SyncService:
    def __init__(
        self,
        entity_repo: EntityRepository,
        sync_repo: SyncRepository,
        conflict_resolver: ConflictResolver
    ):
        self.entity_repo = entity_repo
        self.sync_repo = sync_repo
        self.conflict_resolver = conflict_resolver
    
    async def handle_sync_request(
        self,
        request: InbetweeniesRequest
    ) -> InbetweeniesResponse:
        """Process Inbetweenies sync request"""
        # Apply incoming changes
        conflicts = await self._apply_changes(request.changes, request.user_id)
        
        # Get changes for client
        client_changes = await self._get_changes_for_client(
            request.user_id,
            request.device_id,
            request.vector_clock
        )
        
        # Update vector clock
        updated_clock = await self._update_vector_clock(
            request.user_id,
            request.device_id,
            request.vector_clock
        )
        
        return InbetweeniesResponse(
            changes=client_changes,
            vector_clock=updated_clock,
            conflicts=[c.entity_id for c in conflicts]
        )
```

### 4. API Layer (FastAPI)

```python
# api/app.py
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from ..config import settings
from .routes import entities, sync, health
from ..utils.db import init_db, get_session

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown

app = FastAPI(
    title="FunkyGibbon API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router, tags=["health"])
app.include_router(entities.router, prefix="/api/entities", tags=["entities"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
```

### 5. CLI Layer (Click)

```python
# cli/main.py
import click
import asyncio
from .commands import serve, db, sync

@click.group()
@click.version_option()
def cli():
    """FunkyGibbon - Smart home knowledge graph sync service"""
    pass

cli.add_command(serve.serve)
cli.add_command(db.db)
cli.add_command(sync.sync)

if __name__ == "__main__":
    cli()
```

## Implementation Steps

### Phase 1: Core Foundation (Week 1)
1. Set up project structure and dependencies
2. Implement SQLAlchemy models for entities and relationships
3. Create Pydantic schemas for API validation
4. Set up database connection and migrations
5. Implement base repository pattern

### Phase 2: Data Layer (Week 1-2)
1. Implement entity repository with CRUD operations
2. Implement relationship repository
3. Add sync metadata tables and repositories
4. Create database initialization scripts
5. Add unit tests for repositories

### Phase 3: Business Logic (Week 2)
1. Implement vector clock algorithm
2. Create conflict detection and resolution logic
3. Build Inbetweenies sync service
4. Add change tracking and versioning
5. Implement entity search and filtering

### Phase 4: API Layer (Week 3)
1. Set up FastAPI application structure
2. Implement entity CRUD endpoints
3. Create Inbetweenies sync endpoint
4. Add authentication middleware
5. Implement health and metrics endpoints

### Phase 5: CLI and Tools (Week 3-4)
1. Create Click CLI structure
2. Implement server start/stop commands
3. Add database management commands
4. Create sync testing commands
5. Add configuration management

### Phase 6: Testing & Polish (Week 4)
1. Write comprehensive unit tests
2. Add integration tests for sync flow
3. Create end-to-end test scenarios
4. Add performance benchmarks
5. Write documentation

## Key Design Decisions

### 1. Simple Architecture
- Repository pattern for clean separation
- Service layer for business logic
- Minimal external dependencies
- SQLite as default (PostgreSQL optional)

### 2. Async Throughout
- Use async/await for all I/O operations
- AsyncSession for database access
- httpx for async HTTP client
- asyncio for coordination

### 3. Type Safety
- Type hints on all functions
- Pydantic for runtime validation
- mypy for static type checking
- Strict validation at boundaries

### 4. Testing First
- pytest with async support
- Fixtures for database setup
- Mock external dependencies
- Property-based testing for sync

### 5. Configuration
- Environment variables for config
- Pydantic settings validation
- Separate configs for dev/test/prod
- No hardcoded values

## Dependencies

### Core Dependencies (requirements/base.txt)
```
fastapi>=0.104.0
sqlalchemy>=2.0.0
pydantic>=2.0.0
click>=8.1.0
httpx>=0.25.0
python-dotenv>=1.0.0
alembic>=1.12.0
asyncpg>=0.29.0  # For PostgreSQL
aiosqlite>=0.19.0  # For SQLite
```

### Development Dependencies (requirements/dev.txt)
```
-r base.txt
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
mypy>=1.5.0
black>=23.0.0
ruff>=0.1.0
```

## Testing Strategy

### Unit Tests
- Test models and schemas
- Test repositories with mocked database
- Test services with mocked dependencies
- Test utilities and helpers

### Integration Tests
- Test API endpoints with test database
- Test sync flow end-to-end
- Test conflict resolution scenarios
- Test vector clock synchronization

### Performance Tests
- Benchmark entity operations
- Test sync with large datasets
- Measure API response times
- Profile memory usage

## Security Considerations

1. **Input Validation**: Pydantic models for all inputs
2. **SQL Injection**: Use SQLAlchemy ORM, no raw SQL
3. **Authentication**: JWT tokens for API access
4. **Rate Limiting**: Built into FastAPI middleware
5. **Secrets**: Environment variables, never committed

## Monitoring & Observability

1. **Structured Logging**: JSON logs with context
2. **Metrics**: Prometheus-compatible metrics
3. **Health Checks**: Dedicated health endpoints
4. **Error Tracking**: Proper exception handling
5. **Performance**: Request timing middleware

## Deployment

### Development
```bash
# Install dependencies
pip install -r requirements/dev.txt

# Run migrations
python -m funkygibbon db upgrade

# Start server
python -m funkygibbon serve --debug
```

### Production
```bash
# Using Docker
docker build -t funkygibbon .
docker run -p 8000:8000 funkygibbon

# Using systemd
sudo systemctl start funkygibbon
```

## Next Steps

1. Create initial project structure
2. Set up development environment
3. Implement core models
4. Build repository layer
5. Start with entity CRUD operations