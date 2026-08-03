"""
Relationship Model for Knowledge Graph

This module defines the EntityRelationship model that represents edges
between entities in the knowledge graph.
"""

from enum import Enum
from typing import Dict, Any, Optional, TYPE_CHECKING
from sqlalchemy import Column, String, JSON, ForeignKeyConstraint
from sqlalchemy.orm import relationship

from .base import Base, InbetweeniesTimestampMixin

if TYPE_CHECKING:
    from .entity import Entity, EntityType


class RelationshipType(str, Enum):
    """Types of relationships between entities.

    ADR-012 §1: the house domain's edge vocabulary. The column below is a plain
    String, so this class names constants rather than constraining the schema.
    ``(str, Enum)`` means ``RelationshipType.LOCATED_IN == "located_in"``, so the
    valid_combinations table further down keys correctly whether it is handed an
    enum member or the plain string a query now returns.
    """

    LOCATED_IN = "located_in"
    CONTROLS = "controls"
    CONNECTS_TO = "connects_to"
    PART_OF = "part_of"
    MANAGES = "manages"
    DOCUMENTED_BY = "documented_by"
    PROCEDURE_FOR = "procedure_for"
    TRIGGERED_BY = "triggered_by"
    DEPENDS_ON = "depends_on"
    CONTAINED_IN = "contained_in"
    MONITORS = "monitors"
    AUTOMATES = "automates"
    CONTROLLED_BY_APP = "controlled_by_app"  # New: Links devices to controlling apps
    # ADR-013 §3: replaces HAS_BLOB, which never pointed at a blob -- it pointed
    # at a note that carried one. A relationship names the attachment's role;
    # the blob itself is reached only by content.blob_id on the attachment
    # entity. PDFs are `manual` entities and attach via DOCUMENTED_BY.
    HAS_PHOTO = "has_photo"


