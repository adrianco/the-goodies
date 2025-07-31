"""
Blowing-Off Repositories

DEVELOPMENT CONTEXT:
Updated to use Entity model instead of HomeKit-specific repositories.
All entity operations now go through graph operations.

FUNCTIONALITY:
- Sync metadata repository for tracking sync state
- Base repository patterns (kept for potential future use)

PURPOSE:
Provides repository pattern for sync metadata while entity operations
are handled through graph operations.

REVISION HISTORY:
- 2025-07-30: Removed HomeKit-specific repositories, using Entity model
- 2025-07-28: Initial implementation with HomeKit repositories
"""

from .base import ClientBaseRepository
from .sync_metadata import SyncMetadataRepository

__all__ = [
    "ClientBaseRepository",
    "SyncMetadataRepository",
]