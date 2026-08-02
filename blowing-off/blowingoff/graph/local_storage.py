"""
Local storage implementation for graph data.

This module provides a lightweight local storage mechanism for
entities and relationships that can be used offline.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from datetime import datetime

from inbetweenies.models import Entity, EntityRelationship, EntityType, RelationshipType


class LocalGraphStorage:
    """
    Local file-based storage for graph data.

    This provides a simple persistence mechanism for the client
    that doesn't require a full database.
    """

    def __init__(self, storage_dir: str = "~/.blowing-off/graph"):
        """Initialize local storage"""
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.entities_file = self.storage_dir / "entities.json"
        self.relationships_file = self.storage_dir / "relationships.json"
        self.index_file = self.storage_dir / "index.json"
        self.pending_file = self.storage_dir / "pending.json"

        # In-memory caches
        self._entities: Dict[str, List[Entity]] = {}  # entity_id -> list of versions
        self._relationships: List[EntityRelationship] = []
        self._index: Dict[str, Set[str]] = {
            "by_type": {},  # entity_type -> set of entity_ids
            "by_room": {},  # room_id -> set of device_ids
        }

        # Dirty tracking for the sync push path. Maps id -> "create" | "update".
        # Persisted so that writes made while offline survive a restart and are
        # still pushed on the next successful sync.
        self._pending_entities: Dict[str, str] = {}
        self._pending_relationships: Dict[str, str] = {}

        self._load_data()

    def _load_data(self):
        """Load data from disk"""
        # Load entities
        if self.entities_file.exists():
            with open(self.entities_file, 'r') as f:
                data = json.load(f)
                for entity_id, versions in data.items():
                    self._entities[entity_id] = [
                        Entity(**v) for v in versions
                    ]

        # Load relationships
        if self.relationships_file.exists():
            with open(self.relationships_file, 'r') as f:
                data = json.load(f)
                self._relationships = [
                    EntityRelationship(**r) for r in data
                ]

        # Load pending (unpushed) local changes
        if self.pending_file.exists():
            with open(self.pending_file, 'r') as f:
                pending = json.load(f)
                self._pending_entities = pending.get("entities", {})
                self._pending_relationships = pending.get("relationships", {})

        # Load or rebuild index
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                loaded_index = json.load(f)
                # Ensure index has the proper structure
                if not loaded_index or "by_type" not in loaded_index:
                    self._rebuild_index()
                else:
                    self._index = loaded_index
        else:
            self._rebuild_index()

    def _save_data(self):
        """Save data to disk"""
        # Save entities
        entities_data = {}
        for entity_id, versions in self._entities.items():
            entities_data[entity_id] = [
                self._entity_to_dict(v) for v in versions
            ]

        with open(self.entities_file, 'w') as f:
            json.dump(entities_data, f, indent=2, default=str)

        # Save relationships
        relationships_data = [
            self._relationship_to_dict(r) for r in self._relationships
        ]

        with open(self.relationships_file, 'w') as f:
            json.dump(relationships_data, f, indent=2, default=str)

        # Save index
        with open(self.index_file, 'w') as f:
            json.dump(self._index, f, indent=2)

        # Save pending local changes
        with open(self.pending_file, 'w') as f:
            json.dump({
                "entities": self._pending_entities,
                "relationships": self._pending_relationships,
            }, f, indent=2)

    def _entity_to_dict(self, entity: Entity) -> dict:
        """Convert entity to dictionary for JSON serialization"""
        from datetime import datetime

        # Handle entity_type that might be string or enum
        entity_type_value = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
        source_type_value = entity.source_type.value if hasattr(entity.source_type, 'value') else str(entity.source_type)

        # Handle timestamps that might be datetime objects or strings
        created_at = None
        if hasattr(entity, 'created_at') and entity.created_at:
            if isinstance(entity.created_at, datetime):
                created_at = entity.created_at.isoformat()
            else:
                created_at = str(entity.created_at)

        updated_at = None
        if hasattr(entity, 'updated_at') and entity.updated_at:
            if isinstance(entity.updated_at, datetime):
                updated_at = entity.updated_at.isoformat()
            else:
                updated_at = str(entity.updated_at)

        return {
            "id": entity.id or "",
            "version": entity.version or "",
            "entity_type": entity_type_value,
            "name": entity.name or "",
            "content": entity.content or {},
            "source_type": source_type_value,
            "user_id": entity.user_id or "unknown",
            "parent_versions": entity.parent_versions or [],
            "created_at": created_at,
            "updated_at": updated_at
        }

    def _relationship_to_dict(self, rel: EntityRelationship) -> dict:
        """Convert relationship to dictionary for JSON serialization"""
        from datetime import datetime

        # Handle relationship_type that might be string or enum
        rel_type_value = rel.relationship_type.value if hasattr(rel.relationship_type, 'value') else str(rel.relationship_type)

        # Handle timestamp that might be datetime object or string
        created_at = None
        if hasattr(rel, 'created_at') and rel.created_at:
            if isinstance(rel.created_at, datetime):
                created_at = rel.created_at.isoformat()
            else:
                created_at = str(rel.created_at)

        return {
            "id": rel.id,
            "from_entity_id": rel.from_entity_id,
            "from_entity_version": rel.from_entity_version,
            "to_entity_id": rel.to_entity_id,
            "to_entity_version": rel.to_entity_version,
            "relationship_type": rel_type_value,
            "properties": rel.properties,
            "user_id": rel.user_id,
            "created_at": created_at
        }

    def _rebuild_index(self):
        """Rebuild the index from entities and relationships"""
        self._index = {
            "by_type": {},
            "by_room": {}
        }

        # Index entities by type
        for entity_id, versions in self._entities.items():
            if versions:
                latest = versions[-1]
                type_key = latest.entity_type.value if hasattr(latest.entity_type, 'value') else str(latest.entity_type)
                if type_key not in self._index["by_type"]:
                    self._index["by_type"][type_key] = []
                self._index["by_type"][type_key].append(entity_id)

        # Index devices by room
        for rel in self._relationships:
            if rel.relationship_type == RelationshipType.LOCATED_IN:
                room_id = rel.to_entity_id
                device_id = rel.from_entity_id
                if room_id not in self._index["by_room"]:
                    self._index["by_room"][room_id] = []
                self._index["by_room"][room_id].append(device_id)

    def store_entity(self, entity: Entity, mark_dirty: bool = True) -> Entity:
        """Store an entity version.

        Args:
            entity: the entity version to store.
            mark_dirty: whether to queue this version for the next sync push.
                Local writes must mark dirty. The sync engine passes False when
                applying a version it just pulled from the server — otherwise we
                would immediately push the server's own change back to it.
        """
        is_new = entity.id not in self._entities
        if is_new:
            self._entities[entity.id] = []

        # Check if this is a newer version that should replace the current one
        # This is a simplified approach - in production you'd want proper version comparison
        if self._entities[entity.id]:
            current = self._entities[entity.id][-1]
            # If the new entity has the same version but different content, replace it
            # This handles the case where sync brings in updated entities
            if current.version == entity.version:
                self._entities[entity.id][-1] = entity
            else:
                self._entities[entity.id].append(entity)
        else:
            self._entities[entity.id].append(entity)

        # Update index
        type_key = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
        if type_key not in self._index["by_type"]:
            self._index["by_type"][type_key] = []
        if entity.id not in self._index["by_type"][type_key]:
            self._index["by_type"][type_key].append(entity.id)

        if mark_dirty:
            # An entity created locally and then edited again before it ever
            # syncs is still a create as far as the server is concerned, so a
            # pending "create" is never downgraded to "update".
            if self._pending_entities.get(entity.id) != "create":
                self._pending_entities[entity.id] = "create" if is_new else "update"

        self._save_data()
        return entity

    def get_entity(self, entity_id: str, version: Optional[str] = None) -> Optional[Entity]:
        """Get an entity by ID and optional version"""
        if entity_id not in self._entities:
            return None

        versions = self._entities[entity_id]
        if not versions:
            return None

        if version:
            # Find specific version
            for v in versions:
                if v.version == version:
                    return v
            return None
        else:
            # Return latest version
            return versions[-1]

    def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Get all entities of a specific type (latest versions only)"""
        type_key = entity_type.value if hasattr(entity_type, 'value') else str(entity_type)
        if type_key not in self._index["by_type"]:
            return []

        entities = []
        for entity_id in self._index["by_type"][type_key]:
            entity = self.get_entity(entity_id)
            if entity:
                entities.append(entity)

        return entities

    def store_relationship(self, relationship: EntityRelationship, mark_dirty: bool = True) -> EntityRelationship:
        """Store a relationship.

        Args:
            relationship: the relationship to store.
            mark_dirty: see :meth:`store_entity`. False when applying a
                server-originated relationship during sync.
        """
        is_new = not any(r.id == relationship.id for r in self._relationships)
        if is_new:
            self._relationships.append(relationship)
        else:
            self._relationships = [
                relationship if r.id == relationship.id else r
                for r in self._relationships
            ]

        # Update room index if it's a LOCATED_IN relationship
        if relationship.relationship_type == RelationshipType.LOCATED_IN:
            room_id = relationship.to_entity_id
            device_id = relationship.from_entity_id
            if room_id not in self._index["by_room"]:
                self._index["by_room"][room_id] = []
            if device_id not in self._index["by_room"][room_id]:
                self._index["by_room"][room_id].append(device_id)

        if mark_dirty and relationship.id:
            # Guarded on id: an unidentified relationship would be tracked under
            # the JSON key "null", giving a pending entry that can never be
            # pushed (the server keys on id) and never cleared (no ack ever
            # names it). Callers should assign an id; LocalGraphOperations does.
            if self._pending_relationships.get(relationship.id) != "create":
                self._pending_relationships[relationship.id] = "create" if is_new else "update"

        self._save_data()
        return relationship

    def get_relationships(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        rel_type: Optional[RelationshipType] = None
    ) -> List[EntityRelationship]:
        """Get relationships with optional filters"""
        results = []

        for rel in self._relationships:
            if from_id and rel.from_entity_id != from_id:
                continue
            if to_id and rel.to_entity_id != to_id:
                continue
            if rel_type and rel.relationship_type != rel_type:
                continue

            results.append(rel)

        return results

    # ------------------------------------------------------------------
    # Pending-change tracking (sync push)
    #
    # The sync engine reads these to build the push payload. They are backed
    # by pending.json so an offline write is still pushed after a restart.
    # ------------------------------------------------------------------

    def get_pending_entities(self) -> Dict[str, str]:
        """Return {entity_id: operation} for locally-changed, unpushed entities."""
        return dict(self._pending_entities)

    def get_pending_relationships(self) -> Dict[str, str]:
        """Return {relationship_id: operation} for locally-changed, unpushed relationships."""
        return dict(self._pending_relationships)

    def mark_entity_pending(self, entity_id: str, operation: str = "update"):
        """Explicitly queue an entity for the next push.

        For callers that mutate storage out-of-band; normal writes through
        store_entity() mark themselves.
        """
        if self._pending_entities.get(entity_id) != "create":
            self._pending_entities[entity_id] = operation
        self._save_data()

    def has_pending(self) -> bool:
        """Whether there is any local change waiting to be pushed."""
        return bool(self._pending_entities or self._pending_relationships)

    def pending_count(self) -> int:
        """Total number of local changes waiting to be pushed."""
        return len(self._pending_entities) + len(self._pending_relationships)

    def clear_pending(
        self,
        entity_ids: Optional[List[str]] = None,
        relationship_ids: Optional[List[str]] = None
    ):
        """Drop pending marks for changes the server has confirmed it applied.

        Only the ids the server acknowledged are cleared. Anything written
        while the push was in flight keeps its mark and goes out next sync.
        Passing None for both clears everything.
        """
        if entity_ids is None and relationship_ids is None:
            self._pending_entities.clear()
            self._pending_relationships.clear()
        else:
            for entity_id in entity_ids or []:
                self._pending_entities.pop(entity_id, None)
            for relationship_id in relationship_ids or []:
                self._pending_relationships.pop(relationship_id, None)

        self._save_data()

    def search_entities(self, query: str, entity_types: Optional[List[EntityType]] = None) -> List[Entity]:
        """Simple search implementation"""
        results = []
        query_lower = query.lower()

        # Special case: "*" returns all entities
        if query == "*":
            for entity_id, versions in self._entities.items():
                if not versions:
                    continue

                latest = versions[-1]

                # Filter by type if specified
                if entity_types and latest.entity_type not in entity_types:
                    continue

                results.append(latest)
        else:
            # Normal search
            for entity_id, versions in self._entities.items():
                if not versions:
                    continue

                latest = versions[-1]

                # Filter by type if specified
                if entity_types and latest.entity_type not in entity_types:
                    continue

                # Search in name
                if query_lower in latest.name.lower():
                    results.append(latest)
                    continue

                # Search in content (simple string search)
                if latest.content:
                    content_str = json.dumps(latest.content).lower()
                    if query_lower in content_str:
                        results.append(latest)

        return results

    def get_devices_in_room(self, room_id: str) -> List[Entity]:
        """Get all devices in a room using the index"""
        if room_id not in self._index["by_room"]:
            return []

        devices = []
        for device_id in self._index["by_room"][room_id]:
            device = self.get_entity(device_id)
            if device and device.entity_type == EntityType.DEVICE:
                devices.append(device)

        return devices

    def clear(self):
        """Clear all local data"""
        self._entities.clear()
        self._relationships.clear()
        self._pending_entities.clear()
        self._pending_relationships.clear()
        self._index = {
            "by_type": {},
            "by_room": {}
        }

        # Remove files
        for file in [self.entities_file, self.relationships_file, self.index_file, self.pending_file]:
            if file.exists():
                file.unlink()

    def sync_from_server(self, entities: List[Entity], relationships: List[EntityRelationship]):
        """
        Sync data from server.

        This replaces local data with server data for the given entities.
        """
        # Update entities
        for entity in entities:
            if entity.id not in self._entities:
                self._entities[entity.id] = []

            # Check if this version already exists
            existing_versions = [v.version for v in self._entities[entity.id]]
            if entity.version not in existing_versions:
                self._entities[entity.id].append(entity)
                # Sort by created_at to maintain version order
                self._entities[entity.id].sort(key=lambda e: e.created_at or datetime.min)

        # Update relationships
        # Remove old relationships for these entities
        entity_ids = {e.id for e in entities}
        self._relationships = [
            r for r in self._relationships
            if r.from_entity_id not in entity_ids and r.to_entity_id not in entity_ids
        ]

        # Add new relationships
        self._relationships.extend(relationships)

        # Rebuild index and save
        self._rebuild_index()
        self._save_data()

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the local graph."""
        # Count unique entities (latest version only)
        total_entities = len(self._entities)

        # Count relationships
        total_relationships = len(self._relationships)

        # Count by entity type
        entity_types = {}
        for entity_id, versions in self._entities.items():
            if versions:
                latest = versions[-1]  # Get latest version
                entity_type = str(latest.entity_type)
                if entity_type.startswith('EntityType.'):
                    entity_type = entity_type.replace('EntityType.', '').lower()
                entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

        # Count by relationship type
        relationship_types = {}
        for rel in self._relationships:
            rel_type = str(rel.relationship_type)
            if rel_type.startswith('RelationshipType.'):
                rel_type = rel_type.replace('RelationshipType.', '').lower()
            relationship_types[rel_type] = relationship_types.get(rel_type, 0) + 1

        # Calculate average degree
        if total_entities > 0:
            total_connections = len(set(
                [r.from_entity_id for r in self._relationships] +
                [r.to_entity_id for r in self._relationships]
            ))
            average_degree = (total_relationships * 2) / total_entities if total_entities > 0 else 0
        else:
            average_degree = 0

        # Find isolated entities
        connected_entities = set()
        for rel in self._relationships:
            connected_entities.add(rel.from_entity_id)
            connected_entities.add(rel.to_entity_id)

        isolated_entities = len(self._entities) - len(connected_entities)

        return {
            'total_entities': total_entities,
            'total_relationships': total_relationships,
            'entity_types': entity_types,
            'relationship_types': relationship_types,
            'average_degree': average_degree,
            'isolated_entities': max(0, isolated_entities)
        }
