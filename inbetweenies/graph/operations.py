"""
Core graph operations for entities and relationships.

This module provides base functionality for graph operations that can be
implemented with different backends (SQL, in-memory, etc).
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..models import Entity, EntityType, EntityRelationship, RelationshipType


class GraphOperations(ABC):
    """Abstract base class for graph operations"""

    @abstractmethod
    async def store_entity(self, entity: Entity) -> Entity:
        """Store an entity in the graph"""
        pass

    @abstractmethod
    async def get_entity(self, entity_id: str, version: Optional[str] = None,
                         at: Optional[datetime] = None) -> Optional[Entity]:
        """Get an entity by ID: a specific version, the state at ``at``, or current.

        ADR-004 §3.2: with ``at`` set, the accepted version with the greatest
        valid time <= ``at`` -- and None if the entity did not yet exist, or
        was tombstoned, at that instant. Version strings sort lexically by
        their UTC prefix (PROTOCOL.md §2), which is what makes this a range
        comparison rather than a parse. ``version`` and ``at`` are exclusive.
        """
        pass

    @abstractmethod
    async def get_entities_by_type(self, entity_type: EntityType,
                                   include_deleted: bool = False) -> List[Entity]:
        """Get all entities of a specific type"""
        pass

    async def store_blob(
        self,
        *,
        blob_id: str,
        name: str,
        blob_type: str,
        mime_type: str,
        data: bytes,
        user_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> str:
        """Persist blob bytes and return the blob id.

        Not abstract, and the default raises: a backend that cannot store bytes
        should say so loudly at the point of use rather than silently accepting
        an attachment whose data goes nowhere. Silence is how base64 ended up
        inlined in entity content in the first place (ADR-013 §3) -- there was
        no first-class place to put it and nothing said so.

        Implementations must be idempotent on ``blob_id``: attaching the same
        file twice is a retry, not two blobs.
        """
        raise NotImplementedError(
            f"{type(self).__name__} cannot store blobs; attachments are unavailable "
            "on this backend"
        )

    async def get_blob(self, blob_id: str, include_data: bool = False) -> Optional[Dict[str, Any]]:
        """Fetch blob metadata, and the bytes only when asked.

        Blobs are large -- one install is 86% blob by bytes -- so returning
        data by default would make every metadata read expensive.
        """
        raise NotImplementedError(
            f"{type(self).__name__} cannot read blobs; attachments are unavailable "
            "on this backend"
        )

    @abstractmethod
    async def store_relationship(self, relationship: EntityRelationship) -> EntityRelationship:
        """Store a relationship in the graph"""
        pass

    @abstractmethod
    async def get_relationships(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        rel_type: Optional[RelationshipType] = None,
        include_all_versions: bool = False,
        at: Optional[datetime] = None
    ) -> List[EntityRelationship]:
        """Get relationships with optional filters.

        ADR-004 §1/§3: edges are interval rows, so "which edges?" needs a stance
        on time. ``at`` picks the instant (omitted = now): an edge is included
        iff ``valid_from <= at < coalesce(valid_to, ∞)``. ``include_all_versions``
        returns every interval regardless — history, not state; the sync push
        path needs it and ordinary reads must not. Part of the abstract
        signature so every backend — SQL, in-memory, client cache — answers the
        same question, which is what lets the conformance suite hold them to
        one contract.
        """
        pass

    @abstractmethod
    async def end_relationship(
        self, relationship_id: str, at: Optional[datetime] = None
    ) -> Optional[EntityRelationship]:
        """End an edge's open interval at ``at`` (default now) — ADR-004 §1.

        This is the delete/move primitive. Ending is not deleting: the row is
        kept and every question about the period it covered still answers.
        Returns the ended row, or None if the edge has no open interval (already
        ended, or never existed) — callers treat that as idempotent success.
        """
        pass

    async def update_entity(self, entity_id: str, changes: Dict[str, Any], user_id: str) -> Entity:
        """
        Update an entity by creating a new version.

        Args:
            entity_id: ID of entity to update
            changes: Dictionary of changes to apply
            user_id: User making the change

        Returns:
            New version of the entity
        """
        # Get current entity
        current = await self.get_entity(entity_id)
        if not current:
            raise ValueError(f"Entity {entity_id} not found")

        # Create new version
        new_entity = current.create_new_version(user_id, changes)

        # Store new version
        return await self.store_entity(new_entity)

    async def find_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int = 10,
        at: Optional[datetime] = None
    ) -> Optional[List[Entity]]:
        """
        Find shortest path between two entities using BFS.

        Args:
            from_id: Starting entity ID
            to_id: Target entity ID
            max_depth: Maximum search depth

        Returns:
            List of entities forming the path, or None if no path exists
        """
        if from_id == to_id:
            entity = await self.get_entity(from_id, at=at)
            return [entity] if entity else None

        # BFS implementation
        visited = {from_id}
        queue = [(from_id, [from_id])]
        depth = 0

        while queue and depth < max_depth:
            next_queue = []

            for current_id, path in queue:
                # Get all connected entities
                relationships = await self.get_relationships(from_id=current_id, at=at)

                for rel in relationships:
                    neighbor_id = rel.to_entity_id
                    if neighbor_id in visited:
                        continue
                    visited.add(neighbor_id)

                    # A tombstoned endpoint is not part of the graph even though
                    # the edge row that reaches it may still be open.
                    neighbor = await self.get_entity(neighbor_id, at=at)
                    if neighbor is None or getattr(neighbor, "is_tombstone", False):
                        continue

                    if neighbor_id == to_id:
                        # Found the target
                        full_path = []
                        for entity_id in path + [neighbor_id]:
                            entity = await self.get_entity(entity_id, at=at)
                            if entity:
                                full_path.append(entity)
                        return full_path

                    next_queue.append((neighbor_id, path + [neighbor_id]))

            queue = next_queue
            depth += 1

        return None

    async def get_subgraph(
        self,
        entity_id: str,
        depth: int = 1,
        rel_types: Optional[List[RelationshipType]] = None
    ) -> Dict[str, Any]:
        """
        Get subgraph around an entity up to specified depth.

        Args:
            entity_id: Center entity ID
            depth: How many hops to include
            rel_types: Filter by relationship types (all of them, not just the
                first)

        Returns:
            Dictionary with entities and relationships. Each relationship
            appears exactly once even though it is reachable from both of its
            endpoints.
        """
        entities = {}
        relationships = []
        seen_relationships = set()
        visited = set()

        # Start with center entity
        center = await self.get_entity(entity_id)
        if not center:
            return {"entities": {}, "relationships": []}

        entities[entity_id] = center
        to_visit = [(entity_id, 0)]

        while to_visit:
            current_id, current_depth = to_visit.pop(0)

            if current_depth >= depth:
                continue

            if current_id in visited:
                continue

            visited.add(current_id)

            # Get all relationships for this entity. The primitive filters one
            # type at a time, so ask once per requested type; no filter at all
            # when the caller did not name any.
            edges = []
            for rel_type in (rel_types if rel_types else [None]):
                edges.extend(await self.get_relationships(from_id=current_id, rel_type=rel_type))
                edges.extend(await self.get_relationships(to_id=current_id, rel_type=rel_type))

            for rel in edges:
                # An edge whose endpoints are both expanded is seen twice (once
                # outgoing, once incoming), and a self-loop twice from the same
                # entity; report it once.
                if rel.id not in seen_relationships:
                    seen_relationships.add(rel.id)
                    relationships.append(rel)

                # Add connected entities to visit
                if rel.from_entity_id == current_id:
                    other_id = rel.to_entity_id
                else:
                    other_id = rel.from_entity_id

                if other_id not in entities:
                    other = await self.get_entity(other_id)
                    if other:
                        entities[other_id] = other
                        to_visit.append((other_id, current_depth + 1))

        return {
            "entities": entities,
            "relationships": relationships
        }

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get graph statistics.

        Returns:
            Dictionary with various statistics
        """
        # Get entity counts by type
        entity_counts = {}
        relationship_counts = {}

        # ADR-012 §1: the vocabulary is the domain's. A store that knows its
        # manifest counts what that domain declares; the legacy enum is only
        # the fallback for a bare GraphOperations with no domain attached.
        domain = getattr(self, "domain", None)
        entity_types = sorted(domain.entity_types) if domain is not None else [t.value for t in EntityType]
        for entity_type in entity_types:
            entities = await self.get_entities_by_type(entity_type)
            if entities:
                entity_counts[entity_type] = len(entities)

        # Get all relationships and count by type
        all_relationships = await self.get_relationships()
        for rel in all_relationships:
            rel_type = getattr(rel.relationship_type, "value", rel.relationship_type)
            relationship_counts[rel_type] = relationship_counts.get(rel_type, 0) + 1

        # Calculate average degree
        total_entities = sum(entity_counts.values())
        total_relationships = len(all_relationships)
        avg_degree = (2 * total_relationships / total_entities) if total_entities > 0 else 0

        # Find isolated entities
        connected_entities = set()
        for rel in all_relationships:
            connected_entities.add(rel.from_entity_id)
            connected_entities.add(rel.to_entity_id)

        isolated_count = total_entities - len(connected_entities)

        return {
            "total_entities": total_entities,
            "total_relationships": total_relationships,
            "entity_types": entity_counts,
            "relationship_types": relationship_counts,
            "average_degree": round(avg_degree, 2),
            "isolated_entities": isolated_count
        }