class EntityRelationship(Base, InbetweeniesTimestampMixin):
    """
    Represents edges in the knowledge graph connecting entities.

    This model supports:
    - Typed relationships via RelationshipType enum
    - Versioned relationships (tracks entity versions)
    - Additional properties stored as JSON
    - User tracking for audit
    """
    __tablename__ = "entity_relationships"

    id = Column(String(36), primary_key=True)

    # Source entity (from)
    from_entity_id = Column(String(36), nullable=False)
    from_entity_version = Column(String(255), nullable=False)

    # Target entity (to)
    to_entity_id = Column(String(36), nullable=False)
    to_entity_version = Column(String(255), nullable=False)

    # Relationship metadata. Plain String, not SQLEnum (ADR-012 §1) — see the
    # note on Entity.entity_type. Reads yield a plain str; `.value` on this
    # attribute must be guarded.
    relationship_type = Column(String, nullable=False, index=True)
    properties = Column(JSON, default=dict)

    # Tracking
    user_id = Column(String(36), nullable=True)  # No foreign key, just track the user ID

    # Foreign key constraints
    __table_args__ = (
        ForeignKeyConstraint(
            ["from_entity_id", "from_entity_version"],
            ["entities.id", "entities.version"],
            name="fk_from_entity"
        ),
        ForeignKeyConstraint(
            ["to_entity_id", "to_entity_version"],
            ["entities.id", "entities.version"],
            name="fk_to_entity"
        ),
    )

    from_entity = relationship(
        "Entity",
        foreign_keys=[from_entity_id, from_entity_version],
        back_populates="outgoing_relationships"
    )

    to_entity = relationship(
        "Entity",
        foreign_keys=[to_entity_id, to_entity_version],
        back_populates="incoming_relationships"
    )

    def __repr__(self):
        return (f"<EntityRelationship(id={self.id}, "
                f"type={getattr(self.relationship_type, 'value', self.relationship_type)}, "
                f"from={self.from_entity_id}, "
                f"to={self.to_entity_id})>")

    def to_dict(self) -> Dict[str, Any]:
        """Convert relationship to dictionary for API responses"""
        return {
            "id": self.id,
            "from_entity_id": self.from_entity_id,
            "from_entity_version": self.from_entity_version,
            "to_entity_id": self.to_entity_id,
            "to_entity_version": self.to_entity_version,
            "relationship_type": getattr(self.relationship_type, "value", self.relationship_type),
            "properties": self.properties,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if hasattr(self.created_at, "isoformat") else self.created_at,
            "updated_at": self.updated_at.isoformat() if hasattr(self.updated_at, "isoformat") else self.updated_at
        }

    def is_valid_for_entities(self, from_entity: "Entity", to_entity: "Entity") -> bool:
        """
        Validate if this relationship type is valid between the given entity types.

        Args:
            from_entity: Source entity
            to_entity: Target entity

        Returns:
            True if the relationship is valid, False otherwise
        """
        from .entity import EntityType

        # Define valid combinations for each relationship type
        valid_combinations = {
            RelationshipType.LOCATED_IN: [
                (EntityType.DEVICE, EntityType.ROOM),
                (EntityType.DEVICE, EntityType.ZONE),
                (EntityType.ROOM, EntityType.ZONE),
                (EntityType.ROOM, EntityType.HOME),
                (EntityType.ZONE, EntityType.HOME),
            ],
            RelationshipType.CONTROLS: [
                (EntityType.DEVICE, EntityType.DEVICE),
                (EntityType.AUTOMATION, EntityType.DEVICE),
                (EntityType.SCHEDULE, EntityType.DEVICE),
                (EntityType.SCHEDULE, EntityType.AUTOMATION),
            ],
            RelationshipType.CONNECTS_TO: [
                (EntityType.ROOM, EntityType.ROOM),
                (EntityType.DOOR, EntityType.ROOM),
                (EntityType.WINDOW, EntityType.ROOM),
                (EntityType.ZONE, EntityType.ZONE),
            ],
            RelationshipType.PART_OF: [
                (EntityType.ROOM, EntityType.HOME),
                (EntityType.ZONE, EntityType.HOME),
                (EntityType.DEVICE, EntityType.ZONE),
            ],
            RelationshipType.DOCUMENTED_BY: [
                (EntityType.DEVICE, EntityType.MANUAL),
                (EntityType.DEVICE, EntityType.PROCEDURE),
                (EntityType.HOME, EntityType.MANUAL),
                (EntityType.ROOM, EntityType.NOTE),
            ],
            RelationshipType.PROCEDURE_FOR: [
                (EntityType.PROCEDURE, EntityType.DEVICE),
                (EntityType.PROCEDURE, EntityType.HOME),
            ],
            RelationshipType.TRIGGERED_BY: [
                (EntityType.AUTOMATION, EntityType.DEVICE),
                (EntityType.AUTOMATION, EntityType.SCHEDULE),
            ],
            RelationshipType.MANAGES: [
                (EntityType.AUTOMATION, EntityType.DEVICE),
                (EntityType.SCHEDULE, EntityType.AUTOMATION),
            ],
            RelationshipType.MONITORS: [
                (EntityType.DEVICE, EntityType.ROOM),
                (EntityType.DEVICE, EntityType.ZONE),
                (EntityType.AUTOMATION, EntityType.DEVICE),
            ],
            RelationshipType.AUTOMATES: [
                (EntityType.AUTOMATION, EntityType.DEVICE),
                (EntityType.AUTOMATION, EntityType.ROOM),
                (EntityType.AUTOMATION, EntityType.ZONE),
            ],
            RelationshipType.CONTROLLED_BY_APP: [
                (EntityType.DEVICE, EntityType.APP),
                (EntityType.HOME, EntityType.APP),
                (EntityType.AUTOMATION, EntityType.APP),
            ],
            RelationshipType.HAS_PHOTO: [
                (EntityType.DEVICE, EntityType.PHOTO),
                (EntityType.DOOR, EntityType.PHOTO),
                (EntityType.WINDOW, EntityType.PHOTO),
                (EntityType.ROOM, EntityType.PHOTO),
                (EntityType.HOME, EntityType.PHOTO),
                (EntityType.APP, EntityType.PHOTO),     # App icons / screenshots
                (EntityType.NOTE, EntityType.PHOTO),
                (EntityType.MANUAL, EntityType.PHOTO),
            ],
        }

        # Get valid combinations for this relationship type
        valid_for_type = valid_combinations.get(self.relationship_type, [])

        # Check if the entity type combination is valid
        return (from_entity.entity_type, to_entity.entity_type) in valid_for_type
