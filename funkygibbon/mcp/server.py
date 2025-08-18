"""
MCP Server Implementation for FunkyGibbon

This module implements the MCP server that exposes graph operations
as tools for AI agents and external systems.
"""

from typing import Dict, Any, Optional, List
import logging

from ..graph.index import GraphIndex
from ..repositories.graph_impl import SQLGraphOperations
from .tools import MCP_TOOLS


logger = logging.getLogger(__name__)


class FunkyGibbonMCPServer:
    """MCP server exposing graph operations"""

    def __init__(self, graph_index: GraphIndex, graph_ops: SQLGraphOperations):
        self.graph = graph_index
        self.graph_ops = graph_ops
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
        result = await self.graph_ops.get_devices_in_room(room_id)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_find_device_controls(self, device_id: str) -> Dict[str, Any]:
        """Get controls for a device"""
        result = await self.graph_ops.find_device_controls(device_id)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_get_room_connections(self, room_id: str) -> Dict[str, Any]:
        """Find connections between rooms"""
        result = await self.graph_ops.get_room_connections(room_id)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_search_entities(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Search for entities"""
        result = await self.graph_ops.search_entities_tool(query, entity_types, limit)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_create_entity(
        self,
        entity_type: str,
        name: str,
        content: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new entity"""
        result = await self.graph_ops.create_entity_tool(
            entity_type=entity_type,
            name=name,
            content=content or {},
            user_id="mcp-user"
        )
        if result.success:
            # Update in-memory index
            entity = await self.graph_ops.get_entity(result.result["entity"]["id"])
            if entity:
                self.graph._add_entity(entity)
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_create_relationship(
        self,
        from_entity_id: str,
        to_entity_id: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a relationship between entities"""
        result = await self.graph_ops.create_relationship_tool(
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            relationship_type=relationship_type,
            properties=properties,
            user_id="mcp-user"
        )
        if result.success:
            # Update in-memory index
            rels = await self.graph_ops.get_relationships(
                from_id=from_entity_id,
                to_id=to_entity_id
            )
            for rel in rels:
                if rel.relationship_type.value == relationship_type:
                    self.graph._add_relationship(rel)
                    break
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_find_path(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 10
    ) -> Dict[str, Any]:
        """Find path between entities"""
        result = await self.graph_ops.find_path_tool(from_entity_id, to_entity_id, max_depth)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_get_entity_details(
        self,
        entity_id: str,
        include_relationships: bool = True,
        include_connected: bool = False
    ) -> Dict[str, Any]:
        """Get detailed entity information"""
        result = await self.graph_ops.get_entity_details_tool(entity_id)
        if result.success:
            # Add connected entities if requested
            if include_connected:
                connected = self.graph.get_connected_entities(entity_id)
                result.result["connected_entities"] = [
                    {
                        "entity": conn["entity"].to_dict(),
                        "relationship_type": conn["relationship"].relationship_type.value,
                        "direction": conn["direction"]
                    }
                    for conn in connected
                ]
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_find_similar_entities(
        self,
        entity_id: str,
        threshold: float = 0.7,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Find similar entities"""
        result = await self.graph_ops.find_similar_entities_tool(entity_id, limit)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_get_procedures_for_device(self, device_id: str) -> Dict[str, Any]:
        """Get procedures and manuals for a device"""
        result = await self.graph_ops.get_procedures_for_device_tool(device_id)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_get_automations_in_room(self, room_id: str) -> Dict[str, Any]:
        """Get automations affecting a room"""
        result = await self.graph_ops.get_automations_in_room_tool(room_id)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_update_entity(
        self,
        entity_id: str,
        changes: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Update an entity (creates new version)"""
        result = await self.graph_ops.update_entity_tool(entity_id, changes, user_id)
        if result.success:
            # Update in-memory index
            entity = await self.graph_ops.get_entity(entity_id)
            if entity:
                self.graph._add_entity(entity)
            return result.result
        else:
            raise Exception(result.error)
