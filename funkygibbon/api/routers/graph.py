"""
Graph API Router

This module provides REST endpoints for graph operations including
entity management, relationship creation, and search functionality.
"""

from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from ...database import get_db
from ...models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType
from ...repositories.graph import GraphRepository
from ...graph.index import GraphIndex
from ...search.engine import SearchEngine


# Pydantic models for API
class EntityCreate(BaseModel):
    """Schema for creating a new entity"""
    entity_type: EntityType
    name: str
    content: Dict[str, Any] = Field(default_factory=dict)
    source_type: SourceType = SourceType.MANUAL
    user_id: str


class EntityUpdate(BaseModel):
    """Schema for updating an entity"""
    name: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    user_id: str


class RelationshipCreate(BaseModel):
    """Schema for creating a relationship"""
    from_entity_id: str
    to_entity_id: str
    relationship_type: RelationshipType
    properties: Dict[str, Any] = Field(default_factory=dict)
    user_id: str


class SearchQuery(BaseModel):
    """Schema for search requests"""
    query: str
    entity_types: Optional[List[EntityType]] = None
    limit: int = Field(default=10, le=100)


class PathQuery(BaseModel):
    """Schema for path finding requests"""
    from_entity_id: str
    to_entity_id: str
    max_depth: int = Field(default=10, le=20)


# Create router
router = APIRouter(prefix="/graph", tags=["graph"])

# In-memory graph index (in production, this would be a singleton service)
_graph_index: Optional[GraphIndex] = None


async def get_graph_index(db: AsyncSession = Depends(get_db)) -> GraphIndex:
    """Get or create the graph index"""
    global _graph_index
    
    if _graph_index is None:
        _graph_index = GraphIndex()
        repo = GraphRepository(db)
        await _graph_index.load_from_storage(repo)
    
    return _graph_index


@router.post("/entities", response_model=Dict[str, Any])
async def create_entity(
    entity_data: EntityCreate,
    db: AsyncSession = Depends(get_db),
    graph: GraphIndex = Depends(get_graph_index)
):
    """Create a new entity in the graph"""
    repo = GraphRepository(db)
    
    # Create entity
    entity = Entity(
        id=str(uuid4()),
        version=Entity.create_version(entity_data.user_id),
        entity_type=entity_data.entity_type,
        name=entity_data.name,
        content=entity_data.content,
        source_type=entity_data.source_type,
        user_id=entity_data.user_id,
        parent_versions=[]
    )
    
    # Store in database
    stored = await repo.store_entity(entity)
    await db.commit()
    
    # Update in-memory index
    graph._add_entity(stored)
    
    return {"entity": stored.to_dict()}


@router.get("/entities/{entity_id}", response_model=Dict[str, Any])
async def get_entity(
    entity_id: str,
    version: Optional[str] = Query(None, description="Specific version to retrieve"),
    include_relationships: bool = Query(True, description="Include relationships"),
    db: AsyncSession = Depends(get_db)
):
    """Get an entity by ID"""
    repo = GraphRepository(db)
    
    entity = await repo.get_entity(entity_id, version)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    result = {"entity": entity.to_dict()}
    
    if include_relationships:
        outgoing = await repo.get_relationships(from_id=entity_id)
        incoming = await repo.get_relationships(to_id=entity_id)
        
        result["relationships"] = {
            "outgoing": [rel.to_dict() for rel in outgoing],
            "incoming": [rel.to_dict() for rel in incoming]
        }
    
    return result


@router.get("/entities", response_model=Dict[str, Any])
async def list_entities(
    entity_type: Optional[EntityType] = Query(None, description="Filter by entity type"),
    limit: int = Query(10, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db)
):
    """List entities with optional filtering"""
    repo = GraphRepository(db)
    
    if entity_type:
        entities = await repo.get_entities_by_type(entity_type)
    else:
        # Get all entity types
        all_entities = []
        for et in EntityType:
            type_entities = await repo.get_entities_by_type(et)
            all_entities.extend(type_entities)
        entities = all_entities
    
    # Apply pagination
    paginated = entities[offset:offset + limit]
    
    return {
        "entities": [e.to_dict() for e in paginated],
        "total": len(entities),
        "limit": limit,
        "offset": offset
    }


@router.put("/entities/{entity_id}", response_model=Dict[str, Any])
async def update_entity(
    entity_id: str,
    update_data: EntityUpdate,
    db: AsyncSession = Depends(get_db),
    graph: GraphIndex = Depends(get_graph_index)
):
    """Update an entity (creates new version)"""
    repo = GraphRepository(db)
    
    # Get current entity
    current = await repo.get_entity(entity_id)
    if not current:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Prepare changes
    changes = {}
    if update_data.name is not None:
        changes["name"] = update_data.name
    if update_data.content is not None:
        changes["content"] = update_data.content
    
    # Create new version
    new_entity = current.create_new_version(update_data.user_id, changes)
    
    # Store new version
    stored = await repo.store_entity(new_entity)
    await db.commit()
    
    # Update in-memory index
    graph._add_entity(stored)
    
    return {
        "entity": stored.to_dict(),
        "previous_version": current.version
    }


