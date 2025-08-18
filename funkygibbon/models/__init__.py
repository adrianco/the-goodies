"""
FunkyGibbon Models - Using Inbetweenies graph-based models only
"""

# Import all shared graph models from inbetweenies
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

__all__ = [
    'Base',
    'InbetweeniesTimestampMixin',
    'SyncMetadata',
    'Entity',
    'EntityType',
    'SourceType',
    'EntityRelationship',
    'RelationshipType'
]
