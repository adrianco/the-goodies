"""
Blowing-Off Models - Using Inbetweenies graph-based models

DEVELOPMENT CONTEXT:
Updated in August 2025 to use only graph-based models from the
Inbetweenies package. Removed all HomeKit-specific models in favor
of the more flexible Entity/EntityRelationship approach.

FUNCTIONALITY:
- Imports shared graph models (Entity, EntityRelationship)
- Adds client-specific ClientSyncTracking model for local change detection
- Maintains compatibility with server-side graph models
- Enables sync protocol without polluting shared models

REVISION HISTORY:
- 2025-07-28: Migrated from local models to shared Inbetweenies models
- 2025-07-29: Added ClientSyncTracking for local sync functionality
- 2025-08-12: Removed HomeKit models, now using only graph-based models
"""

# Import all shared models from inbetweenies (including SyncMetadata)
from inbetweenies.models import (
    Base,
    InbetweeniesTimestampMixin,
    SyncMetadata,
    Entity,
    EntityType,
    SourceType,
    EntityRelationship,
    RelationshipType
)

# Import client-specific models
from .sync_tracking import ClientSyncTracking

__all__ = [
    'Base',
    'InbetweeniesTimestampMixin',
    'SyncMetadata',
    'Entity',
    'EntityType',
    'SourceType',
    'EntityRelationship',
    'RelationshipType',
    'ClientSyncTracking'
]
