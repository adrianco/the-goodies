"""
FunkyGibbon - Base Repository Pattern with Conflict Resolution

DEVELOPMENT CONTEXT:
Created in July 2025 to implement the repository pattern for data access.
This module is central to our bidirectional sync strategy, implementing
last-write-wins conflict resolution and providing a consistent interface
for all entity operations across the system. Updated in July 2025 to work
with simplified HomeKit-compatible models from the Inbetweenies package.

FUNCTIONALITY:
- Generic repository pattern for all entity types (CRUD operations)
- ConflictResolver implements last-write-wins with sync_id tiebreaker
- Sync operations with automatic conflict detection and resolution
- Change tracking via get_changes_since for incremental sync
- Automatic timestamp management (no version fields)
- Type-safe operations using Python generics
- Works with shared HomeKit models (no soft deletes)

PURPOSE:
Provides a consistent data access layer that handles the complexity of
bidirectional sync and conflict resolution. This ensures all entities
follow the same patterns and sync protocol rules. Now uses simplified
models without soft deletes or version tracking.

KNOWN ISSUES:
- Conflict resolution within 1 second uses sync_id (may not be intuitive)
- No batch operations for performance (single entity at a time)
- Missing database indexes on updated_at for performance
- Greenlet/async issues with some SQLAlchemy operations in sync context

REVISION HISTORY:
- 2025-07-28: Initial repository pattern implementation
- 2025-07-28: Added ConflictResolver with last-write-wins
- 2025-07-28: Added sync_entity method for bidirectional sync
- 2025-07-28: Fixed datetime parsing in sync_entity for ISO format strings
- 2025-07-28: Enhanced ConflictResolver to handle both string and datetime objects
- 2025-07-28: Added timezone normalization for datetime comparisons
- 2025-07-29: Improved ConflictResolver with robust timezone-aware datetime normalization
- 2025-07-29: Fixed sync_entity to check by entity ID first (for conflicts) then sync_id (for normal sync)
- 2025-07-28: Added soft delete support
- 2025-07-28: Added get_changes_since for incremental sync
- 2025-07-28: Fixed timezone handling in conflict resolution
- 2025-07-29: Migrated to shared Inbetweenies models (removed soft deletes and version fields)
- 2025-07-29: Updated all queries to work without is_deleted field

DEPENDENCIES:
- sqlalchemy: Async ORM operations
- typing: Generic type support
- datetime: UTC timestamp handling
- inbetweenies.models: Shared HomeKit-compatible models
- inbetweenies.sync: Conflict resolution logic

USAGE:
# Create a repository for a model:
device_repo = BaseRepository(Device)

# CRUD operations:
device = await device_repo.create(db, name="Light", device_type="light")
device = await device_repo.get_by_id(db, device.id)
device = await device_repo.update(db, device.id, name="Bright Light")
await device_repo.soft_delete(db, device.id)

# Sync with conflict resolution:
entity, updated, conflict = await device_repo.sync_entity(db, remote_data)
if conflict:
    print(f"Conflict resolved: {conflict.reason}")
"""

import json
from datetime import datetime, UTC
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from inbetweenies.models import Base
from inbetweenies.sync import ConflictResolver, ConflictResolution
from inbetweenies.repositories import BaseSyncRepository

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""
    
    def __init__(self, model_class: Type[T]):
        self.model_class = model_class
        self.conflict_resolver = ConflictResolver()
    
    async def create(self, db: AsyncSession, **kwargs) -> T:
        """Create a new entity."""
        import uuid
        
        # Generate ID if not provided
        if 'id' not in kwargs:
            kwargs['id'] = str(uuid.uuid4())
            
        # Set timestamps if not provided
        now = datetime.now(UTC)
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)
        
        # Generate sync_id if not provided
        if 'sync_id' not in kwargs:
            kwargs['sync_id'] = str(uuid.uuid4())
        
        entity = self.model_class(**kwargs)
        db.add(entity)
        await db.commit()
        await db.refresh(entity)
        return entity
    
    async def get_by_id(self, db: AsyncSession, id: str) -> Optional[T]:
        """Get entity by ID."""
        stmt = select(self.model_class).where(
            and_(
                self.model_class.id == id,
                True  # Models don't have is_deleted - include all records
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_sync_id(self, db: AsyncSession, sync_id: str) -> Optional[T]:
        """Get entity by sync ID."""
        stmt = select(self.model_class).where(
            and_(
                self.model_class.sync_id == sync_id,
                True  # Models don't have is_deleted - include all records
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_all(self, db: AsyncSession, limit: int = 1000) -> List[T]:
        """Get all entities (excluding deleted)."""
        stmt = select(self.model_class).where(
            True  # Models don't have is_deleted
        ).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def update(self, db: AsyncSession, id: str, **kwargs) -> Optional[T]:
        """Update an entity by ID."""
        entity = await self.get_by_id(db, id)
        if not entity:
            return None
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        
        # Update timestamp and version
        entity.updated_at = datetime.now(UTC)
        # Models don't have version field
        
        await db.commit()
        await db.refresh(entity)
        return entity
    
    async def soft_delete(self, db: AsyncSession, id: str) -> bool:
        """Soft delete an entity."""
        entity = await self.get_by_id(db, id)
        if not entity:
            return False
        
        # Models don't have is_deleted - actually delete the record
        await db.delete(entity)
        await db.commit()
        return True
    
    async def sync_entity(
        self, 
        db: AsyncSession, 
        remote_data: Dict[str, Any]
    ) -> tuple[T, bool, Optional[ConflictResolution]]:
        """
        Sync a remote entity with local database.
        
        Returns:
            Tuple of (entity, was_updated, conflict_resolution)
        """
        sync_id = remote_data["sync_id"]
        entity_id = remote_data.get("id")
        
        # First try to find by entity ID (for conflict detection)
        local_entity = None
        if entity_id:
            local_entity = await self.get_by_id(db, entity_id)
        
        # If not found by ID, try by sync_id (for normal sync)
        if not local_entity:
            local_entity = await self.get_by_sync_id(db, sync_id)
        
        if not local_entity:
            # Parse datetime strings to datetime objects
            parsed_data = remote_data.copy()
            for key in ["created_at", "updated_at"]:
                if key in parsed_data and isinstance(parsed_data[key], str):
                    parsed_data[key] = datetime.fromisoformat(parsed_data[key].replace("Z", "+00:00"))
            
            # New entity, create it
            entity = await self.create(db, **parsed_data)
            return entity, True, None
        
        # Check for conflicts
        local_data = local_entity.to_dict()
        resolution = self.conflict_resolver.resolve(local_data, remote_data)
        
        if resolution.winner == remote_data:
            # Remote wins, update local
            for key, value in remote_data.items():
                if hasattr(local_entity, key) and key not in ["id", "created_at"]:
                    # Parse datetime strings
                    if key in ["updated_at"] and isinstance(value, str):
                        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    setattr(local_entity, key, value)
            
            await db.commit()
            await db.refresh(local_entity)
            return local_entity, True, resolution
        else:
            # Local wins, no update needed
            return local_entity, False, resolution
    
    async def get_changes_since(
        self, 
        db: AsyncSession, 
        timestamp: datetime,
        limit: int = 100
    ) -> List[T]:
        """Get all entities changed since a timestamp."""
        stmt = select(self.model_class).where(
            self.model_class.updated_at > timestamp
        ).order_by(
            self.model_class.updated_at
        ).limit(limit)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())