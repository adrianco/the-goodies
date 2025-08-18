"""
Core graph operations for entities and relationships.

This module provides base functionality for graph operations that can be
implemented with different backends (SQL, in-memory, etc).
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Set, Tuple
from datetime import datetime
from uuid import uuid4

from ..models import Entity, EntityType, EntityRelationship, RelationshipType


class GraphOperations(ABC):
    """Abstract base class for graph operations"""

    @abstractmethod
    async def store_entity(self, entity: Entity) -> Entity:
        """Store an entity in the graph"""
        pass

    @abstractmethod
    async def get_entity(self, entity_id: str, version: Optional[str] = None) -> Optional[Entity]:
        """Get an entity by ID and optional version"""
        pass

    @abstractmethod
    async def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Get all entities of a specific type"""
        pass

    @abstractmethod
    async def store_relationship(self, relationship: EntityRelationship) -> EntityRelationship:
        """Store a relationship in the graph"""
        pass

    @abstractmethod
    async def get_relationships(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        rel_type: Optional[RelationshipType] = None
    ) -> List[EntityRelationship]:
        """Get relationships with optional filters"""
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
        max_depth: int = 10
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
            entity = await self.get_entity(from_id)
            return [entity] if entity else None

        # BFS implementation
        visited = {from_id}
        queue = [(from_id, [from_id])]
        depth = 0

        while queue and depth < max_depth:
            next_queue = []

            for current_id, path in queue:
                # Get all connected entities
                relationships = await self.get_relationships(from_id=current_id)

                for rel in relationships:
                    neighbor_id = rel.to_entity_id

                    if neighbor_id == to_id:
                        # Found the target
                        full_path = []
                        for entity_id in path + [neighbor_id]:
                            entity = await self.get_entity(entity_id)
                            if entity:
                                full_path.append(entity)
                        return full_path

                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
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
            rel_types: Filter by relationship types

        Returns:
            Dictionary with entities and relationships
        """
        entities = {}
        relationships = []
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

            # Get all relationships for this entity
            outgoing = await self.get_relationships(from_id=current_id, rel_type=rel_types[0] if rel_types else None)
            incoming = await self.get_relationships(to_id=current_id, rel_type=rel_types[0] if rel_types else None)

            for rel in outgoing + incoming:
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

        for entity_type in EntityType:
            entities = await self.get_entities_by_type(entity_type)
            if entities:
                entity_counts[entity_type.value] = len(entities)

        # Get all relationships and count by type
        all_relationships = await self.get_relationships()
        for rel in all_relationships:
            rel_type = rel.relationship_type.value
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
