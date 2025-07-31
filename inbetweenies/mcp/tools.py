"""
MCP tools implementation that works with graph operations.

These tools can be used with any GraphOperations implementation,
allowing them to work both server-side and client-side.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from abc import ABC

from ..models import Entity, EntityType, EntityRelationship, RelationshipType, SourceType
from ..graph.operations import GraphOperations
from ..graph.search import GraphSearch


@dataclass
class ToolResult:
    """Result from an MCP tool execution"""
    success: bool
    result: Any
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error
        }


class MCPTools(GraphOperations, GraphSearch, ABC):
    """
    MCP tools implementation.
    
    This class provides all the MCP tool methods that work with
    the abstract GraphOperations interface.
    """
    
    async def get_devices_in_room(self, room_id: str) -> ToolResult:
        """Get all devices located in a specific room"""
        try:
            # Get the room to verify it exists
            room = await self.get_entity(room_id)
            if not room or room.entity_type != EntityType.ROOM:
                return ToolResult(False, None, f"Room {room_id} not found")
            
            # Get all devices in this room
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
                "devices": [d.to_dict() for d in devices],
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
            
            # Get capabilities from device content
            capabilities = device.content.get("capabilities", []) if device.content else []
            
            # Get devices this device controls
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
                        "type": controlled.entity_type.value
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
            
            # Get connections via CONNECTS_TO relationships
            connections = []
            
            # Outgoing connections
            outgoing = await self.get_relationships(
                from_id=room_id,
                rel_type=RelationshipType.CONNECTS_TO
            )
            
            # Incoming connections
            incoming = await self.get_relationships(
                to_id=room_id,
                rel_type=RelationshipType.CONNECTS_TO
            )
            
            connected_rooms = {}
            
            for rel in outgoing + incoming:
                other_id = rel.to_entity_id if rel.from_entity_id == room_id else rel.from_entity_id
                
                if other_id not in connected_rooms:
                    other_room = await self.get_entity(other_id)
                    if other_room and other_room.entity_type == EntityType.ROOM:
                        connected_rooms[other_id] = {
                            "id": other_room.id,
                            "name": other_room.name,
                            "connection_type": rel.properties.get("via", "direct") if rel.properties else "direct"
                        }
            
            return ToolResult(True, {
                "room_id": room_id,
                "room_name": room.name,
                "connections": list(connected_rooms.values()),
                "connection_count": len(connected_rooms)
            })
            
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def search_entities_tool(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> ToolResult:
        """Full-text search across entities"""
        try:
            # Convert string types to EntityType enums
            type_filter = None
            if entity_types:
                type_filter = [EntityType(et) for et in entity_types]
            
            # Use the search functionality
            results = await self.search_entities(query, type_filter, limit)
            
            return ToolResult(True, {
                "query": query,
                "results": [r.to_dict() for r in results],
                "count": len(results)
            })
            
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def create_entity_tool(
        self,
        entity_type: str,
        name: str,
        content: Dict[str, Any],
        user_id: str
    ) -> ToolResult:
        """Create a new entity in the graph"""
        try:
            from uuid import uuid4
            
            entity = Entity(
                id=str(uuid4()),
                version=Entity.create_version(user_id),
                entity_type=EntityType(entity_type),
                name=name,
                content=content,
                source_type=SourceType.MANUAL,
                user_id=user_id,
                parent_versions=[]
            )
            
            stored = await self.store_entity(entity)
            
            return ToolResult(True, {
                "entity": stored.to_dict(),
                "created": True
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
        """Create relationship between entities"""
        try:
            # Verify entities exist
            from_entity = await self.get_entity(from_entity_id)
            to_entity = await self.get_entity(to_entity_id)
            
            if not from_entity:
                return ToolResult(False, None, f"From entity {from_entity_id} not found")
            if not to_entity:
                return ToolResult(False, None, f"To entity {to_entity_id} not found")
            
            from uuid import uuid4
            
            relationship = EntityRelationship(
                id=str(uuid4()),
                from_entity_id=from_entity_id,
                from_entity_version=from_entity.version,
                to_entity_id=to_entity_id,
                to_entity_version=to_entity.version,
                relationship_type=RelationshipType(relationship_type),
                properties=properties or {},
                user_id=user_id
            )
            
            # Validate relationship
            if not relationship.is_valid_for_entities(from_entity, to_entity):
                return ToolResult(
                    False, 
                    None, 
                    f"Invalid relationship: {from_entity.entity_type.value} "
                    f"cannot have {relationship_type} relationship to {to_entity.entity_type.value}"
                )
            
            stored = await self.store_relationship(relationship)
            
            return ToolResult(True, {
                "relationship": {
                    "id": stored.id,
                    "from_entity": {"id": from_entity_id, "name": from_entity.name},
                    "to_entity": {"id": to_entity_id, "name": to_entity.name},
                    "type": relationship_type,
                    "properties": properties
                },
                "created": True
            })
            
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def find_path_tool(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 10
    ) -> ToolResult:
        """Find shortest path between two entities"""
        try:
            path = await self.find_path(from_entity_id, to_entity_id, max_depth)
            
            if not path:
                return ToolResult(True, {
                    "from": from_entity_id,
                    "to": to_entity_id,
                    "path": [],
                    "length": 0,
                    "found": False
                })
            
            return ToolResult(True, {
                "from": from_entity_id,
                "to": to_entity_id,
                "path": [{"id": e.id, "name": e.name, "type": e.entity_type.value} for e in path],
                "length": len(path) - 1,
                "found": True
            })
            
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def get_entity_details_tool(self, entity_id: str) -> ToolResult:
        """Get comprehensive information about an entity"""
        try:
            entity = await self.get_entity(entity_id)
            if not entity:
                return ToolResult(False, None, f"Entity {entity_id} not found")
            
            # Get relationships
            outgoing = await self.get_relationships(from_id=entity_id)
            incoming = await self.get_relationships(to_id=entity_id)
            
            # Get version history
            versions = await self.get_entity_versions(entity_id) if hasattr(self, 'get_entity_versions') else [entity]
            
            return ToolResult(True, {
                "entity": entity.to_dict(),
                "relationships": {
                    "outgoing": [
                        {
                            "to": r.to_entity_id,
                            "type": r.relationship_type.value,
                            "properties": r.properties
                        } for r in outgoing
                    ],
                    "incoming": [
                        {
                            "from": r.from_entity_id,
                            "type": r.relationship_type.value,
                            "properties": r.properties
                        } for r in incoming
                    ]
                },
                "version_count": len(versions),
                "current_version": entity.version
            })
            
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def find_similar_entities_tool(
        self,
        entity_id: str,
        limit: int = 5
    ) -> ToolResult:
        """Find entities similar to a given entity"""
        try:
            similar = await self.find_similar_entities(entity_id, limit)
            
            return ToolResult(True, {
                "reference_entity_id": entity_id,
                "similar_entities": [r.to_dict() for r in similar],
                "count": len(similar)
            })
            
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def get_procedures_for_device_tool(self, device_id: str) -> ToolResult:
        """Get procedures and manuals for a device"""
        try:
            device = await self.get_entity(device_id)
            if not device or device.entity_type != EntityType.DEVICE:
                return ToolResult(False, None, f"Device {device_id} not found")
            
            procedures = []
            manuals = []
            
            # Get procedures
            proc_relationships = await self.get_relationships(
                to_id=device_id,
                rel_type=RelationshipType.PROCEDURE_FOR
            )
            
            for rel in proc_relationships:
                proc = await self.get_entity(rel.from_entity_id)
                if proc and proc.entity_type == EntityType.PROCEDURE:
                    procedures.append({
                        "id": proc.id,
                        "name": proc.name,
                        "content": proc.content
                    })
            
            # Get manuals
            manual_relationships = await self.get_relationships(
                from_id=device_id,
                rel_type=RelationshipType.DOCUMENTED_BY
            )
            
            for rel in manual_relationships:
                manual = await self.get_entity(rel.to_entity_id)
                if manual and manual.entity_type == EntityType.MANUAL:
                    manuals.append({
                        "id": manual.id,
                        "name": manual.name,
                        "content": manual.content
                    })
            
            return ToolResult(True, {
                "device_id": device_id,
                "device_name": device.name,
                "procedures": procedures,
                "manuals": manuals,
                "total_documentation": len(procedures) + len(manuals)
            })
            
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def get_automations_in_room_tool(self, room_id: str) -> ToolResult:
        """Find all automations affecting a room"""
        try:
            room = await self.get_entity(room_id)
            if not room or room.entity_type != EntityType.ROOM:
                return ToolResult(False, None, f"Room {room_id} not found")
            
            # Get devices in room
            device_rels = await self.get_relationships(
                to_id=room_id,
                rel_type=RelationshipType.LOCATED_IN
            )
            
            device_ids = {rel.from_entity_id for rel in device_rels}
            
            # Find automations that control these devices
            automations = []
            seen_automations = set()
            
            for device_id in device_ids:
                auto_rels = await self.get_relationships(
                    to_id=device_id,
                    rel_type=RelationshipType.AUTOMATES
                )
                
                for rel in auto_rels:
                    if rel.from_entity_id not in seen_automations:
                        automation = await self.get_entity(rel.from_entity_id)
                        if automation and automation.entity_type == EntityType.AUTOMATION:
                            automations.append({
                                "id": automation.id,
                                "name": automation.name,
                                "content": automation.content,
                                "affects_devices": []
                            })
                            seen_automations.add(automation.id)
                
                # Track which devices are affected
                for auto in automations:
                    if auto["id"] in [r.from_entity_id for r in auto_rels]:
                        device = await self.get_entity(device_id)
                        if device:
                            auto["affects_devices"].append({
                                "id": device.id,
                                "name": device.name
                            })
            
            return ToolResult(True, {
                "room_id": room_id,
                "room_name": room.name,
                "automations": automations,
                "automation_count": len(automations)
            })
            
        except Exception as e:
            return ToolResult(False, None, str(e))
    
    async def update_entity_tool(
        self,
        entity_id: str,
        changes: Dict[str, Any],
        user_id: str
    ) -> ToolResult:
        """Update entity (creates new version)"""
        try:
            new_version = await self.update_entity(entity_id, changes, user_id)
            
            return ToolResult(True, {
                "entity_id": entity_id,
                "new_version": new_version.version,
                "changes_applied": changes,
                "parent_versions": new_version.parent_versions
            })
            
        except Exception as e:
            return ToolResult(False, None, str(e))