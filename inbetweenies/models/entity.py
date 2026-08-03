"""
Entity Model for Knowledge Graph

This module defines the generic Entity model that can represent any node
in the knowledge graph (homes, rooms, devices, procedures, etc.).
"""

import itertools
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Any, Optional
from sqlalchemy import (
    Boolean, Column, Index, Integer, JSON, String, DateTime, text
)
from sqlalchemy.orm import relationship

from .base import Base, InbetweeniesTimestampMixin

# Monotonic per-process counter for version-string tiebreaking. next() is atomic
# under CPython's GIL, so this is safe across threads without extra locking.
_version_counter = itertools.count()


class EntityType(str, Enum):
    """Types of entities in the knowledge graph.

    ADR-012 §1: this is the *house domain's* vocabulary, not the engine's. The
    columns that used to be ``SQLEnum(EntityType)`` are plain strings now, so a
    second domain is a manifest rather than a schema migration. The class stays
    because house code (and the future house manifest) still needs names for
    these constants — but nothing in the store depends on it. Being a
    ``(str, Enum)`` subclass, ``EntityType.DEVICE == "device"`` holds, which is
    why comparisons across the codebase survive the column change untouched.
    """

    # Core entity types
    HOME = "home"
    ROOM = "room"
    DEVICE = "device"
    ZONE = "zone"
    DOOR = "door"
    WINDOW = "window"
    PROCEDURE = "procedure"
    MANUAL = "manual"
    NOTE = "note"
    SCHEDULE = "schedule"
    AUTOMATION = "automation"
    APP = "app"  # New: Application entity type for HomeKit, Comfort app, etc.


class SourceType(str, Enum):
    """Source of entity data"""
    HOMEKIT = "homekit"
    MATTER = "matter"
    MANUAL = "manual"
    IMPORTED = "imported"
    GENERATED = "generated"


