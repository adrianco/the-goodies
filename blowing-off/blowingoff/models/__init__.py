"""
Blowing-Off Models - Using Inbetweenies HomeKit-compatible models

DEVELOPMENT CONTEXT:
Updated in July 2025 to use shared HomeKit-compatible models from the
Inbetweenies package while adding client-specific sync tracking functionality.
This enables the client to work with standardized models while maintaining
local change detection capabilities.

FUNCTIONALITY:
- Imports shared HomeKit models (Home, Room, Accessory, etc.)
- Adds client-specific ClientSyncTracking model for local change detection
- Maintains compatibility with server-side models
- Enables sync protocol without polluting shared models

REVISION HISTORY:
- 2025-07-28: Migrated from local models to shared Inbetweenies models
- 2025-07-29: Added ClientSyncTracking for local sync functionality
- 2025-07-29: Removed unused entity_state and event repository files
"""

# Import all shared models from inbetweenies (including SyncMetadata)
from inbetweenies.models import (
    Base,
    Home,
    Room,
    Accessory,
    Service,
    Characteristic,
    User,
    accessory_rooms,
    InbetweeniesTimestampMixin,
    SyncMetadata
)

# Import client-specific models
from .sync_tracking import ClientSyncTracking

__all__ = [
    'Base',
    'Home',
    'Room',
    'Accessory',
    'Service',
    'Characteristic',
    'User',
    'accessory_rooms',
    'InbetweeniesTimestampMixin',
    'SyncMetadata',
    'ClientSyncTracking'
]