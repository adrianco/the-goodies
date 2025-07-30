"""
Local implementation of graph operations for the Blowing-Off client.

This module provides the concrete implementation of graph operations
that work with local storage instead of a database.
"""

from typing import List, Optional, Any
from dataclasses import dataclass

from inbetweenies.graph import GraphOperations, GraphSearch
from inbetweenies.mcp import MCPTools
from inbetweenies.models import Entity, EntityType, EntityRelationship, RelationshipType

from .local_storage import LocalGraphStorage


@dataclass
class SearchResult:
    """Simple search result for local implementation"""
    entity: Entity
    score: float = 1.0
    
    def to_dict(self):
        return {
            "entity": self.entity.__dict__,
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
    
    async def store_entity(self, entity: Entity) -> Entity:
        """Store an entity locally"""
        return self.storage.store_entity(entity)
    
    async def get_entity(self, entity_id: str, version: Optional[str] = None) -> Optional[Entity]:
        """Get an entity from local storage"""
        return self.storage.get_entity(entity_id, version)
    
    async def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Get all entities of a specific type"""
        return self.storage.get_entities_by_type(entity_type)
    
    async def store_relationship(self, relationship: EntityRelationship) -> EntityRelationship:
        """Store a relationship locally"""
        return self.storage.store_relationship(relationship)
    
    async def get_relationships(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        rel_type: Optional[RelationshipType] = None
    ) -> List[EntityRelationship]:
        """Get relationships with optional filters"""
        return self.storage.get_relationships(from_id, to_id, rel_type)
    
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