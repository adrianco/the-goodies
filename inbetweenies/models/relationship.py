"""
Relationship Model for Knowledge Graph

This module defines the EntityRelationship model that represents edges
between entities in the knowledge graph.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Dict, Any, Optional, TYPE_CHECKING
from sqlalchemy import Column, DateTime, Index, String, JSON
from sqlalchemy.orm import relationship

from .base import Base, InbetweeniesTimestampMixin

if TYPE_CHECKING:
    from .entity import Entity, EntityType


def _as_aware(value: datetime) -> datetime:
    """Treat a naive datetime as UTC.

    SQLite has no timezone type, so a ``DateTime(timezone=True)`` column round
    trips as naive however it was written. Comparing that against an aware
    "now" raises TypeError, which would turn every interval check into a 500 on
    exactly the rows the migration backfilled. Storage is UTC throughout, so
    reattaching UTC is a restatement of the invariant rather than a guess.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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

    # ADR-004 §1: (id, valid_from) mirrors the entity table's (id, version).
    #
    # `id` is the LOGICAL edge identity, stable across every interval of that
    # edge's life; `valid_from` distinguishes the successive rows. A single-column
    # `id` key made "never update a row" unimplementable — a re-pointed edge had
    # nowhere to put its successor, which is exactly why the old code mutated the
    # row in place and destroyed the prior topology (review finding C4).
    id = Column(String(36), primary_key=True)
    # Defaulted so every construction site gets a well-formed interval without
    # having to remember: an edge starts being true when it is created. Sync
    # apply overrides it with the incoming interval's own valid_from, which is
    # the client's edit time and the axis that matters (ADR-004 §2).
    valid_from = Column(
        DateTime(timezone=True),
        primary_key=True,
        default=lambda: datetime.now(UTC),
    )

    # Source entity (from)
    from_entity_id = Column(String(36), nullable=False)

    # Target entity (to)
    to_entity_id = Column(String(36), nullable=False)

    # Relationship metadata. Plain String, not SQLEnum (ADR-012 §1) — see the
    # note on Entity.entity_type. Reads yield a plain str; `.value` on this
    # attribute must be guarded.
    relationship_type = Column(String, nullable=False, index=True)
    properties = Column(JSON, default=dict)

    # Tracking
    user_id = Column(String(36), nullable=True)  # No foreign key, just track the user ID

    # ADR-004 §1: edges are immutable interval rows.
    #
    # An edge is true over a half-open interval on the VALID-TIME axis (client
    # edit time, ADR-004 §2) — never on server_seq, which is the replication
    # axis and must not be consulted by queries. Changing an edge ends the old
    # row and inserts a new one; deleting ends the row. Rows are never updated
    # in content and never deleted, which is what makes the prior topology
    # recoverable: before this, re-pointing a `located_in` edge overwrote the
    # row and the old placement was simply gone (review finding C4).
    #
    # Current at T  ⇔  valid_from <= T < coalesce(valid_to, ∞)
    # Current graph ⇔  valid_to IS NULL   (what the GraphIndex loads; ADR-003
    #                                      is unchanged by this)
    #
    # valid_from is a primary-key column, declared above. valid_to stays
    # nullable, and null is not "unknown" — it is the open interval, meaning
    # this edge is still true.
    valid_to = Column(DateTime(timezone=True), nullable=True, index=True)

    # ADR-004 §1: the composite version-pin columns and their FKs are GONE.
    #
    # A pin recorded which entity *version* an edge pointed at when it was
    # created. That is temporal-looking and temporally useless: it says nothing
    # about when the edge stopped being true, and it forced an edge rewrite on
    # every endpoint version bump. Endpoints now resolve by id + T through
    # snapshot() (ADR-004 §3.4), so the time axis does the job the pin was only
    # pretending to do.
    #
    # The ORM from_entity/to_entity relationships went with them. They were
    # static joins onto one frozen version; an as-of graph has no single correct
    # endpoint row to join to, because the answer depends on T. Callers resolve
    # endpoints explicitly instead — a lost convenience, but the convenience was
    # returning a wrong answer for every T except creation time.
    __table_args__ = (
        # The current graph: what GraphIndex loads, and the overwhelmingly
        # common read. ADR-003's design is unchanged by this.
        Index("ix_rel_current", "valid_to"),
        # As-of resolution walks one edge id's intervals in time order.
        Index("ix_rel_id_validity", "id", "valid_from", "valid_to"),
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
            "to_entity_id": self.to_entity_id,
            "relationship_type": getattr(self.relationship_type, "value", self.relationship_type),
            "properties": self.properties,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if hasattr(self.created_at, "isoformat") else self.created_at,
            "updated_at": self.updated_at.isoformat() if hasattr(self.updated_at, "isoformat") else self.updated_at,
            # ADR-004 §1 interval bounds. Emitted as None rather than omitted so
            # a consumer can distinguish "still true" (valid_to null) from an
            # older peer that does not carry the field at all.
            "valid_from": self.valid_from.isoformat() if hasattr(self.valid_from, "isoformat") else self.valid_from,
            "valid_to": self.valid_to.isoformat() if hasattr(self.valid_to, "isoformat") else self.valid_to,
        }

    def is_current_at(self, at: Optional[datetime] = None) -> bool:
        """Is this edge true at ``at`` on the valid-time axis? (ADR-004 §1/§3.3)

        Half-open by design: ``valid_from <= at < coalesce(valid_to, ∞)``. The
        interval is closed at the start and open at the end so that ending one
        row and starting its successor at the same instant yields exactly one
        current edge, never zero and never two — which is the whole point of
        end-and-insert.

        A null ``valid_from`` reads as "has always been true" so that rows
        written before the ADR-004 migration remain visible rather than
        silently dropping out of every snapshot.
        """
        moment = at or datetime.now(UTC)
        if self.valid_from is not None and _as_aware(self.valid_from) > moment:
            return False
        if self.valid_to is not None and _as_aware(self.valid_to) <= moment:
            return False
        return True

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
