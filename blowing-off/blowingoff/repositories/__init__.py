"""
Blowing-Off Client - Repository Package

DEVELOPMENT CONTEXT:
Created as the data access layer in July 2025. This package implements the
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
- 2025-07-28: Initial repository pattern implementation
- 2025-07-28: Added sync metadata repository
- 2025-07-28: Enhanced with specialized queries
- 2025-07-28: Added entity state repository

DEPENDENCIES:
- Base repository for common functionality
- Entity-specific model classes
- SQLAlchemy for database operations

USAGE:
    from blowingoff.repositories import ClientAccessoryRepository
    
    async with session_factory() as session:
        accessory_repo = ClientAccessoryRepository(session)
        accessories = await accessory_repo.get_by_room(room_id)
        
        # All mutations automatically track sync status
        await accessory_repo.update(accessory_id, name="New Name")
"""

from .base import ClientBaseRepository
from .home import ClientHomeRepository
from .room import ClientRoomRepository
from .accessory import ClientAccessoryRepository
from .user import ClientUserRepository
# EntityState and Event repositories removed for HomeKit focus
# from .entity_state import ClientEntityStateRepository  
# from .event import ClientEventRepository
from .sync_metadata import SyncMetadataRepository

__all__ = [
    "ClientBaseRepository",
    "ClientHomeRepository",
    "ClientRoomRepository",
    "ClientAccessoryRepository",
    "ClientUserRepository",
    # "ClientEntityStateRepository",  # Removed for HomeKit focus
    # "ClientEventRepository",         # Removed for HomeKit focus
    "SyncMetadataRepository",
]