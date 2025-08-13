"""
Inbetweenies Protocol - Smart Home Data Models

STATUS: ✅ Production Ready - Graph-based models only

ARCHITECTURE:
SQLAlchemy models for The Goodies smart home knowledge graph system
using a pure Entity-based architecture for maximum flexibility.

CORE MODELS:
- Entity: Universal smart home entity (devices, rooms, homes, etc.)
- EntityRelationship: Connections between entities with typed relationships
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
- Graph operations with relationship traversal
- Content field for flexible device-specific data storage

PRODUCTION READY:
All models successfully handle entity storage, relationships,
and synchronization with comprehensive test coverage.
"""

from .base import Base, InbetweeniesTimestampMixin
from .sync_metadata import SyncMetadata
from .entity import Entity, EntityType, SourceType
from .relationship import EntityRelationship, RelationshipType
from .blob import Blob, BlobType, BlobStatus

__all__ = [
    'Base',
    'InbetweeniesTimestampMixin',
    'SyncMetadata',
    'Entity',
    'EntityType',
    'SourceType',
    'EntityRelationship',
    'RelationshipType',
    'Blob',
    'BlobType',
    'BlobStatus'
]