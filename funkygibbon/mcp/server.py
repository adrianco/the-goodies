"""
MCP Server Implementation for FunkyGibbon

This module implements the MCP server that exposes graph operations
as tools for AI agents and external systems.
"""

from typing import Dict, Any, Optional, List
from uuid import uuid4
import logging

from ..graph.index import GraphIndex
from ..search.engine import SearchEngine
from ..repositories.graph import GraphRepository
from ..models import (
    Entity, EntityType, SourceType,
    EntityRelationship, RelationshipType
)
from .tools import MCP_TOOLS


logger = logging.getLogger(__name__)


class FunkyGibbonMCPServer:
    """MCP server exposing graph operations"""
    
    def __init__(self, graph_index: GraphIndex, graph_repo: GraphRepository):
        self.graph = graph_index
        self.repo = graph_repo
        self.search = SearchEngine(graph_index)
        self.tools = {tool["name"]: tool for tool in MCP_TOOLS}
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available MCP tools"""
        return MCP_TOOLS
    
    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route tool calls to appropriate handlers.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        if tool_name not in self.tools:
            return {
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(self.tools.keys())
            }
        
        try:
            # Route to specific handler
            handler = getattr(self, f"_handle_{tool_name}", None)
            if not handler:
                return {"error": f"Handler not implemented for tool: {tool_name}"}
            
            result = await handler(**arguments)
            return {"success": True, "result": result}
            
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}")
            return {"error": str(e)}
    
    async def _handle_get_devices_in_room(self, room_id: str) -> Dict[str, Any]:
        """Get all devices in a specific room"""
        # Find all devices with LOCATED_IN relationship to the room
        relationships = await self.repo.get_relationships(
            to_id=room_id,
            rel_type=RelationshipType.LOCATED_IN
        )
        
        devices = []
        for rel in relationships:
            if rel.from_entity and rel.from_entity.entity_type == EntityType.DEVICE:
                devices.append(rel.from_entity.to_dict())
        
        return {
            "room_id": room_id,
            "devices": devices,
            "count": len(devices)
        }
    
    async def _handle_find_device_controls(self, device_id: str) -> Dict[str, Any]:
        """Get controls for a device"""
        # Get the device
        device = await self.repo.get_entity(device_id)
        if not device or device.entity_type != EntityType.DEVICE:
            return {"error": "Device not found"}
        
        # Find devices this device controls
        controls_relationships = await self.repo.get_relationships(
            from_id=device_id,
            rel_type=RelationshipType.CONTROLS
        )
        
        # Find devices that control this device
        controlled_by = await self.repo.get_relationships(
            to_id=device_id,
            rel_type=RelationshipType.CONTROLS
        )
        
        return {
            "device": device.to_dict(),
            "controls": [rel.to_entity.to_dict() for rel in controls_relationships if rel.to_entity],
            "controlled_by": [rel.from_entity.to_dict() for rel in controlled_by if rel.from_entity],
            "capabilities": device.content.get("capabilities", [])
        }
    
    async def _handle_get_room_connections(self, room_id: str) -> Dict[str, Any]:
        """Find connections between rooms"""
        # Get all CONNECTS_TO relationships
        connections = self.graph.get_connected_entities(
            room_id,
            rel_type=RelationshipType.CONNECTS_TO,
            direction="both"
        )
        
        # Find doors and windows in this room
        located_in_room = await self.repo.get_relationships(
            to_id=room_id,
            rel_type=RelationshipType.LOCATED_IN
        )
        
        doors = []
        windows = []
        
        for rel in located_in_room:
            if rel.from_entity:
                if rel.from_entity.entity_type == EntityType.DOOR:
                    doors.append(rel.from_entity.to_dict())
                elif rel.from_entity.entity_type == EntityType.WINDOW:
                    windows.append(rel.from_entity.to_dict())
        
        return {
            "room_id": room_id,
            "connected_rooms": [conn["entity"].to_dict() for conn in connections],
            "doors": doors,
            "windows": windows
        }
    
    async def _handle_search_entities(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Search for entities"""
        # Convert string types to EntityType enums
        types = None
        if entity_types:
            types = [EntityType(t) for t in entity_types]
        
        results = self.search.search_entities(query, types, limit)
        
        return {
            "query": query,
            "results": [result.to_dict() for result in results],
            "count": len(results)
        }
    
    async def _handle_create_entity(
        self,
        entity_type: str,
        name: str,
        content: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new entity"""
        entity = Entity(
            id=str(uuid4()),
            version=Entity.create_version("mcp-user"),
            entity_type=EntityType(entity_type),
            name=name,
            content=content or {},
            source_type=SourceType.MANUAL,
            user_id="mcp-user",
            parent_versions=[]
        )
        
        stored = await self.repo.store_entity(entity)
        await self.repo.db.commit()
        
        # Update in-memory index
        self.graph._add_entity(stored)
        
        return {"entity": stored.to_dict()}
    
    async def _handle_create_relationship(
        self,
        from_entity_id: str,
        to_entity_id: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a relationship between entities"""
        # Get entities to validate they exist and get versions
        from_entity = await self.repo.get_entity(from_entity_id)
        to_entity = await self.repo.get_entity(to_entity_id)
        
        if not from_entity or not to_entity:
            return {"error": "One or both entities not found"}
        
        relationship = EntityRelationship(
            id=str(uuid4()),
            from_entity_id=from_entity.id,
            from_entity_version=from_entity.version,
            to_entity_id=to_entity.id,
            to_entity_version=to_entity.version,
            relationship_type=RelationshipType(relationship_type),
            properties=properties or {},
            user_id="mcp-user"
        )
        
        # Validate relationship is allowed
        # TODO: Enable validation once server restart picks up the new method from Inbetweenies
        # if not relationship.is_valid_for_entities(from_entity, to_entity):
        #     return {
        #         "error": f"Relationship {relationship_type} not valid between "
        #                 f"{from_entity.entity_type} and {to_entity.entity_type}"
        #     }
        
        stored = await self.repo.store_relationship(relationship)
        await self.repo.db.commit()
        
        # Update in-memory index
        self.graph._add_relationship(stored)
        
        return {"relationship": stored.to_dict()}
    
    async def _handle_find_path(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 10
    ) -> Dict[str, Any]:
        """Find path between entities"""
        path = self.graph.find_path(from_entity_id, to_entity_id, max_depth)
        
        if not path:
            return {
                "from": from_entity_id,
                "to": to_entity_id,
                "path": [],
                "found": False
            }
        
        # Get entity details for path
        path_entities = []
        for entity_id in path:
            entity = self.graph.entities.get(entity_id)
            if entity:
                path_entities.append({
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.entity_type.value
                })
        
        return {
            "from": from_entity_id,
            "to": to_entity_id,
            "path": path_entities,
            "length": len(path) - 1,
            "found": True
        }
    
    async def _handle_get_entity_details(
        self,
        entity_id: str,
        include_relationships: bool = True,
        include_connected: bool = False
    ) -> Dict[str, Any]:
        """Get detailed entity information"""
        entity = await self.repo.get_entity(entity_id)
        if not entity:
            return {"error": "Entity not found"}
        
        result = {"entity": entity.to_dict()}
        
        if include_relationships:
            outgoing = await self.repo.get_relationships(from_id=entity_id)
            incoming = await self.repo.get_relationships(to_id=entity_id)
            
            result["relationships"] = {
                "outgoing": [rel.to_dict() for rel in outgoing],
                "incoming": [rel.to_dict() for rel in incoming]
            }
        
        if include_connected:
            connected = self.graph.get_connected_entities(entity_id)
            result["connected_entities"] = [
                {
                    "entity": conn["entity"].to_dict(),
                    "relationship_type": conn["relationship"].relationship_type.value,
                    "direction": conn["direction"]
                }
                for conn in connected
            ]
        
        return result
    
    async def _handle_find_similar_entities(
        self,
        entity_id: str,
        threshold: float = 0.7,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Find similar entities"""
        results = self.search.find_similar(entity_id, threshold, limit)
        
        return {
            "reference_entity_id": entity_id,
            "similar_entities": [result.to_dict() for result in results],
            "count": len(results)
        }
    
    async def _handle_get_procedures_for_device(self, device_id: str) -> Dict[str, Any]:
        """Get procedures and manuals for a device"""
        # Find DOCUMENTED_BY relationships
        documented_by = await self.repo.get_relationships(
            from_id=device_id,
            rel_type=RelationshipType.DOCUMENTED_BY
        )
        
        # Find PROCEDURE_FOR relationships
        procedures = await self.repo.get_relationships(
            to_id=device_id,
            rel_type=RelationshipType.PROCEDURE_FOR
        )
        
        manuals = []
        procedure_docs = []
        
        for rel in documented_by:
            if rel.to_entity:
                if rel.to_entity.entity_type == EntityType.MANUAL:
                    manuals.append(rel.to_entity.to_dict())
                elif rel.to_entity.entity_type == EntityType.PROCEDURE:
                    procedure_docs.append(rel.to_entity.to_dict())
        
        for rel in procedures:
            if rel.from_entity and rel.from_entity.entity_type == EntityType.PROCEDURE:
                procedure_docs.append(rel.from_entity.to_dict())
        
        # Remove duplicates
        seen = set()
        unique_procedures = []
        for proc in procedure_docs:
            if proc["id"] not in seen:
                seen.add(proc["id"])
                unique_procedures.append(proc)
        
        return {
            "device_id": device_id,
            "manuals": manuals,
            "procedures": unique_procedures
        }
    
    async def _handle_get_automations_in_room(self, room_id: str) -> Dict[str, Any]:
        """Get automations affecting a room"""
        # First get all devices in the room
        devices_in_room = await self._handle_get_devices_in_room(room_id)
        device_ids = {d["id"] for d in devices_in_room["devices"]}
        
        # Find automations that manage these devices
        automations = []
        seen_automation_ids = set()
        
        for device_id in device_ids:
            # MANAGES relationships
            managed_by = await self.repo.get_relationships(
                to_id=device_id,
                rel_type=RelationshipType.MANAGES
            )
            
            # AUTOMATES relationships
            automated_by = await self.repo.get_relationships(
                to_id=device_id,
                rel_type=RelationshipType.AUTOMATES
            )
            
            for rel in managed_by + automated_by:
                if (rel.from_entity and 
                    rel.from_entity.entity_type == EntityType.AUTOMATION and
                    rel.from_entity.id not in seen_automation_ids):
                    
                    seen_automation_ids.add(rel.from_entity.id)
                    automations.append(rel.from_entity.to_dict())
        
        return {
            "room_id": room_id,
            "automations": automations,
            "count": len(automations)
        }
    
    async def _handle_update_entity(
        self,
        entity_id: str,
        changes: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Update an entity (creates new version)"""
        # Get current entity
        current = await self.repo.get_entity(entity_id)
        if not current:
            return {"error": "Entity not found"}
        
        # Create new version
        new_entity = current.create_new_version(user_id, changes)
        
        # Store new version
        stored = await self.repo.store_entity(new_entity)
        await self.repo.db.commit()
        
        # Update in-memory index with new version
        self.graph._add_entity(stored)
        
        return {
            "entity": stored.to_dict(),
            "previous_version": current.version
        }