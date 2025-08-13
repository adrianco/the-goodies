"""
Local implementation of graph operations for the Blowing-Off client.

This module provides the concrete implementation of graph operations
that work with local storage instead of a database.
"""

from typing import List, Optional, Any, Dict
from dataclasses import dataclass
import uuid
from datetime import datetime, UTC

from inbetweenies.graph import GraphOperations, GraphSearch
from inbetweenies.mcp import MCPTools, ToolResult
from inbetweenies.models import Entity, EntityType, EntityRelationship, RelationshipType

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
    async def get_devices_in_room(self, room_id: str) -> ToolResult:
        """Get all devices located in a specific room"""
        try:
            room = await self.get_entity(room_id)
            if not room or room.entity_type != EntityType.ROOM:
                return ToolResult(False, None, f"Room {room_id} not found")
            
            relationships = await self.get_relationships(
                to_id=room_id,
                rel_type=RelationshipType.LOCATED_IN
            )
            
            devices = []
            for rel in relationships:
                device = await self.get_entity(rel.from_entity_id)
                if device and device.entity_type == EntityType.DEVICE:
                    devices.append(device)
            
            return ToolResult(True, {
                "room_id": room_id,
                "devices": [d.to_dict() if hasattr(d, 'to_dict') else d.__dict__ for d in devices],
                "count": len(devices)
            })
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def find_device_controls(self, device_id: str) -> ToolResult:
        """Get available controls and services for a device"""
        try:
            device = await self.get_entity(device_id)
            if not device or device.entity_type != EntityType.DEVICE:
                return ToolResult(False, None, f"Device {device_id} not found")
            
            capabilities = device.content.get("capabilities", []) if device.content else []
            
            controls_relationships = await self.get_relationships(
                from_id=device_id,
                rel_type=RelationshipType.CONTROLS
            )
            
            controlled_devices = []
            for rel in controls_relationships:
                controlled = await self.get_entity(rel.to_entity_id)
                if controlled:
                    controlled_devices.append({
                        "id": controlled.id,
                        "name": controlled.name,
                        "type": controlled.entity_type.value if hasattr(controlled.entity_type, 'value') else str(controlled.entity_type)
                    })
            
            return ToolResult(True, {
                "device_id": device_id,
                "device_name": device.name,
                "capabilities": capabilities,
                "controlled_devices": controlled_devices,
                "services": device.content.get("services", []) if device.content else []
            })
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def get_room_connections(self, room_id: str) -> ToolResult:
        """Find all rooms connected to a given room"""
        try:
            room = await self.get_entity(room_id)
            if not room or room.entity_type != EntityType.ROOM:
                return ToolResult(False, None, f"Room {room_id} not found")
            
            # Find direct connections
            from_connections = await self.get_relationships(
                from_id=room_id,
                rel_type=RelationshipType.CONNECTS_TO
            )
            to_connections = await self.get_relationships(
                to_id=room_id,
                rel_type=RelationshipType.CONNECTS_TO
            )
            
            connected_rooms = []
            for rel in from_connections:
                connected = await self.get_entity(rel.to_entity_id)
                if connected and connected.entity_type == EntityType.ROOM:
                    connected_rooms.append(connected)
            
            for rel in to_connections:
                connected = await self.get_entity(rel.from_entity_id)
                if connected and connected.entity_type == EntityType.ROOM:
                    if connected.id not in [r.id for r in connected_rooms]:
                        connected_rooms.append(connected)
            
            return ToolResult(True, {
                "room_id": room_id,
                "connected_rooms": [r.to_dict() if hasattr(r, 'to_dict') else r.__dict__ for r in connected_rooms],
                "count": len(connected_rooms)
            })
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def store_entity(self, entity: Entity) -> Entity:
        """Store an entity locally"""
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
    
    async def search_entities_tool(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> ToolResult:
        """Full-text search across entities (MCP tool)"""
        try:
            # Convert string types to EntityType enums if provided
            type_filter = None
            if entity_types:
                type_filter = []
                for et in entity_types:
                    try:
                        type_filter.append(EntityType(et))
                    except ValueError:
                        # Try uppercase
                        try:
                            type_filter.append(EntityType(et.upper()))
                        except ValueError:
                            pass  # Skip invalid types
            
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
            # Convert string type to EntityType enum
            try:
                etype = EntityType(entity_type)
            except ValueError:
                etype = EntityType(entity_type.upper())
            
            # Create entity
            entity = Entity(
                id=str(uuid.uuid4()),
                entity_type=etype,
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
            # Convert string type to RelationshipType enum
            try:
                rtype = RelationshipType(relationship_type)
            except ValueError:
                rtype = RelationshipType(relationship_type.upper())
            
            # Create relationship
            relationship = EntityRelationship(
                id=str(uuid.uuid4()),
                from_entity_id=from_entity_id,
                to_entity_id=to_entity_id,
                relationship_type=rtype,
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
    
    async def get_procedures_for_device_tool(self, device_id: str) -> ToolResult:
        """Get procedures for a device (MCP tool)"""
        try:
            device = await self.get_entity(device_id)
            if not device or device.entity_type != EntityType.DEVICE:
                return ToolResult(False, None, f"Device {device_id} not found")
            
            # Find procedures related to this device
            relationships = await self.get_relationships(
                from_id=device_id,
                rel_type=RelationshipType.PROCEDURE_FOR
            )
            
            procedures = []
            for rel in relationships:
                proc = await self.get_entity(rel.to_entity_id)
                if proc and proc.entity_type == EntityType.PROCEDURE:
                    procedures.append(proc)
            
            return ToolResult(True, {
                "device_id": device_id,
                "procedures": [p.to_dict() if hasattr(p, 'to_dict') else p.__dict__ for p in procedures],
                "count": len(procedures)
            })
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def get_automations_in_room_tool(self, room_id: str) -> ToolResult:
        """Get automations in a room (MCP tool)"""
        try:
            room = await self.get_entity(room_id)
            if not room or room.entity_type != EntityType.ROOM:
                return ToolResult(False, None, f"Room {room_id} not found")
            
            # Find automations related to this room
            relationships = await self.get_relationships(
                to_id=room_id,
                rel_type=RelationshipType.AUTOMATES
            )
            
            automations = []
            for rel in relationships:
                auto = await self.get_entity(rel.from_entity_id)
                if auto and auto.entity_type == EntityType.AUTOMATION:
                    automations.append(auto)
            
            return ToolResult(True, {
                "room_id": room_id,
                "automations": [a.to_dict() if hasattr(a, 'to_dict') else a.__dict__ for a in automations],
                "count": len(automations)
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