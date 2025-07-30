"""
Inbetweenies Protocol - Shared Models

These models are designed to match HomeKit's structure:
- Home: Top-level container (HMHome)
- Room: Locations within a home (HMRoom)  
- Accessory: Physical devices (HMAccessory)
- Service: Functions an accessory provides (HMService)
- Characteristic: Properties of a service (HMCharacteristic)
- User: People with access to the home (HMUser)
- SyncMetadata: Synchronization state and history tracking
"""

from .base import Base, InbetweeniesTimestampMixin
from .home import Home
from .room import Room
from .accessory import Accessory, accessory_rooms
from .service import Service
from .characteristic import Characteristic
from .user import User
from .sync_metadata import SyncMetadata
from .entity import Entity, EntityType, SourceType
from .relationship import EntityRelationship, RelationshipType

__all__ = [
    'Base',
    'InbetweeniesTimestampMixin',
    'Home',
    'Room',
    'Accessory',
    'accessory_rooms',
    'Service',
    'Characteristic',
    'User',
    'SyncMetadata',
    'Entity',
    'EntityType',
    'SourceType',
    'EntityRelationship',
    'RelationshipType'
]