"""
Graph traversal algorithms and utilities.

Provides various graph traversal algorithms for exploring entity relationships.
"""

from typing import List, Dict, Set, Optional, Callable, Any
from collections import deque, defaultdict
from abc import ABC, abstractmethod

from ..models import Entity, EntityRelationship, RelationshipType

# Relationship types whose edges run child -> parent, i.e. the *target* of the
# edge is the containing entity. This is the schema's own convention:
# ``EntityRelationship.is_valid_for_entities`` validates PART_OF as ROOM->HOME /
# ZONE->HOME / DEVICE->ZONE and LOCATED_IN as DEVICE->ROOM / ROOM->HOME, so an
# edge of these types points *upwards*. Every other type is stored parent ->
# child, the way CONTROLS is validated (AUTOMATION->DEVICE, DEVICE->DEVICE:
# controller -> controlled). ``get_ancestors``/``get_descendants`` consult this
# so that "ancestor" means the same thing whichever convention a type uses.
CHILD_TO_PARENT_TYPES = frozenset({
    RelationshipType.PART_OF,
    RelationshipType.LOCATED_IN,
    RelationshipType.CONTAINED_IN,
})


class GraphTraversal(ABC):
    """Abstract base class for graph traversal operations"""

    @abstractmethod
    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID"""
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

    async def bfs(
        self,
        start_id: str,
        visit_fn: Optional[Callable[[Entity, int], bool]] = None,
        max_depth: Optional[int] = None,
        rel_types: Optional[List[RelationshipType]] = None
    ) -> List[Entity]:
        """
        Breadth-first search traversal.

        Args:
            start_id: Starting entity ID
            visit_fn: Optional function to call for each entity (return False to stop)
            max_depth: Maximum depth to traverse
            rel_types: Filter by relationship types

        Returns:
            List of visited entities in BFS order
        """
        visited = set()
        visited_entities = []
        queue = deque([(start_id, 0)])

        while queue:
            entity_id, depth = queue.popleft()

            if entity_id in visited:
                continue

            if max_depth is not None and depth > max_depth:
                continue

            visited.add(entity_id)

            # Get the entity
            entity = await self.get_entity(entity_id)
            if not entity:
                continue

            visited_entities.append(entity)

            # Call visit function if provided
            if visit_fn and not visit_fn(entity, depth):
                break

            # Get connected entities
            relationships = await self.get_relationships(from_id=entity_id)

            for rel in relationships:
                if rel_types and rel.relationship_type not in rel_types:
                    continue

                if rel.to_entity_id not in visited:
                    queue.append((rel.to_entity_id, depth + 1))

        return visited_entities

    async def dfs(
        self,
        start_id: str,
        visit_fn: Optional[Callable[[Entity, int], bool]] = None,
        max_depth: Optional[int] = None,
        rel_types: Optional[List[RelationshipType]] = None
    ) -> List[Entity]:
        """
        Depth-first search traversal.

        Args:
            start_id: Starting entity ID
            visit_fn: Optional function to call for each entity (return False to stop)
            max_depth: Maximum depth to traverse
            rel_types: Filter by relationship types

        Returns:
            List of visited entities in DFS order
        """
        visited = set()
        visited_entities = []

        async def dfs_helper(entity_id: str, depth: int) -> bool:
            if entity_id in visited:
                return True

            if max_depth is not None and depth > max_depth:
                return True

            visited.add(entity_id)

            # Get the entity
            entity = await self.get_entity(entity_id)
            if not entity:
                return True

            visited_entities.append(entity)

            # Call visit function if provided
            if visit_fn and not visit_fn(entity, depth):
                return False

            # Get connected entities
            relationships = await self.get_relationships(from_id=entity_id)

            for rel in relationships:
                if rel_types and rel.relationship_type not in rel_types:
                    continue

                if not await dfs_helper(rel.to_entity_id, depth + 1):
                    return False

            return True

        await dfs_helper(start_id, 0)
        return visited_entities

    async def find_all_paths(
        self,
        start_id: str,
        end_id: str,
        max_length: int = 5,
        rel_types: Optional[List[RelationshipType]] = None
    ) -> List[List[str]]:
        """
        Find all paths between two entities.

        Args:
            start_id: Starting entity ID
            end_id: Target entity ID
            max_length: Maximum path length
            rel_types: Filter by relationship types

        Returns:
            List of paths (each path is a list of entity IDs)
        """
        all_paths = []

        async def dfs_paths(current_id: str, path: List[str]):
            if len(path) > max_length:
                return

            if current_id == end_id:
                all_paths.append(path.copy())
                return

            # Get connected entities
            relationships = await self.get_relationships(from_id=current_id)

            for rel in relationships:
                if rel_types and rel.relationship_type not in rel_types:
                    continue

                if rel.to_entity_id not in path:  # Avoid cycles
                    path.append(rel.to_entity_id)
                    await dfs_paths(rel.to_entity_id, path)
                    path.pop()

        await dfs_paths(start_id, [start_id])
        return all_paths

    async def _hierarchy_step(
        self,
        entity_id: str,
        rel_type: RelationshipType,
        upwards: bool
    ) -> List[str]:
        """
        Take one hierarchy hop away from an entity.

        Which way round the edge is stored depends on the relationship type
        (see CHILD_TO_PARENT_TYPES), so "upwards" is not the same as "incoming".

        Args:
            entity_id: Entity to step away from
            rel_type: Relationship type defining the hierarchy
            upwards: True for the level above, False for the level below

        Returns:
            IDs of the entities one level above or below this one
        """
        # An upward edge type is followed forwards to reach a parent, a
        # downward one backwards; and vice versa for children.
        if (rel_type in CHILD_TO_PARENT_TYPES) == upwards:
            relationships = await self.get_relationships(from_id=entity_id, rel_type=rel_type)
            return [rel.to_entity_id for rel in relationships]

        relationships = await self.get_relationships(to_id=entity_id, rel_type=rel_type)
        return [rel.from_entity_id for rel in relationships]

    async def _walk_hierarchy(
        self,
        entity_id: str,
        rel_type: RelationshipType,
        upwards: bool,
        max_depth: Optional[int] = None
    ) -> List[Entity]:
        """
        Walk a single-relationship-type hierarchy breadth-first.

        The starting entity is never included and no entity is reported twice,
        so cyclic data terminates. ``max_depth`` counts hops, as in ``bfs``:
        None is unbounded, 1 is the immediately adjacent level, 0 is nothing.

        Args:
            entity_id: Starting entity ID
            rel_type: Relationship type defining the hierarchy
            upwards: True to walk towards ancestors, False towards descendants
            max_depth: Maximum number of hops to take

        Returns:
            List of entities in breadth-first order, nearest level first
        """
        found = []
        visited = {entity_id}
        queue = deque([(entity_id, 0)])

        while queue:
            current_id, depth = queue.popleft()

            if max_depth is not None and depth >= max_depth:
                continue

            for next_id in await self._hierarchy_step(current_id, rel_type, upwards):
                if next_id in visited:
                    continue

                visited.add(next_id)

                entity = await self.get_entity(next_id)
                if not entity:
                    continue

                found.append(entity)
                queue.append((next_id, depth + 1))

        return found

    async def get_ancestors(
        self,
        entity_id: str,
        rel_type: RelationshipType,
        max_depth: Optional[int] = None
    ) -> List[Entity]:
        """
        Get all ancestors of an entity following a specific relationship type.

        An ancestor is an entity above this one in the hierarchy that rel_type
        describes. The edge direction that means "above" is the schema's, not a
        fixed one: for PART_OF and the other CHILD_TO_PARENT_TYPES the walk
        follows outgoing edges (a DEVICE is PART_OF a ZONE is PART_OF a HOME, so
        the ancestors of the device are the zone then the home); for every other
        type it follows incoming ones (a DEVICE that CONTROLS another is the
        controlled device's ancestor).

        The entity itself is never an ancestor of itself, and this is the exact
        inverse of ``get_descendants``: ``b`` is in ``get_ancestors(a)`` if and
        only if ``a`` is in ``get_descendants(b)``.

        Args:
            entity_id: Starting entity ID
            rel_type: Relationship type to follow (e.g., PART_OF)
            max_depth: Maximum number of levels to climb (None for all, 1 for
                immediate parents only)

        Returns:
            List of ancestor entities, closest generation first
        """
        return await self._walk_hierarchy(entity_id, rel_type, upwards=True, max_depth=max_depth)

    async def get_descendants(
        self,
        entity_id: str,
        rel_type: RelationshipType,
        max_depth: Optional[int] = None
    ) -> List[Entity]:
        """
        Get all descendants of an entity following a specific relationship type.

        A descendant is an entity below this one in the hierarchy that rel_type
        describes -- the exact inverse of ``get_ancestors``, walking the same
        edges the other way. As there, the direction that means "below" comes
        from the schema: the descendants of a HOME under PART_OF are the rooms
        and zones whose edges point *at* it.

        The entity itself is not one of its own descendants.

        Args:
            entity_id: Starting entity ID
            rel_type: Relationship type to follow
            max_depth: Maximum number of levels to descend (None for all, 1 for
                immediate children only)

        Returns:
            List of descendant entities, closest generation first
        """
        return await self._walk_hierarchy(entity_id, rel_type, upwards=False, max_depth=max_depth)

    async def detect_cycles(
        self,
        start_id: Optional[str] = None,
        rel_types: Optional[List[RelationshipType]] = None
    ) -> List[List[str]]:
        """
        Detect cycles in the graph.

        Args:
            start_id: Optional starting point. If None the entire graph is
                checked, including components no single entity reaches.
            rel_types: Filter by relationship types

        Returns:
            List of cycles (each cycle is a list of entity IDs, closed: the
            entity the cycle returns to is repeated at the end)
        """
        cycles = []
        visited = set()
        rec_stack = set()
        path = []

        async def dfs_cycle(entity_id: str) -> bool:
            visited.add(entity_id)
            rec_stack.add(entity_id)
            path.append(entity_id)

            # Get outgoing relationships
            relationships = await self.get_relationships(from_id=entity_id)

            for rel in relationships:
                if rel_types and rel.relationship_type not in rel_types:
                    continue

                if rel.to_entity_id not in visited:
                    if await dfs_cycle(rel.to_entity_id):
                        return True
                elif rel.to_entity_id in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(rel.to_entity_id)
                    cycles.append(path[cycle_start:] + [rel.to_entity_id])

            path.pop()
            rec_stack.remove(entity_id)
            return False

        if start_id:
            await dfs_cycle(start_id)
        else:
            # Check the entire graph. An entity with no outgoing edge cannot be
            # part of a cycle, so the sources of the (unfiltered) relationship
            # list are a complete set of roots -- no need for a list-all-entities
            # primitive the interface does not have.
            for rel in await self.get_relationships():
                if rel_types and rel.relationship_type not in rel_types:
                    continue

                if rel.from_entity_id not in visited:
                    await dfs_cycle(rel.from_entity_id)

        return cycles

    async def calculate_centrality(
        self,
        entity_id: str,
        metric: str = "degree"
    ) -> float:
        """
        Calculate centrality metric for an entity.

        Args:
            entity_id: Entity to calculate centrality for
            metric: Type of centrality ("degree", "closeness", "betweenness")

        Returns:
            Centrality score
        """
        if metric == "degree":
            # Simple degree centrality
            outgoing = await self.get_relationships(from_id=entity_id)
            incoming = await self.get_relationships(to_id=entity_id)
            return len(outgoing) + len(incoming)

        # Other metrics would require more complex calculations
        # and access to the full graph
        return 0.0
