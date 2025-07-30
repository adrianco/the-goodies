"""
Inbetweenies Repository Interfaces - Abstract base classes for repositories

These interfaces define the contract that repositories must implement
to support the Inbetweenies sync protocol.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, TypeVar, Generic

from ..sync.conflict import ConflictResolution
from ..models.base import Base

T = TypeVar("T", bound=Base)


class SyncCapable(ABC):
    """Interface for repositories that support sync operations."""
    
    @abstractmethod
    async def sync_entity(
        self, 
        remote_data: Dict[str, Any]
    ) -> tuple[Any, bool, Optional[ConflictResolution]]:
        """
        Sync a remote entity with local database.
        
        Returns:
            Tuple of (entity, was_updated, conflict_resolution)
        """
        pass
    
    @abstractmethod
    async def get_by_sync_id(self, sync_id: str) -> Optional[Any]:
        """Get entity by sync ID."""
        pass


class ChangeTrackable(ABC):
    """Interface for repositories that track changes."""
    
    @abstractmethod
    async def get_changes_since(
        self, 
        timestamp: datetime,
        limit: int = 100
    ) -> List[Any]:
        """Get all entities changed since a timestamp."""
        pass
    
    @abstractmethod
    async def mark_synced(self, entity_id: str, sync_time: datetime) -> None:
        """Mark an entity as synced."""
        pass


class ConflictAware(ABC):
    """Interface for repositories that handle conflicts."""
    
    @abstractmethod
    async def resolve_conflict(
        self,
        local_entity: Any,
        remote_data: Dict[str, Any]
    ) -> ConflictResolution:
        """Resolve a conflict between local and remote data."""
        pass


class BaseSyncRepository(Generic[T], SyncCapable, ChangeTrackable, ABC):
    """
    Base repository interface combining all sync capabilities.
    
    This is the primary interface that sync-enabled repositories should implement.
    """
    
    @abstractmethod
    async def create(self, **kwargs) -> T:
        """Create a new entity."""
        pass
    
    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[T]:
        """Get entity by ID."""
        pass
    
    @abstractmethod
    async def update(self, id: str, **kwargs) -> Optional[T]:
        """Update an entity by ID."""
        pass
    
    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete an entity (soft or hard delete based on implementation)."""
        pass
    
    @abstractmethod
    async def get_all(self, limit: int = 1000) -> List[T]:
        """Get all entities."""
        pass