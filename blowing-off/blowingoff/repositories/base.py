"""
Blowing-Off Client - Base Repository Pattern

DEVELOPMENT CONTEXT:
Created as the foundation for all data access in July 2025. This repository
pattern provides a clean abstraction over SQLAlchemy for all client-side database
operations. It implements sync-aware CRUD operations that automatically track
local changes for the Inbetweenies protocol. Updated to work with shared
HomeKit-compatible models from Inbetweenies package.

FUNCTIONALITY:
- Generic repository pattern for type-safe data access
- Specialized queries for sync operations (pending, conflicts)
- Automatic sync tracking for create/update operations
- Conflict resolution support with optimistic locking
- Time-based change tracking for incremental sync
- Client-side sync status tracking via ClientSyncTracking model
- Transaction-aware with explicit flush control
- Works with shared HomeKit-compatible models

PURPOSE:
This base repository ensures:
- Consistent data access patterns across all entities
- Clean separation between business logic and data access
- Type safety with Generic[T] pattern
- Efficient queries for sync engine operations
- Easy testing with mockable interface

KNOWN ISSUES:
- No automatic relationship loading (must use selectinload)
- Bulk operations could be more efficient
- Missing query caching for frequently accessed data
- No built-in pagination support yet
- No automatic cleanup of old sync tracking records

REVISION HISTORY:
- 2025-07-28: Initial implementation with basic CRUD
- 2025-07-28: Added sync-aware operations
- 2025-07-28: Enhanced conflict resolution support
- 2025-07-28: Added time-based change queries
- 2025-07-29: Updated to work with shared Inbetweenies models
- 2025-07-29: Implemented ClientSyncTracking for local change detection
- 2025-07-29: Added get_pending(), get_conflicts(), mark_synced() methods
- 2025-07-29: Automatic sync tracking on create/update operations

DEPENDENCIES:
- SQLAlchemy 2.0+ with async support
- Generic typing for type safety
- inbetweenies.models for shared base classes
- ClientSyncTracking model for local change tracking

USAGE:
    class AccessoryRepository(ClientBaseRepository[Accessory]):
        def __init__(self, session: AsyncSession):
            super().__init__(Accessory, session)

        async def get_by_room(self, room_id: str) -> List[Accessory]:
            # Custom query methods can extend base functionality
            result = await self.session.execute(
                select(self.model).where(self.model.room_id == room_id)
            )
            return list(result.scalars().all())
"""

from typing import TypeVar, Generic, Type, Optional, List, Dict, Any
from datetime import datetime, UTC
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from ..models import Base

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
        from ..models.sync_tracking import ClientSyncTracking

        # Get entity IDs with pending sync status
        pending_result = await self.session.execute(
            select(ClientSyncTracking.entity_id)
            .where(and_(
                ClientSyncTracking.entity_type == self.model.__tablename__.rstrip('s'),
                ClientSyncTracking.sync_status == "pending"
            ))
        )
        pending_ids = [row[0] for row in pending_result.fetchall()]

        if not pending_ids:
            return []

        # Get the actual entities
        result = await self.session.execute(
            select(self.model).where(self.model.id.in_(pending_ids))
        )
        return list(result.scalars().all())

    async def get_conflicts(self) -> List[T]:
        """Get entities with conflicts."""
        from ..models.sync_tracking import ClientSyncTracking

        # Get entity IDs with conflict status
        conflict_result = await self.session.execute(
            select(ClientSyncTracking.entity_id)
            .where(and_(
                ClientSyncTracking.entity_type == self.model.__tablename__.rstrip('s'),
                ClientSyncTracking.sync_status == "conflict"
            ))
        )
        conflict_ids = [row[0] for row in conflict_result.fetchall()]

        if not conflict_ids:
            return []

        # Get the actual entities
        result = await self.session.execute(
            select(self.model).where(self.model.id.in_(conflict_ids))
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
        """Create new entity."""
        entity = self.model(**kwargs)
        self.session.add(entity)
        await self.session.flush()

        # Mark as pending for sync
        await self._mark_pending(entity.id, "create")

        return entity

    async def update(self, id: str, **kwargs) -> Optional[T]:
        """Update entity and mark as pending."""
        entity = await self.get(id)
        if not entity:
            return None

        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        # Mark as pending for sync
        await self._mark_pending(id, "update")

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
        from ..models.sync_tracking import ClientSyncTracking

        entity = await self.get(id)
        if not entity:
            return None

        # Find or create sync tracking record
        sync_record = await self._get_or_create_sync_record(id)
        sync_record.mark_synced()

        await self.session.flush()
        return entity

    async def mark_conflict(self, id: str, error: str) -> Optional[T]:
        """Mark entity as having conflict."""
        from ..models.sync_tracking import ClientSyncTracking

        entity = await self.get(id)
        if not entity:
            return None

        # Find or create sync tracking record
        sync_record = await self._get_or_create_sync_record(id)
        sync_record.mark_conflict(error)

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

        # Mark as pending for sync
        await self._mark_pending(id, "update")

        await self.session.flush()
        return entity

    async def _get_or_create_sync_record(self, entity_id: str):
        """Get or create sync tracking record for entity."""
        from ..models.sync_tracking import ClientSyncTracking

        # Try to find existing record
        result = await self.session.execute(
            select(ClientSyncTracking)
            .where(and_(
                ClientSyncTracking.entity_id == entity_id,
                ClientSyncTracking.entity_type == self.model.__tablename__.rstrip('s')
            ))
        )
        sync_record = result.scalar_one_or_none()

        if not sync_record:
            # Create new record
            sync_record = ClientSyncTracking(
                entity_id=entity_id,
                entity_type=self.model.__tablename__.rstrip('s'),
                entity_updated_at=datetime.now(UTC)
            )
            self.session.add(sync_record)

        return sync_record

    async def _mark_pending(self, entity_id: str, operation: str = "update"):
        """Mark entity as having pending changes."""
        sync_record = await self._get_or_create_sync_record(entity_id)
        sync_record.mark_pending(operation)
        await self.session.flush()
