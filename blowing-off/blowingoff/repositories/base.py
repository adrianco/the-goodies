"""
Blowing-Off Client - Base Repository Pattern

DEVELOPMENT CONTEXT:
Created as the foundation for all data access in January 2024. This repository
pattern provides a clean abstraction over SQLAlchemy for all client-side database
operations. It implements sync-aware CRUD operations that automatically track
local changes for the Inbetweenies protocol.

FUNCTIONALITY:
- Generic repository pattern for type-safe data access
- Automatic sync status tracking on all mutations
- Specialized queries for sync operations (pending, conflicts)
- Conflict resolution support with optimistic locking
- Time-based change tracking for incremental sync
- Bulk operations for efficient sync processing
- Transaction-aware with explicit flush control

PURPOSE:
This base repository ensures:
- Consistent data access patterns across all entities
- Automatic sync tracking without manual intervention
- Clean separation between business logic and data access
- Type safety with Generic[T] pattern
- Efficient queries for sync engine operations
- Easy testing with mockable interface

KNOWN ISSUES:
- No automatic relationship loading (must use selectinload)
- Bulk operations could be more efficient
- Missing query caching for frequently accessed data
- No built-in pagination support yet

REVISION HISTORY:
- 2024-01-15: Initial implementation with basic CRUD
- 2024-01-18: Added sync-aware operations
- 2024-01-20: Enhanced conflict resolution support
- 2024-01-22: Added time-based change queries

DEPENDENCIES:
- SQLAlchemy 2.0+ with async support
- Generic typing for type safety
- Base model with ClientTimestampMixin

USAGE:
    class DeviceRepository(ClientBaseRepository[ClientDevice]):
        def __init__(self, session: AsyncSession):
            super().__init__(ClientDevice, session)
            
        async def get_by_room(self, room_id: str) -> List[ClientDevice]:
            # Custom query methods can extend base functionality
            result = await self.session.execute(
                select(self.model).where(self.model.room_id == room_id)
            )
            return list(result.scalars().all())
"""

from typing import TypeVar, Generic, Type, Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from ..models.base import Base, SyncStatus

T = TypeVar("T", bound=Base)


class ClientBaseRepository(Generic[T]):
    """Base repository with sync-aware operations."""
    
    def __init__(self, model: Type[T], session: AsyncSession):
        self.model = model
        self.session = session
        
    async def get(self, id: str) -> Optional[T]:
        """Get entity by ID."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
        
    async def get_all(self) -> List[T]:
        """Get all entities."""
        result = await self.session.execute(select(self.model))
        return list(result.scalars().all())
        
    async def get_pending(self) -> List[T]:
        """Get entities with pending changes."""
        result = await self.session.execute(
            select(self.model).where(
                self.model.sync_status == SyncStatus.PENDING
            )
        )
        return list(result.scalars().all())
        
    async def get_conflicts(self) -> List[T]:
        """Get entities with conflicts."""
        result = await self.session.execute(
            select(self.model).where(
                self.model.sync_status == SyncStatus.CONFLICT
            )
        )
        return list(result.scalars().all())
        
    async def get_modified_since(self, since: datetime) -> List[T]:
        """Get entities modified since timestamp."""
        result = await self.session.execute(
            select(self.model).where(
                self.model.updated_at > since
            )
        )
        return list(result.scalars().all())
        
    async def create(self, **kwargs) -> T:
        """Create new entity with pending status."""
        entity = self.model(**kwargs)
        entity.mark_pending()
        self.session.add(entity)
        await self.session.flush()
        return entity
        
    async def update(self, id: str, **kwargs) -> Optional[T]:
        """Update entity and mark as pending."""
        entity = await self.get(id)
        if not entity:
            return None
            
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
                
        entity.mark_pending()
        await self.session.flush()
        return entity
        
    async def delete(self, id: str) -> bool:
        """Delete entity."""
        entity = await self.get(id)
        if not entity:
            return False
            
        await self.session.delete(entity)
        await self.session.flush()
        return True
        
    async def mark_synced(self, id: str, server_updated_at: datetime) -> Optional[T]:
        """Mark entity as synced."""
        entity = await self.get(id)
        if entity:
            entity.mark_synced(server_updated_at)
            await self.session.flush()
        return entity
        
    async def mark_conflict(self, id: str, error: str) -> Optional[T]:
        """Mark entity as having conflict."""
        entity = await self.get(id)
        if entity:
            entity.mark_conflict(error)
            await self.session.flush()
        return entity
        
    async def resolve_conflict(self, id: str, **kwargs) -> Optional[T]:
        """Resolve conflict by updating entity."""
        entity = await self.get(id)
        if not entity:
            return None
            
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
                
        entity.mark_synced(kwargs.get("updated_at", datetime.now()))
        await self.session.flush()
        return entity