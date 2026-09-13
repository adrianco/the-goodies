"""
Local implementation of graph operations for the Blowing-Off client.

This module provides the concrete implementation of graph operations
that work with local storage instead of a database.
"""

from typing import List, Optional, Any, Dict
from dataclasses import dataclass
import uuid
from datetime import datetime, UTC

from inbetweenies.mcp import MCPTools, ToolResult
from inbetweenies.models import Entity, EntityType, EntityRelationship

from .local_storage import LocalGraphStorage


@dataclass
class SearchResult:
    """Simple search result for local implementation"""
    entity: Entity
    score: float = 1.0

    def to_dict(self):
        # Properly convert entity to dict, handling SQLAlchemy objects
        if hasattr(self.entity, 'to_dict'):
            # Use the entity's to_dict method if available
            entity_dict = self.entity.to_dict()
        elif hasattr(self.entity, '__dict__'):
            # Manually convert from attributes
            entity_dict = {}
            for key, value in self.entity.__dict__.items():
                if not key.startswith('_'):
                    # Convert enums to strings
                    if hasattr(value, 'value'):
                        entity_dict[key] = value.value
                    elif isinstance(value, datetime):
                        entity_dict[key] = value.isoformat()
                    elif value is None:
                        entity_dict[key] = None
                    else:
                        entity_dict[key] = value
        else:
            # Fallback to string representation
            entity_dict = str(self.entity)

        # Ensure required fields exist
        if isinstance(entity_dict, dict):
            # Ensure these fields are present even if None
            entity_dict.setdefault('id', None)
            entity_dict.setdefault('name', None)
            entity_dict.setdefault('entity_type', 'unknown')
            entity_dict.setdefault('updated_at', None)
            entity_dict.setdefault('created_at', None)

        return {
            "entity": entity_dict,
            "score": self.score
        }


