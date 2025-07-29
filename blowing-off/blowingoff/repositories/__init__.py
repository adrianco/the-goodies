"""
Blowing-Off Client - Repository Package

DEVELOPMENT CONTEXT:
Created as the data access layer in January 2024. This package implements the
repository pattern for all client-side database operations. Each repository
provides type-safe, sync-aware access to specific entity types. The repository
pattern ensures clean separation between business logic and data persistence,
making the codebase easier to test and maintain.

FUNCTIONALITY:
- Exports all repository classes for entity access
- Provides consistent interface across all entity types
- Ensures sync tracking on all data mutations
- Supports both generic and specialized queries
- Enables mock implementations for testing
- Handles transaction boundaries properly

PURPOSE:
This package enables:
- Clean data access abstraction
- Consistent sync tracking
- Type-safe database operations
- Easy testing with mocks
- Specialized queries per entity
- Future database migration support

KNOWN ISSUES:
- No caching layer implemented yet
- Missing bulk operation optimizations
- No query result pagination
- Limited indexing strategies

REVISION HISTORY:
- 2024-01-15: Initial repository pattern implementation
- 2024-01-18: Added sync metadata repository
- 2024-01-20: Enhanced with specialized queries
- 2024-01-22: Added entity state repository

DEPENDENCIES:
- Base repository for common functionality
- Entity-specific model classes
- SQLAlchemy for database operations

USAGE:
    from blowingoff.repositories import ClientDeviceRepository
    
    async with session_factory() as session:
        device_repo = ClientDeviceRepository(session)
        devices = await device_repo.get_by_room(room_id)
        
        # All mutations automatically track sync status
        await device_repo.update(device_id, name="New Name")
"""

from .base import ClientBaseRepository
from .house import ClientHouseRepository
from .room import ClientRoomRepository
from .device import ClientDeviceRepository
from .user import ClientUserRepository
from .entity_state import ClientEntityStateRepository
from .event import ClientEventRepository
from .sync_metadata import SyncMetadataRepository

__all__ = [
    "ClientBaseRepository",
    "ClientHouseRepository",
    "ClientRoomRepository",
    "ClientDeviceRepository",
    "ClientUserRepository",
    "ClientEntityStateRepository",
    "ClientEventRepository",
    "SyncMetadataRepository",
]