"""
Inbetweenies Protocol - Smart Home Data Models

STATUS: ✅ Production Ready - All models tested and operational

ARCHITECTURE:
SQLAlchemy models for The Goodies smart home knowledge graph system
supporting both modern Entity-based architecture and legacy HomeKit
compatibility for seamless migration and integration.

CORE MODELS:
- Entity: Universal smart home entity (devices, rooms, homes, etc.)
- EntityRelationship: Connections between entities with typed relationships
- Home/Room/Accessory: HomeKit-compatible legacy models
- Service/Characteristic: Device capability modeling
- User: Access control and user management
- SyncMetadata: Client synchronization state tracking

ENTITY TYPES:
HOME, ROOM, DEVICE, ZONE, DOOR, WINDOW, PROCEDURE, MANUAL, NOTE, 
SCHEDULE, AUTOMATION - comprehensive smart home entity coverage

RELATIONSHIP TYPES:
LOCATED_IN, CONTROLS, MONITORS, PART_OF, DEPENDS_ON, SIMILAR_TO -
flexible entity interconnection modeling

KEY FEATURES:
- Immutable versioning with complete audit trail
- Full-text search capabilities across all entity content
- Backward compatibility with HomeKit models
- Graph operations with relationship traversal
- Content field for flexible device-specific data storage

PRODUCTION READY:
All models successfully handle entity storage, relationships,
and synchronization with comprehensive test coverage.
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