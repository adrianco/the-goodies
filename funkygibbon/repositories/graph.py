"""
Graph Repository for Entity and Relationship Operations

This module provides the repository pattern implementation for graph operations,
handling storage and retrieval of entities and relationships.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Entity, EntityType, EntityRelationship, RelationshipType
from .base import BaseRepository


class GraphRepository(BaseRepository[Entity]):
    """Repository for graph operations on entities and relationships"""
    
    model = Entity
    
    def __init__(self, db: AsyncSession):
        """Initialize with database session"""
        super().__init__(Entity)
        self.db = db
    
    async def store_entity(self, entity: Entity) -> Entity:
        """
        Store entity with version tracking.
        
        Args:
            entity: Entity to store
            
        Returns:
            Stored entity
        """
        self.db.add(entity)
        await self.db.flush()
        return entity
    
    async def get_entity(self, entity_id: str, version: Optional[str] = None) -> Optional[Entity]:
        """
        Get specific version or latest entity.
        
        Args:
            entity_id: Entity ID
            version: Specific version to retrieve (optional)
            
        Returns:
            Entity if found, None otherwise
        """
        if version:
            # Get specific version
            stmt = select(Entity).where(
                and_(Entity.id == entity_id, Entity.version == version)
            )
        else:
            # Get latest version
            stmt = select(Entity).where(
                Entity.id == entity_id
            ).order_by(Entity.created_at.desc()).limit(1)
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """
        Get all entities of a specific type (latest versions only).
        
        Args:
            entity_type: Type of entities to retrieve
            
        Returns:
            List of entities
        """
        # Subquery to get latest version for each entity ID
        subquery = (
            select(Entity.id, Entity.version, Entity.created_at)
            .where(Entity.entity_type == entity_type)
            .subquery()
        )
        
        # Window function to rank versions by created_at
        from sqlalchemy import func
        ranked = (
            select(
                subquery.c.id,
                subquery.c.version,
                func.row_number().over(
                    partition_by=subquery.c.id,
                    order_by=subquery.c.created_at.desc()
                ).label("rn")
            ).subquery()
        )
        
        # Get only the latest version (rn=1) for each entity
        latest_versions = (
            select(ranked.c.id, ranked.c.version)
            .where(ranked.c.rn == 1)
            .subquery()
        )
        
        # Join with Entity table to get full entity data
        stmt = (
            select(Entity)
            .join(
                latest_versions,
                and_(
                    Entity.id == latest_versions.c.id,
                    Entity.version == latest_versions.c.version
                )
            )
            .options(selectinload(Entity.outgoing_relationships))
            .options(selectinload(Entity.incoming_relationships))
        )
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_entity_versions(self, entity_id: str) -> List[Entity]:
        """
        Get all versions of an entity.
        
        Args:
            entity_id: Entity ID
            
        Returns:
            List of all entity versions ordered by creation time
        """
        stmt = (
            select(Entity)
            .where(Entity.id == entity_id)
            .order_by(Entity.created_at.asc())
        )
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def store_relationship(self, relationship: EntityRelationship) -> EntityRelationship:
        """
        Store relationship between entities.
        
        Args:
            relationship: Relationship to store
            
        Returns:
            Stored relationship
        """
        # Generate ID if not provided
        if not relationship.id:
            relationship.id = str(uuid4())
            
        self.db.add(relationship)
        await self.db.flush()
        return relationship
    
    async def get_relationships(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        rel_type: Optional[RelationshipType] = None,
        include_all_versions: bool = False
    ) -> List[EntityRelationship]:
        """
        Query relationships with filters.
        
        Args:
            from_id: Source entity ID (optional)
            to_id: Target entity ID (optional)
            rel_type: Relationship type filter (optional)
            include_all_versions: Include relationships from all entity versions
            
        Returns:
            List of matching relationships
        """
        conditions = []
        
        if from_id:
            conditions.append(EntityRelationship.from_entity_id == from_id)
        if to_id:
            conditions.append(EntityRelationship.to_entity_id == to_id)
        if rel_type:
            conditions.append(EntityRelationship.relationship_type == rel_type)
        
        stmt = select(EntityRelationship)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Include related entities
        stmt = stmt.options(
            selectinload(EntityRelationship.from_entity),
            selectinload(EntityRelationship.to_entity)
        )
        
        result = await self.db.execute(stmt)
        relationships = list(result.scalars().all())
        
        # Filter to latest versions only if requested
        if not include_all_versions and (from_id or to_id):
            # Get latest versions of the entities
            latest_versions = {}
            
            for rel in relationships:
                if rel.from_entity_id not in latest_versions:
                    latest_from = await self.get_entity(rel.from_entity_id)
                    if latest_from:
                        latest_versions[rel.from_entity_id] = latest_from.version
                        
                if rel.to_entity_id not in latest_versions:
                    latest_to = await self.get_entity(rel.to_entity_id)
                    if latest_to:
                        latest_versions[rel.to_entity_id] = latest_to.version
            
            # Filter relationships to only include latest versions
            relationships = [
                rel for rel in relationships
                if (rel.from_entity_version == latest_versions.get(rel.from_entity_id) and
                    rel.to_entity_version == latest_versions.get(rel.to_entity_id))
            ]
        
        return relationships
    
    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 10
    ) -> List[Entity]:
        """
        Search entities by name or content.
        
        Args:
            query: Search query
            entity_types: Filter by entity types (optional)
            limit: Maximum results to return
            
        Returns:
            List of matching entities (latest versions only)
        """
        conditions = []
        
        # Search in name
        conditions.append(Entity.name.ilike(f"%{query}%"))
        
        # For SQLite JSON search, we need to cast to text
        # This is a simplified search - in production you might want FTS
        # Note: JSON search in SQLite is limited, consider using PostgreSQL for better JSON support
        
        stmt = select(Entity).where(or_(*conditions))
        
        if entity_types:
            stmt = stmt.where(Entity.entity_type.in_(entity_types))
        
        # Get latest versions only - simplified approach
        # In production, you'd want to use the window function approach
        stmt = stmt.order_by(Entity.created_at.desc()).limit(limit * 3)
        
        result = await self.db.execute(stmt)
        entities = list(result.scalars().all())
        
        # Simple deduplication - keep only latest version of each entity
        seen_ids = set()
        unique_entities = []
        
        for entity in entities:
            if entity.id not in seen_ids:
                seen_ids.add(entity.id)
                unique_entities.append(entity)
                if len(unique_entities) >= limit:
                    break
        
        return unique_entities
    
    async def get_connected_entities(
        self,
        entity_id: str,
        rel_type: Optional[RelationshipType] = None,
        direction: str = "both"
    ) -> List[Dict[str, Any]]:
        """
        Get all entities connected to a given entity.
        
        Args:
            entity_id: Center entity ID
            rel_type: Filter by relationship type (optional)
            direction: "outgoing", "incoming", or "both"
            
        Returns:
            List of connected entities with relationship info
        """
        connected = []
        
        if direction in ("outgoing", "both"):
            outgoing = await self.get_relationships(
                from_id=entity_id,
                rel_type=rel_type
            )
            
            for rel in outgoing:
                if rel.to_entity:
                    connected.append({
                        "entity": rel.to_entity,
                        "relationship": rel,
                        "direction": "outgoing"
                    })
        
        if direction in ("incoming", "both"):
            incoming = await self.get_relationships(
                to_id=entity_id,
                rel_type=rel_type
            )
            
            for rel in incoming:
                if rel.from_entity:
                    connected.append({
                        "entity": rel.from_entity,
                        "relationship": rel,
                        "direction": "incoming"
                    })
        
        return connected