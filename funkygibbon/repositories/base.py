"""
Base repository class with common CRUD operations and conflict resolution.
"""

import json
from datetime import datetime, UTC
from datetime import datetime, UTC
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.base import Base, BaseEntity, ConflictResolution

T = TypeVar("T", bound=BaseEntity)


class ConflictResolver:
    """Handles last-write-wins conflict resolution."""
    
    @staticmethod
    def resolve(local: Dict[str, Any], remote: Dict[str, Any]) -> ConflictResolution:
        """
        Resolve conflicts using last-write-wins strategy.
        
        Args:
            local: Local entity data
            remote: Remote entity data
            
        Returns:
            ConflictResolution with winner and reason
        """
        local_ts = datetime.fromisoformat(local["updated_at"].replace("Z", "+00:00"))
        remote_ts = datetime.fromisoformat(remote["updated_at"].replace("Z", "+00:00"))
        
        # Calculate millisecond difference
        diff_ms = int((remote_ts - local_ts).total_seconds() * 1000)
        
        if abs(diff_ms) < 1000:  # Within 1 second, use sync_id as tiebreaker
            if remote["sync_id"] > local["sync_id"]:
                return ConflictResolution(
                    winner=remote,
                    loser=local,
                    reason="timestamps equal, remote has higher sync_id",
                    timestamp_diff_ms=diff_ms
                )
            else:
                return ConflictResolution(
                    winner=local,
                    loser=remote,
                    reason="timestamps equal, local has higher sync_id",
                    timestamp_diff_ms=diff_ms
                )
        
        if remote_ts > local_ts:
            return ConflictResolution(
                winner=remote,
                loser=local,
                reason="remote has newer timestamp",
                timestamp_diff_ms=diff_ms
            )
        else:
            return ConflictResolution(
                winner=local,
                loser=remote,
                reason="local has newer timestamp",
                timestamp_diff_ms=diff_ms
            )


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""
    
    def __init__(self, model_class: Type[T]):
        self.model_class = model_class
        self.conflict_resolver = ConflictResolver()
    
    async def create(self, db: AsyncSession, **kwargs) -> T:
        """Create a new entity."""
        # Set timestamps if not provided
        now = datetime.now(UTC)
        kwargs.setdefault("created_at", now)
        kwargs.setdefault("updated_at", now)
        
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
                self.model_class.is_deleted == False
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_sync_id(self, db: AsyncSession, sync_id: str) -> Optional[T]:
        """Get entity by sync ID."""
        stmt = select(self.model_class).where(
            and_(
                self.model_class.sync_id == sync_id,
                self.model_class.is_deleted == False
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_all(self, db: AsyncSession, limit: int = 1000) -> List[T]:
        """Get all entities (excluding deleted)."""
        stmt = select(self.model_class).where(
            self.model_class.is_deleted == False
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
        entity.version = str(int(entity.version) + 1)
        
        await db.commit()
        await db.refresh(entity)
        return entity
    
    async def soft_delete(self, db: AsyncSession, id: str) -> bool:
        """Soft delete an entity."""
        entity = await self.get_by_id(db, id)
        if not entity:
            return False
        
        entity.is_deleted = True
        entity.updated_at = datetime.now(UTC)
        entity.version = str(int(entity.version) + 1)
        
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
        local_entity = await self.get_by_sync_id(db, sync_id)
        
        if not local_entity:
            # New entity, create it
            entity = await self.create(db, **remote_data)
            return entity, True, None
        
        # Check for conflicts
        local_data = local_entity.to_dict()
        resolution = self.conflict_resolver.resolve(local_data, remote_data)
        
        if resolution.winner == remote_data:
            # Remote wins, update local
            for key, value in remote_data.items():
                if hasattr(local_entity, key) and key not in ["id", "created_at"]:
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