class LocalGraphOperations(MCPTools):
    """
    Local implementation of graph operations.

    This class provides all the functionality needed for MCP tools
    and graph operations using local storage.
    """

    def __init__(self, storage: Optional[LocalGraphStorage] = None):
        """Initialize with local storage"""
        self.storage = storage or LocalGraphStorage()

    # Inherited MCP tool methods from MCPTools
    async def store_entity(self, entity: Entity, mark_dirty: bool = True) -> Entity:
        """Store an entity locally.

        Args:
            entity: the entity version to store.
            mark_dirty: whether to queue this version for the next sync push.
                The sync engine passes False when applying a server change.
        """
        import uuid
        # Generate ID if not set
        if not entity.id:
            entity.id = str(uuid.uuid4())
        # Set user_id if not set
        if not entity.user_id:
            entity.user_id = "local-user"
        # Generate version if not set
        if not entity.version:
            entity.version = Entity.create_version(entity.user_id)
        # Ensure parent_versions is a list
        if not hasattr(entity, 'parent_versions') or entity.parent_versions is None:
            entity.parent_versions = []
        return self.storage.store_entity(entity, mark_dirty=mark_dirty)

    async def get_entity(self, entity_id: str, version: Optional[str] = None,
                         at: Optional[datetime] = None) -> Optional[Entity]:
        """Get an entity from local storage (a version, the state as of ``at``, or latest)."""
        return self.storage.get_entity(entity_id, version, at=at)

    async def end_relationship(
        self, relationship_id: str, at: Optional[datetime] = None
    ) -> Optional[EntityRelationship]:
        """End an edge locally (ADR-004 §1); pushed as an end-event on the next sync."""
        return self.storage.end_relationship(relationship_id, at, mark_dirty=True)

    async def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Get all entities of a specific type"""
        return self.storage.get_entities_by_type(entity_type)

    async def store_relationship(
        self,
        relationship: EntityRelationship,
        mark_dirty: bool = True
    ) -> EntityRelationship:
        """Store a relationship locally.

        Args:
            relationship: the relationship to store.
            mark_dirty: see :meth:`store_entity`.
        """
        import uuid
        # Mirror store_entity: an id is generated rather than assumed. Without
        # this a relationship saved with id=None was tracked under the JSON key
        # "null", producing a pending entry that could never be pushed and never
        # cleared -- it just accumulated on every sync.
        if not relationship.id:
            relationship.id = str(uuid.uuid4())
        if not relationship.user_id:
            relationship.user_id = "local-user"
        return self.storage.store_relationship(relationship, mark_dirty=mark_dirty)

    def get_pending_entities(self) -> dict:
        """Return {entity_id: operation} for locally-changed, unpushed entities."""
        return self.storage.get_pending_entities()

    def batch_writes(self):
        """Apply many rows with ONE store rewrite (see LocalGraphStorage).

        Exposed here rather than letting callers reach through to `.storage`:
        the sync engine talks to this object, and a caller that has to know the
        storage layout to batch its writes has been handed the wrong seam.
        """
        return self.storage.batch_writes()

    def get_pending_relationships(self) -> dict:
        """Return {relationship_id: operation} for locally-changed, unpushed relationships."""
        return self.storage.get_pending_relationships()

    def pending_count(self) -> int:
        """Total number of local changes waiting to be pushed."""
        return self.storage.pending_count()

    def clear_pending(self, entity_ids=None, relationship_ids=None):
        """Drop pending marks for changes the server confirmed it applied."""
        self.storage.clear_pending(entity_ids, relationship_ids)

    async def get_relationships(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        rel_type: Optional[str] = None,
        include_all_versions: bool = False,
        at: Optional[datetime] = None
    ) -> List[EntityRelationship]:
        """Get relationships with optional filters.

        ADR-004 §1/§3: current edges by default, the state as of ``at`` when
        given; ``include_all_versions=True`` adds retired intervals, which the
        sync push path needs and ordinary graph reads must not see.
        """
        return self.storage.get_relationships(
            from_id, to_id, rel_type, include_all_versions=include_all_versions, at=at
        )

    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """Search entities locally"""
        entities = self.storage.search_entities(query, entity_types)

        # Convert to SearchResult and limit
        results = []
        for entity in entities[:limit]:
            # Simple scoring based on name match
            score = 1.0
            if query.lower() == entity.name.lower():
                score = 2.0
            elif query.lower() in entity.name.lower():
                score = 1.5

            results.append(SearchResult(entity=entity, score=score))

        # Sort by score
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    async def get_entity_versions(self, entity_id: str) -> List[Entity]:
        """Get all versions of an entity"""
        if entity_id in self.storage._entities:
            return self.storage._entities[entity_id]
        return []

    async def find_path(self, from_id: str, to_id: str, max_depth: int = 10) -> List[Entity]:
        """
        Find path between entities using BFS.

        This is a simple implementation for local use.
        """
        from collections import deque

        # Check if entities exist
        start = await self.get_entity(from_id)
        end = await self.get_entity(to_id)

        if not start or not end:
            return []

        # BFS to find path
        queue = deque([(from_id, [start])])
        visited = {from_id}

        while queue and len(visited) < 1000:  # Limit to prevent infinite loops
            current_id, path = queue.popleft()

            if len(path) > max_depth:
                continue

            if current_id == to_id:
                return path

            # Get all relationships from current entity
            relationships = await self.get_relationships(from_id=current_id)

            for rel in relationships:
                next_id = rel.to_entity_id
                if next_id not in visited:
                    visited.add(next_id)
                    next_entity = await self.get_entity(next_id)
                    if next_entity:
                        queue.append((next_id, path + [next_entity]))

        return []

    async def search_entities_tool(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> ToolResult:
        """Full-text search across entities (MCP tool)"""
        try:
            # ADR-012 §1: the manifest says what is a type; unknown ones are
            # skipped rather than guessed at.
            type_filter = None
            if entity_types:
                type_filter = [et for et in entity_types if et in self.domain.entity_types]

            # Use the search functionality
            results = await self.search_entities(query, type_filter, limit)

            # Convert results to dict format
            return ToolResult(True, {
                "results": [r.to_dict() for r in results],
                "count": len(results),
                "query": query
            })
        except Exception as e:
            return ToolResult(False, None, str(e))

    async def create_entity_tool(
        self,
        entity_type: str,
        name: str,
        content: Optional[Dict[str, Any]] = None,
        user_id: str = "system"
    ) -> ToolResult:
        """Create a new entity (MCP tool)"""
        try:
            self.domain.check_entity_type(entity_type)

            # Create entity
            entity = Entity(
                id=str(uuid.uuid4()),
                entity_type=entity_type,
                name=name,
                content=content or {},
                version=f"{datetime.now(UTC).isoformat()}Z-{user_id}",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                user_id=user_id,
                            )

            # Store it
            stored = await self.store_entity(entity)

            return ToolResult(True, {
                "entity": stored.to_dict() if hasattr(stored, 'to_dict') else stored.__dict__
            })
        except Exception as e:
            return ToolResult(False, None, str(e))

    async def create_relationship_tool(
        self,
        from_entity_id: str,
        to_entity_id: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None,
        user_id: str = "system"
    ) -> ToolResult:
        """Create a relationship between entities (MCP tool)"""
        try:
            self.domain.check_relationship_type(relationship_type)

            # Create relationship
            relationship = EntityRelationship(
                id=str(uuid.uuid4()),
                from_entity_id=from_entity_id,
                to_entity_id=to_entity_id,
                relationship_type=relationship_type,
                properties=properties or {},
                created_at=datetime.now(UTC),
                user_id=user_id
            )

            # Store it
            stored = await self.store_relationship(relationship)

            return ToolResult(True, {
                "relationship": stored.__dict__ if hasattr(stored, '__dict__') else str(stored)
            })
        except Exception as e:
            return ToolResult(False, None, str(e))

    async def find_path_tool(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 10
    ) -> ToolResult:
        """Find path between entities (MCP tool)"""
        try:
            path = await self.find_path(from_entity_id, to_entity_id, max_depth)

            return ToolResult(True, {
                "path": [e.to_dict() if hasattr(e, 'to_dict') else e.__dict__ for e in path],
                "length": len(path) - 1 if path else 0,
                "found": bool(path)
            })
        except Exception as e:
            return ToolResult(False, None, str(e))

    async def get_entity_details_tool(self, entity_id: str) -> ToolResult:
        """Get detailed entity information (MCP tool)"""
        try:
            entity = await self.get_entity(entity_id)
            if not entity:
                return ToolResult(False, None, f"Entity {entity_id} not found")

            # Get relationships
            from_rels = await self.get_relationships(from_id=entity_id)
            to_rels = await self.get_relationships(to_id=entity_id)

            return ToolResult(True, {
                "entity": entity.to_dict() if hasattr(entity, 'to_dict') else entity.__dict__,
                "outgoing_relationships": len(from_rels),
                "incoming_relationships": len(to_rels),
                "total_connections": len(from_rels) + len(to_rels)
            })
        except Exception as e:
            return ToolResult(False, None, str(e))

    async def find_similar_entities_tool(
        self,
        entity_id: str,
        threshold: float = 0.5,
        limit: int = 5
    ) -> ToolResult:
        """Find similar entities (MCP tool)"""
        try:
            similar = await self.find_similar_entities(entity_id, limit)

            return ToolResult(True, {
                "results": [s.to_dict() for s in similar],
                "count": len(similar),
                "reference_entity_id": entity_id
            })
        except Exception as e:
            return ToolResult(False, None, str(e))

    async def update_entity_tool(
        self,
        entity_id: str,
        changes: Dict[str, Any],
        user_id: str = "system"
    ) -> ToolResult:
        """Update an entity (creates new version) (MCP tool)"""
        try:
            # Get current entity
            current = await self.get_entity(entity_id)
            if not current:
                return ToolResult(False, None, f"Entity {entity_id} not found")

            # Create new version
            updated = Entity(
                id=entity_id,
                entity_type=current.entity_type,
                name=changes.get('name', current.name),
                content=changes.get('content', current.content),
                version=f"{datetime.now(UTC).isoformat()}Z-{user_id}",
                parent_versions=[current.version] if current.version else [],
                created_at=current.created_at,
                updated_at=datetime.now(UTC),
                user_id=current.user_id if hasattr(current, 'user_id') else user_id
                            )

            # Store new version
            stored = await self.store_entity(updated)

            return ToolResult(True, {
                "entity": stored.to_dict() if hasattr(stored, 'to_dict') else stored.__dict__,
                "previous_version": current.version,
                "new_version": stored.version
            })
        except Exception as e:
            return ToolResult(False, None, str(e))

    async def find_similar_entities(self, entity_id: str, limit: int = 5) -> List[SearchResult]:
        """Find similar entities based on type and properties"""
        reference = await self.get_entity(entity_id)
        if not reference:
            return []

        # Get entities of the same type
        similar = await self.get_entities_by_type(reference.entity_type)

        # Filter out the reference entity and score by name similarity
        results = []
        for entity in similar:
            if entity.id == entity_id:
                continue

            # Simple similarity scoring
            score = 0.5  # Base score for same type

            # Name similarity
            ref_words = set(reference.name.lower().split())
            ent_words = set(entity.name.lower().split())
            common_words = ref_words & ent_words
            if common_words:
                score += len(common_words) / max(len(ref_words), len(ent_words))

            results.append(SearchResult(entity=entity, score=score))

        # Sort by score and limit
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def update_entity(self, entity_id: str, changes: dict, user_id: str) -> Entity:
        """Update entity by creating new version"""
        current = await self.get_entity(entity_id)
        if not current:
            raise ValueError(f"Entity {entity_id} not found")

        # Create new version
        new_entity = current.create_new_version(user_id, changes)

        # Store new version
        return await self.store_entity(new_entity)

    def filter_and_rank_results(self, entities: List[Entity], query: str, limit: int) -> List[SearchResult]:
        """Helper method to convert entities to search results"""
        results = []
        query_lower = query.lower()

        for entity in entities:
            # Simple scoring
            score = 0.5
            if query_lower == entity.name.lower():
                score = 2.0
            elif query_lower in entity.name.lower():
                score = 1.0

            results.append(SearchResult(entity=entity, score=score))

        # Sort and limit
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