class Entity(Base, InbetweeniesTimestampMixin):
    """
    Generic entity that can represent any node in the knowledge graph.

    This model supports:
    - Flexible entity types via EntityType enum
    - JSON content for extensible properties
    - Version tracking with parent versions for immutability
    - Source tracking to know where data originated
    """
    __tablename__ = "entities"

    # Primary key is composite of id and version for immutability
    id = Column(String(36), primary_key=True)
    version = Column(String(255), primary_key=True)

    # Entity metadata.
    #
    # ADR-012 §1: a plain String, not SQLEnum(EntityType). Vocabulary is the
    # domain's business, checked at the API/sync boundary against the domain
    # manifest; the engine stores what the domain declares. As SQLEnum this was
    # HOME/ROOM/DEVICE baked into the *database*, making a new domain a schema
    # migration. Reads now yield a plain str rather than an EntityType, so any
    # `.value` on this attribute must be guarded (see to_dict below).
    entity_type = Column(String, nullable=False, index=True)
    name = Column(String(255), nullable=False)

    # Flexible content storage
    content = Column(JSON, nullable=False, default=dict)

    # Tracking
    source_type = Column(String, nullable=False, default=SourceType.MANUAL.value)
    user_id = Column(String(36), nullable=True)  # No foreign key, just track the user ID

    # Version tracking for immutability
    parent_versions = Column(JSON, default=list)

    # --- Server-maintained bookkeeping (ADR-002) ---------------------------
    # Both are assigned by the server when it stores a row. Clients replicate
    # them but never author them, and neither appears on the wire.
    #
    # is_latest records which version won, rather than leaving it to be
    # re-derived. Three places used to infer it independently and disagree:
    # api/sync.py took the lexically greatest version, GraphRepository took the
    # greatest created_at, and conflict resolution decided by LWW on
    # updated_at. That let a preserved losing version be served as current by
    # the REST API while sync correctly reported the winner. A resolution
    # outcome is a fact about a row, so it is stored on the row.
    is_latest = Column(Boolean, nullable=False, default=True, server_default=text("1"))

    # server_seq is the replication axis (ADR-004 §2): a gap-free monotonic
    # stamp assigned in server apply order, used for delta cursors and
    # pagination. Deliberately NOT wall-clock: `updated_at > since` cannot
    # distinguish rows written in the same microsecond, and is hostage to clock
    # adjustment. Queries never consult it; sync never consults client time.
    server_seq = Column(Integer, nullable=True)

    __table_args__ = (
        # The delta scan: `where is_latest and server_seq > :cursor`.
        Index("ix_entities_is_latest_server_seq", "is_latest", "server_seq"),
        # `max(server_seq)` for the next stamp and for ADR-003's generation
        # check. The composite above cannot serve this: its leading column is
        # is_latest, so a bare server_seq aggregate would have to scan.
        Index("ix_entities_server_seq", "server_seq"),
        # Resolving one entity's history.
        Index("ix_entities_id_version", "id", "version"),
    )

    # Relationships defined in EntityRelationship model
    outgoing_relationships = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.from_entity_id",
        back_populates="from_entity",
        primaryjoin="and_(Entity.id==EntityRelationship.from_entity_id, "
                   "Entity.version==EntityRelationship.from_entity_version)"
    )

    incoming_relationships = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.to_entity_id",
        back_populates="to_entity",
        primaryjoin="and_(Entity.id==EntityRelationship.to_entity_id, "
                   "Entity.version==EntityRelationship.to_entity_version)"
    )

    def __repr__(self):
        entity_type_str = self.entity_type.value if hasattr(self.entity_type, 'value') else str(self.entity_type)
        return f"<Entity(id={self.id}, type={entity_type_str}, name={self.name}, version={self.version[:8] if self.version else ''})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary for API responses"""
        # Handle entity_type and source_type that might be strings or enums
        entity_type_value = self.entity_type.value if hasattr(self.entity_type, 'value') else str(self.entity_type)
        source_type_value = self.source_type.value if hasattr(self.source_type, 'value') else str(self.source_type)

        return {
            "id": self.id,
            "version": self.version,
            "entity_type": entity_type_value,
            "name": self.name,
            "content": self.content,
            "source_type": source_type_value,
            "user_id": self.user_id,
            "parent_versions": self.parent_versions,
            "created_at": self.created_at.isoformat() if hasattr(self.created_at, "isoformat") else self.created_at,
            "updated_at": self.updated_at.isoformat() if hasattr(self.updated_at, "isoformat") else self.updated_at
        }

    @classmethod
    def create_version(cls, user_id: str) -> str:
        """Generate a version string: ``{utc-iso8601}-{counter:06d}-{user_id}``.

        The timestamp is timezone-aware UTC ISO-8601 (``+00:00`` offset, no extra
        trailing ``Z``). The counter is a 6-digit monotonic per-process tiebreaker
        that disambiguates edits made within the same microsecond. Versions sort
        lexically, and because the timestamp prefix is fixed-width UTC, lexical
        order equals chronological order. See inbetweenies/PROTOCOL.md §2.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        counter = next(_version_counter) % 1000000
        return f"{timestamp}-{counter:06d}-{user_id}"

    @staticmethod
    def version_timestamp(version: str) -> Optional[datetime]:
        """Parse the UTC timestamp out of a version string, or None if it can't.

        Version is ``{utc-iso8601}-{counter:06d}-{user_id}``. The ISO-8601 prefix
        ends at the UTC offset (``+00:00``); the counter and (possibly hyphenated)
        user id follow. We anchor on the offset rather than splitting on ``-`` so a
        hyphenated user id (e.g. ``local-client``) parses correctly, and a stray
        legacy trailing ``Z`` is tolerated. Used to derive a remote edit's time for
        conflict resolution, since the wire EntityChange carries no updated_at.
        """
        match = re.match(r"^(.*?[+-]\d{2}:\d{2})", version)
        if not match:
            return None
        try:
            parsed = datetime.fromisoformat(match.group(1))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def create_new_version(self, user_id: str, changes: Dict[str, Any]) -> "Entity":
        """
        Create a new version of this entity with changes.

        Args:
            user_id: User making the change
            changes: Dictionary of fields to update

        Returns:
            New Entity instance with updated version
        """
        # Create new version data
        new_data = self.to_dict()
        new_data.update(changes)

        # Merge content if provided in changes. The merge is written into
        # new_data, never back into ``changes``: the caller's dict is an input
        # and several callers (e.g. MCPTools.update_entity_tool) report it back
        # as the delta that was requested.
        if "content" in changes:
            merged_content = self.content.copy() if self.content else {}
            merged_content.update(changes["content"])
            new_data["content"] = merged_content

        # Update version tracking
        new_data["version"] = self.create_version(user_id)
        new_data["parent_versions"] = self.parent_versions + [self.version]
        new_data["user_id"] = user_id

        # Remove timestamps as they'll be set automatically
        new_data.pop("created_at", None)
        new_data.pop("updated_at", None)

        # No enum coercion (ADR-012 §1). to_dict() already yields strings and
        # the columns are strings, so the round-trip is now a no-op. The two
        # EntityType()/SourceType() calls that used to sit here would have
        # rejected any vocabulary the house enums don't know — exactly the
        # schema-level gate the ADR moves to the domain manifest at the
        # API/sync boundary.
        return Entity(**new_data)
