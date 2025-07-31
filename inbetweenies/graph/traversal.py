"""
Graph traversal algorithms and utilities.

Provides various graph traversal algorithms for exploring entity relationships.
"""

from typing import List, Dict, Set, Optional, Callable, Any
from collections import deque, defaultdict
from abc import ABC, abstractmethod

from ..models import Entity, EntityRelationship, RelationshipType


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
    
    async def get_ancestors(
        self,
        entity_id: str,
        rel_type: RelationshipType,
        max_depth: Optional[int] = None
    ) -> List[Entity]:
        """
        Get all ancestors of an entity following a specific relationship type.
        
        Args:
            entity_id: Starting entity ID
            rel_type: Relationship type to follow (e.g., PART_OF)
            max_depth: Maximum depth to traverse
            
        Returns:
            List of ancestor entities
        """
        ancestors = []
        visited = set()
        
        async def find_ancestors(current_id: str, depth: int):
            if current_id in visited:
                return
                
            if max_depth is not None and depth > max_depth:
                return
                
            visited.add(current_id)
            
            # Get incoming relationships of the specified type
            relationships = await self.get_relationships(to_id=current_id, rel_type=rel_type)
            
            for rel in relationships:
                parent = await self.get_entity(rel.from_entity_id)
                if parent and parent.id not in visited:
                    ancestors.append(parent)
                    await find_ancestors(parent.id, depth + 1)
        
        await find_ancestors(entity_id, 0)
        return ancestors
    
    async def get_descendants(
        self,
        entity_id: str,
        rel_type: RelationshipType,
        max_depth: Optional[int] = None
    ) -> List[Entity]:
        """
        Get all descendants of an entity following a specific relationship type.
        
        Args:
            entity_id: Starting entity ID
            rel_type: Relationship type to follow
            max_depth: Maximum depth to traverse
            
        Returns:
            List of descendant entities
        """
        # Use BFS with relationship filter
        return await self.bfs(
            entity_id,
            max_depth=max_depth,
            rel_types=[rel_type]
        )
    
    async def detect_cycles(
        self,
        start_id: Optional[str] = None,
        rel_types: Optional[List[RelationshipType]] = None
    ) -> List[List[str]]:
        """
        Detect cycles in the graph.
        
        Args:
            start_id: Optional starting point (if None, check entire graph)
            rel_types: Filter by relationship types
            
        Returns:
            List of cycles (each cycle is a list of entity IDs)
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
            # Check entire graph
            # This would need access to all entities, which requires extending the interface
            pass
        
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