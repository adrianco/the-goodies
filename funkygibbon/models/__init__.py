"""
FunkyGibbon Models - Using Inbetweenies HomeKit-compatible models + Graph models
"""

# Import all shared models from inbetweenies
from inbetweenies.models import (
    Base,
    Home,
    Room,
    Accessory,
    Service,
    Characteristic,
    User,
    accessory_rooms,
    SyncMetadata
)

# Import new graph models from inbetweenies
from inbetweenies.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType

__all__ = [
    'Base',
    'Home',
    'Room',
    'Accessory',
    'Service',
    'Characteristic',
    'User',
    'accessory_rooms',
    'SyncMetadata',
    # Graph models
    'Entity',
    'EntityType',
    'SourceType',
    'EntityRelationship',
    'RelationshipType'
]