"""
SQLAlchemy implementation of graph operations for FunkyGibbon.

This module provides the concrete implementation of the abstract
graph operations using SQLAlchemy for database access.
"""

from typing import List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from inbetweenies.graph import GraphOperations, GraphSearch
from inbetweenies.mcp import MCPTools
from inbetweenies.models import Entity, EntityType, EntityRelationship, RelationshipType, SourceType


class SQLGraphOperations(MCPTools):
    """
    SQLAlchemy implementation of graph operations.
    
    This class provides the concrete implementation of all abstract methods
    from GraphOperations, GraphSearch, and MCPTools using SQLAlchemy.
    """
    
    def __init__(self, db: AsyncSession):
        """Initialize with database session"""
        self.db = db
    
    async def store_entity(self, entity: Entity) -> Entity:
        """Store an entity in the database"""
        self.db.add(entity)
        await self.db.flush()
        return entity
    
    async def get_entity(self, entity_id: str, version: Optional[str] = None) -> Optional[Entity]:
        """Get an entity by ID and optional version"""
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
        """Get all entities of a specific type (latest versions only)"""
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
    
    async def store_relationship(self, relationship: EntityRelationship) -> EntityRelationship:
        """Store a relationship in the database"""
        from uuid import uuid4
        
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
        rel_type: Optional[RelationshipType] = None
    ) -> List[EntityRelationship]:
        """Get relationships with optional filters"""
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
        
        # Filter to latest versions only if entity IDs are specified
        if not hasattr(self, '_include_all_versions') and (from_id or to_id):
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
    ) -> List[Any]:  # Returns List[SearchResult]
        """Search entities by name or content"""
        from sqlalchemy import or_
        
        conditions = []
        
        # Search in name
        conditions.append(Entity.name.ilike(f"%{query}%"))
        
        # For SQLite JSON search, we need to cast to text
        # This is a simplified search - in production you might want FTS
        
        stmt = select(Entity).where(or_(*conditions))
        
        if entity_types:
            stmt = stmt.where(Entity.entity_type.in_(entity_types))
        
        # Get latest versions only - simplified approach
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
        
        # Convert to SearchResult objects
        return self.filter_and_rank_results(unique_entities, query, limit)
    
    async def get_entity_versions(self, entity_id: str) -> List[Entity]:
        """Get all versions of an entity"""
        stmt = (
            select(Entity)
            .where(Entity.id == entity_id)
            .order_by(Entity.created_at.asc())
        )
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def find_path(self, from_id: str, to_id: str, max_depth: int = 10) -> List[Entity]:
        """Find path between entities using BFS"""
        # For now, return empty list - graph traversal needs the in-memory index
        # This would be better implemented with recursive CTEs in SQL
        return []
    
    async def find_similar_entities(self, entity_id: str, limit: int = 5) -> List[Any]:
        """Find similar entities"""
        # For now, return entities of the same type
        entity = await self.get_entity(entity_id)
        if not entity:
            return []
        
        similar = await self.get_entities_by_type(entity.entity_type)
        # Filter out the reference entity
        similar = [e for e in similar if e.id != entity_id]
        return self.filter_and_rank_results(similar[:limit], entity.name, limit)
    
    async def update_entity(self, entity_id: str, changes: dict, user_id: str) -> Entity:
        """Update entity by creating new version"""
        current = await self.get_entity(entity_id)
        if not current:
            raise ValueError(f"Entity {entity_id} not found")
        
        # Create new version
        new_entity = current.create_new_version(user_id, changes)
        
        # Store new version
        stored = await self.store_entity(new_entity)
        await self.db.commit()
        
        return stored