@router.get("/entities/{entity_id}/versions", response_model=Dict[str, Any])
async def get_entity_versions(
    entity_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all versions of an entity"""
    repo = GraphRepository(db)
    
    versions = await repo.get_entity_versions(entity_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    return {
        "entity_id": entity_id,
        "versions": [v.to_dict() for v in versions],
        "count": len(versions)
    }


@router.post("/relationships", response_model=Dict[str, Any])
async def create_relationship(
    rel_data: RelationshipCreate,
    db: AsyncSession = Depends(get_db),
    graph: GraphIndex = Depends(get_graph_index)
):
    """Create a relationship between entities"""
    repo = GraphRepository(db)
    
    # Validate entities exist
    from_entity = await repo.get_entity(rel_data.from_entity_id)
    to_entity = await repo.get_entity(rel_data.to_entity_id)
    
    if not from_entity or not to_entity:
        raise HTTPException(status_code=404, detail="One or both entities not found")
    
    # Create relationship
    relationship = EntityRelationship(
        id=str(uuid4()),
        from_entity_id=from_entity.id,
        from_entity_version=from_entity.version,
        to_entity_id=to_entity.id,
        to_entity_version=to_entity.version,
        relationship_type=rel_data.relationship_type,
        properties=rel_data.properties,
        user_id=rel_data.user_id
    )
    
    # Validate relationship type
    # TODO: Enable validation once server restart picks up the new method from Inbetweenies
    # if not relationship.is_valid_for_entities(from_entity, to_entity):
    #     raise HTTPException(
    #         status_code=400,
    #         detail=f"Relationship {rel_data.relationship_type} not valid between "
    #                f"{from_entity.entity_type} and {to_entity.entity_type}"
    #     )
    
    # Store relationship
    stored = await repo.store_relationship(relationship)
    await db.commit()
    
    # Update in-memory index
    graph._add_relationship(stored)
    
    return {"relationship": stored.to_dict()}


@router.get("/relationships", response_model=Dict[str, Any])
async def list_relationships(
    from_entity_id: Optional[str] = Query(None, description="Filter by source entity"),
    to_entity_id: Optional[str] = Query(None, description="Filter by target entity"),
    relationship_type: Optional[RelationshipType] = Query(None, description="Filter by type"),
    db: AsyncSession = Depends(get_db)
):
    """List relationships with optional filtering"""
    repo = GraphRepository(db)
    
    relationships = await repo.get_relationships(
        from_id=from_entity_id,
        to_id=to_entity_id,
        rel_type=relationship_type
    )
    
    return {
        "relationships": [rel.to_dict() for rel in relationships],
        "count": len(relationships)
    }


@router.post("/search", response_model=Dict[str, Any])
async def search_graph(
    search_query: SearchQuery,
    graph: GraphIndex = Depends(get_graph_index)
):
    """Search entities by content"""
    search_engine = SearchEngine(graph)
    
    results = search_engine.search_entities(
        query=search_query.query,
        entity_types=search_query.entity_types,
        limit=search_query.limit
    )
    
    return {
        "query": search_query.query,
        "results": [result.to_dict() for result in results],
        "count": len(results)
    }


@router.post("/path", response_model=Dict[str, Any])
async def find_path(
    path_query: PathQuery,
    graph: GraphIndex = Depends(get_graph_index)
):
    """Find shortest path between two entities"""
    path = graph.find_path(
        path_query.from_entity_id,
        path_query.to_entity_id,
        path_query.max_depth
    )
    
    if not path:
        return {
            "from": path_query.from_entity_id,
            "to": path_query.to_entity_id,
            "path": [],
            "found": False
        }
    
    # Get entity details for path
    path_entities = []
    for entity_id in path:
        entity = graph.entities.get(entity_id)
        if entity:
            path_entities.append({
                "id": entity.id,
                "name": entity.name,
                "type": entity.entity_type.value
            })
    
    return {
        "from": path_query.from_entity_id,
        "to": path_query.to_entity_id,
        "path": path_entities,
        "length": len(path) - 1,
        "found": True
    }


@router.get("/entities/{entity_id}/connected", response_model=Dict[str, Any])
async def get_connected_entities(
    entity_id: str,
    relationship_type: Optional[RelationshipType] = Query(None, description="Filter by relationship type"),
    direction: str = Query("both", regex="^(incoming|outgoing|both)$", description="Direction of relationships"),
    max_depth: int = Query(1, le=5, description="Maximum traversal depth"),
    graph: GraphIndex = Depends(get_graph_index)
):
    """Get entities connected to a given entity"""
    connected = graph.get_connected_entities(
        entity_id,
        rel_type=relationship_type,
        direction=direction,
        max_depth=max_depth
    )
    
    return {
        "entity_id": entity_id,
        "connected": [
            {
                "entity": conn["entity"].to_dict(),
                "relationship_type": conn["relationship"].relationship_type.value,
                "direction": conn["direction"],
                "distance": conn["distance"]
            }
            for conn in connected
        ],
        "count": len(connected)
    }


@router.get("/entities/{entity_id}/similar", response_model=Dict[str, Any])
async def find_similar_entities(
    entity_id: str,
    threshold: float = Query(0.7, ge=0, le=1, description="Similarity threshold"),
    limit: int = Query(10, le=50, description="Maximum results"),
    graph: GraphIndex = Depends(get_graph_index)
):
    """Find entities similar to the given entity"""
    search_engine = SearchEngine(graph)
    
    results = search_engine.find_similar(entity_id, threshold, limit)
    
    return {
        "reference_entity_id": entity_id,
        "similar_entities": [result.to_dict() for result in results],
        "count": len(results)
    }


@router.get("/statistics", response_model=Dict[str, Any])
async def get_graph_statistics(
    graph: GraphIndex = Depends(get_graph_index)
):
    """Get graph statistics"""
    return graph.get_statistics()