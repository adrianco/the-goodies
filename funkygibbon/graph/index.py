"""
In-Memory Graph Index for Fast Traversal

This module provides an in-memory graph structure for efficient
path finding, traversal, and relationship queries.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from collections import deque, defaultdict
from dataclasses import dataclass

from ..models import Entity, EntityRelationship, RelationshipType
from ..repositories.graph import GraphRepository


@dataclass
class GraphNode:
    """Node in the graph with entity data and connections"""
    entity: Entity
    outgoing: List[Tuple[EntityRelationship, str]]  # (relationship, target_id)
    incoming: List[Tuple[EntityRelationship, str]]  # (relationship, source_id)


class GraphIndex:
    """In-memory graph structure for fast operations"""

    def __init__(self):
        # Core data structures
        self.entities: Dict[str, Entity] = {}
        self.nodes: Dict[str, GraphNode] = {}
        self.relationships_by_source: Dict[str, List[EntityRelationship]] = defaultdict(list)
        self.relationships_by_target: Dict[str, List[EntityRelationship]] = defaultdict(list)
        self.relationships_by_type: Dict[RelationshipType, List[EntityRelationship]] = defaultdict(list)

        # Indices for fast lookup
        self.entities_by_type: Dict[str, Set[str]] = defaultdict(set)
        self.entities_by_name: Dict[str, Set[str]] = defaultdict(set)

    async def load_from_storage(self, graph_repo: GraphRepository):
        """
        Load graph data from persistent storage into memory.

        Args:
            graph_repo: Repository to load data from
        """
        # Clear existing data
        self.clear()

        # Load all entity types
        from ..models import EntityType
        for entity_type in EntityType:
            entities = await graph_repo.get_entities_by_type(entity_type)
            for entity in entities:
                self._add_entity(entity)

        # Load all relationships
        relationships = await graph_repo.get_relationships(include_all_versions=False)
        for rel in relationships:
            self._add_relationship(rel)

        # Build graph nodes
        self._build_nodes()

    def clear(self):
        """Clear all graph data"""
        self.entities.clear()
        self.nodes.clear()
        self.relationships_by_source.clear()
        self.relationships_by_target.clear()
        self.relationships_by_type.clear()
        self.entities_by_type.clear()
        self.entities_by_name.clear()

    def _add_entity(self, entity: Entity):
        """Add entity to indices"""
        self.entities[entity.id] = entity
        self.entities_by_type[entity.entity_type.value].add(entity.id)

        # Index by name (case-insensitive)
        name_lower = entity.name.lower()
        self.entities_by_name[name_lower].add(entity.id)

    def _add_relationship(self, rel: EntityRelationship):
        """Add relationship to indices"""
        self.relationships_by_source[rel.from_entity_id].append(rel)
        self.relationships_by_target[rel.to_entity_id].append(rel)
        self.relationships_by_type[rel.relationship_type].append(rel)

    def _build_nodes(self):
        """Build graph nodes with connections"""
        for entity_id, entity in self.entities.items():
            outgoing = [
                (rel, rel.to_entity_id)
                for rel in self.relationships_by_source.get(entity_id, [])
            ]
            incoming = [
                (rel, rel.from_entity_id)
                for rel in self.relationships_by_target.get(entity_id, [])
            ]

            self.nodes[entity_id] = GraphNode(
                entity=entity,
                outgoing=outgoing,
                incoming=incoming
            )

    def find_path(self, from_id: str, to_id: str, max_depth: int = 10) -> List[str]:
        """
        Find shortest path between two entities using BFS.

        Args:
            from_id: Source entity ID
            to_id: Target entity ID
            max_depth: Maximum search depth

        Returns:
            List of entity IDs forming the path, empty if no path exists
        """
        if from_id not in self.nodes or to_id not in self.nodes:
            return []

        if from_id == to_id:
            return [from_id]

        # BFS
        queue = deque([(from_id, [from_id])])
        visited = {from_id}
        depth = 0

        while queue and depth < max_depth:
            level_size = len(queue)

            for _ in range(level_size):
                current, path = queue.popleft()

                # Check all outgoing connections
                node = self.nodes.get(current)
                if node:
                    for rel, next_id in node.outgoing:
                        if next_id == to_id:
                            return path + [to_id]

                        if next_id not in visited and next_id in self.nodes:
                            visited.add(next_id)
                            queue.append((next_id, path + [next_id]))

            depth += 1

        return []

    def get_connected_entities(
        self,
        entity_id: str,
        rel_type: Optional[RelationshipType] = None,
        direction: str = "both",
        max_depth: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get entities connected to the given entity.

        Args:
            entity_id: Center entity ID
            rel_type: Filter by relationship type
            direction: "outgoing", "incoming", or "both"
            max_depth: How many hops to traverse

        Returns:
            List of dictionaries with entity and relationship info
        """
        if entity_id not in self.nodes:
            return []

        results = []
        visited = {entity_id}
        queue = deque([(entity_id, 0)])

        while queue:
            current_id, depth = queue.popleft()

            if depth >= max_depth:
                continue

            node = self.nodes.get(current_id)
            if not node:
                continue

            # Process outgoing relationships
            if direction in ("outgoing", "both"):
                for rel, target_id in node.outgoing:
                    if rel_type and rel.relationship_type != rel_type:
                        continue

                    if target_id in self.entities:
                        results.append({
                            "entity": self.entities[target_id],
                            "relationship": rel,
                            "direction": "outgoing",
                            "distance": depth + 1
                        })

                        if target_id not in visited and depth + 1 < max_depth:
                            visited.add(target_id)
                            queue.append((target_id, depth + 1))

            # Process incoming relationships
            if direction in ("incoming", "both"):
                for rel, source_id in node.incoming:
                    if rel_type and rel.relationship_type != rel_type:
                        continue

                    if source_id in self.entities:
                        results.append({
                            "entity": self.entities[source_id],
                            "relationship": rel,
                            "direction": "incoming",
                            "distance": depth + 1
                        })

                        if source_id not in visited and depth + 1 < max_depth:
                            visited.add(source_id)
                            queue.append((source_id, depth + 1))

        return results

    def find_entities_by_name(self, name: str, fuzzy: bool = True) -> List[Entity]:
        """
        Find entities by name.

        Args:
            name: Name to search for
            fuzzy: Enable fuzzy matching

        Returns:
            List of matching entities
        """
        name_lower = name.lower()

        if fuzzy:
            # Find all names that contain the search term
            matching_ids = set()
            for indexed_name, entity_ids in self.entities_by_name.items():
                if name_lower in indexed_name:
                    matching_ids.update(entity_ids)

            return [self.entities[eid] for eid in matching_ids if eid in self.entities]
        else:
            # Exact match
            entity_ids = self.entities_by_name.get(name_lower, set())
            return [self.entities[eid] for eid in entity_ids if eid in self.entities]

    def get_subgraph(self, entity_ids: Set[str], include_relationships: bool = True) -> Dict[str, Any]:
        """
        Extract a subgraph containing only specified entities.

        Args:
            entity_ids: Set of entity IDs to include
            include_relationships: Include relationships between entities

        Returns:
            Dictionary with entities and relationships
        """
        subgraph_entities = {
            eid: entity for eid, entity in self.entities.items()
            if eid in entity_ids
        }

        subgraph_relationships = []

        if include_relationships:
            for entity_id in entity_ids:
                # Get outgoing relationships where target is also in subgraph
                for rel in self.relationships_by_source.get(entity_id, []):
                    if rel.to_entity_id in entity_ids:
                        subgraph_relationships.append(rel)

        return {
            "entities": subgraph_entities,
            "relationships": subgraph_relationships
        }

    def calculate_centrality(self, entity_id: str) -> Dict[str, int]:
        """
        Calculate simple centrality metrics for an entity.

        Args:
            entity_id: Entity to analyze

        Returns:
            Dictionary with centrality metrics
        """
        node = self.nodes.get(entity_id)
        if not node:
            return {
                "degree": 0,
                "in_degree": 0,
                "out_degree": 0
            }

        return {
            "degree": len(node.incoming) + len(node.outgoing),
            "in_degree": len(node.incoming),
            "out_degree": len(node.outgoing)
        }

    def find_cycles(self, start_id: str, max_length: int = 5) -> List[List[str]]:
        """
        Find cycles in the graph starting from a given entity.

        Args:
            start_id: Entity to start from
            max_length: Maximum cycle length

        Returns:
            List of cycles (each cycle is a list of entity IDs)
        """
        cycles = []

        def dfs(current: str, path: List[str], visited: Set[str]):
            if len(path) > max_length:
                return

            node = self.nodes.get(current)
            if not node:
                return

            for rel, next_id in node.outgoing:
                if next_id == start_id and len(path) > 2:
                    # Found a cycle
                    cycles.append(path + [start_id])
                elif next_id not in visited:
                    visited.add(next_id)
                    dfs(next_id, path + [next_id], visited)
                    visited.remove(next_id)

        if start_id in self.nodes:
            dfs(start_id, [start_id], {start_id})

        return cycles

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get graph statistics.

        Returns:
            Dictionary with various graph metrics
        """
        entity_type_counts = {
            entity_type: len(ids)
            for entity_type, ids in self.entities_by_type.items()
        }

        relationship_type_counts = {
            rel_type.value: len(rels)
            for rel_type, rels in self.relationships_by_type.items()
        }

        # Calculate average degree
        total_degree = sum(
            len(node.incoming) + len(node.outgoing)
            for node in self.nodes.values()
        )
        avg_degree = total_degree / len(self.nodes) if self.nodes else 0

        return {
            "total_entities": len(self.entities),
            "total_relationships": sum(len(rels) for rels in self.relationships_by_source.values()),
            "entity_types": entity_type_counts,
            "relationship_types": relationship_type_counts,
            "average_degree": avg_degree,
            "isolated_entities": len([
                node for node in self.nodes.values()
                if not node.incoming and not node.outgoing
            ])
        }
