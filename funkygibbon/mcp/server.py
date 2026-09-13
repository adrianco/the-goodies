"""
MCP Server Implementation for FunkyGibbon

This module implements the MCP server that exposes graph operations
as tools for AI agents and external systems.
"""

from typing import Dict, Any, Optional, List
import logging

from ..graph.index import GraphIndex
from ..graph.index_service import GraphIndexService
from ..repositories.graph_impl import SQLGraphOperations
from .tools import MCP_TOOLS


logger = logging.getLogger(__name__)


class FunkyGibbonMCPServer:
    """MCP server exposing graph operations"""

    def __init__(self, graph_index: GraphIndex, graph_ops: SQLGraphOperations,
                 index_service: Optional["GraphIndexService"] = None):
        self.graph = graph_index
        self.graph_ops = graph_ops
        # ADR-003 decision 2: writes go through the service so the index is
        # patched AND its storage marker re-read. Patching `self.graph`
        # directly (the old way, still the fallback when no service is given)
        # left the marker behind, so the next read saw drift and rebuilt --
        # correct, but a full rebuild on every MCP edge write.
        self.index_service = index_service
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

    async def _index_entity(self, entity) -> None:
        """Write-through for an entity this server just wrote (ADR-003 decision 2).

        Through the service when we have one, so the storage marker is re-read
        and the drift net does not fire on our own write; patching `self.graph`
        directly -- the old way, still the fallback -- left the marker behind
        and cost a full rebuild on the next read.
        """
        await self.graph_ops.db.commit()
        if self.index_service is not None:
            await self.index_service.entity_written(self.graph_ops.db, entity)
        else:
            self.graph._add_entity(entity)

    async def _handle_get_devices_in_room(self, room_id: str, at: Optional[str] = None) -> Dict[str, Any]:
        """Get all devices in a specific room"""
        result = await self.graph_ops.get_devices_in_room(room_id, at=at)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_find_device_controls(self, device_id: str, at: Optional[str] = None) -> Dict[str, Any]:
        """Get controls for a device"""
        result = await self.graph_ops.find_device_controls(device_id, at=at)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_get_room_connections(self, room_id: str, at: Optional[str] = None) -> Dict[str, Any]:
        """Find connections between rooms"""
        result = await self.graph_ops.get_room_connections(room_id, at=at)
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
        content: Optional[Dict[str, Any]] = None,
        user_id: str = "mcp-user",
    ) -> Dict[str, Any]:
        """Create a new entity"""
        # `user_id` is in the catalog schema and KittenKong has always sent
        # it; this handler used to reject it as an unexpected keyword, which
        # the router turned into a 400 -- so the documented argument failed
        # the call. Every handler accepts what its schema declares.
        result = await self.graph_ops.create_entity_tool(
            entity_type=entity_type,
            name=name,
            content=content or {},
            user_id=user_id or "mcp-user",
        )
        if result.success:
            # Update in-memory index
            entity = await self.graph_ops.get_entity(result.result["entity"]["id"])
            if entity:
                await self._index_entity(entity)
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_create_relationship(
        self,
        from_entity_id: str,
        to_entity_id: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None,
        user_id: str = "mcp-user",
    ) -> Dict[str, Any]:
        """Create a relationship between entities"""
        result = await self.graph_ops.create_relationship_tool(
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            relationship_type=relationship_type,
            properties=properties,
            user_id=user_id or "mcp-user",
        )
        if result.success:
            await self.graph_ops.db.commit()
            rels = await self.graph_ops.get_relationships(
                from_id=from_entity_id,
                to_id=to_entity_id
            )
            for rel in rels:
                if getattr(rel.relationship_type, "value", rel.relationship_type) == relationship_type:
                    if self.index_service is not None:
                        await self.index_service.relationship_written(self.graph_ops.db, rel)
                    else:
                        self.graph._add_relationship(rel)
                    break
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_find_path(
        self,
        from_entity_id: str,
        to_entity_id: str,
        max_depth: int = 10,
        at: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find path between entities"""
        result = await self.graph_ops.find_path_tool(from_entity_id, to_entity_id, max_depth, at=at)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_get_entity_details(
        self,
        entity_id: str,
        include_relationships: bool = True,
        include_connected: bool = False,
        at: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get detailed entity information"""
        result = await self.graph_ops.get_entity_details_tool(entity_id, at=at)
        if result.success:
            # Add connected entities if requested
            if include_connected:
                connected = self.graph.get_connected_entities(entity_id)
                result.result["connected_entities"] = [
                    {
                        "entity": conn["entity"].to_dict(),
                        "relationship_type": getattr(
                            conn["relationship"].relationship_type, "value",
                            conn["relationship"].relationship_type),
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

    async def _handle_get_procedures_for_device(self, device_id: str, at: Optional[str] = None) -> Dict[str, Any]:
        """Get procedures and manuals for a device"""
        result = await self.graph_ops.get_procedures_for_device_tool(device_id, at=at)
        if result.success:
            return result.result
        else:
            raise Exception(result.error)

    async def _handle_get_automations_in_room(self, room_id: str, at: Optional[str] = None) -> Dict[str, Any]:
        """Get automations affecting a room"""
        result = await self.graph_ops.get_automations_in_room_tool(room_id, at=at)
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
                await self._index_entity(entity)
            return result.result
        else:
            raise Exception(result.error)

    # --- Attachments --------------------------------------------------- #

    async def _handle_attach_photo(
        self,
        parent_entity_id: str,
        filename: str,
        data_b64: str,
        mime_type: str = None,
        description: str = None,
        user_id: str = None,
    ) -> Dict[str, Any]:
        """Attach an image as a photo entity linked by has_photo."""
        result = await self.graph_ops.attach_photo(
            parent_entity_id, filename, data_b64, mime_type, description, user_id)
        if not result.success:
            raise Exception(result.error)
        # Write-through, as every other mutating handler does: the index is the
        # application's one index (ADR-003) and a new entity must appear in it
        # without waiting for the drift check.
        attachment = await self.graph_ops.get_entity(result.result["attachment_id"])
        if attachment:
            await self._index_entity(attachment)
        return result.result

    async def _handle_attach_document(
        self,
        parent_entity_id: str,
        filename: str,
        data_b64: str,
        mime_type: str = None,
        description: str = None,
        user_id: str = None,
    ) -> Dict[str, Any]:
        """Attach a PDF as a manual entity linked by documented_by."""
        result = await self.graph_ops.attach_document(
            parent_entity_id, filename, data_b64, mime_type, description, user_id)
        if not result.success:
            raise Exception(result.error)
        attachment = await self.graph_ops.get_entity(result.result["attachment_id"])
        if attachment:
            await self._index_entity(attachment)
        return result.result

    async def _handle_get_blob(self, blob_id: str, include_data: bool = False) -> Dict[str, Any]:
        """Fetch a blob's metadata, and bytes only when asked."""
        result = await self.graph_ops.get_blob_tool(blob_id, include_data)
        if not result.success:
            raise Exception(result.error)
        return result.result

    # --- History and retraction ---------------------------------------- #

    async def _handle_get_entity_versions(self, entity_id: str) -> Dict[str, Any]:
        """Full version history, newest first."""
        result = await self.graph_ops.get_entity_versions_tool(entity_id)
        if not result.success:
            raise Exception(result.error)
        return result.result

    async def _handle_tombstone_entity(
        self,
        entity_id: str,
        reason: str,
        is_error: bool = False,
        user_id: str = None,
    ) -> Dict[str, Any]:
        """Retract an entity by appending a tombstone version.

        Not a delete: the store is append-only, and the earlier versions stay
        readable. The index is refreshed so the retracted entity stops showing
        up in queries immediately.
        """
        result = await self.graph_ops.tombstone_entity(entity_id, reason, is_error, user_id)
        if not result.success:
            raise Exception(result.error)
        entity = await self.graph_ops.get_entity(entity_id)
        if entity:
            await self._index_entity(entity)
        return result.result

    # --- Relationship parity (issue #85) and the as-of surface (ADR-004 §3) ---

    async def _handle_list_relationships(
        self,
        from_entity_id: Optional[str] = None,
        to_entity_id: Optional[str] = None,
        relationship_type: Optional[str] = None,
        include_history: bool = False,
        at: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = await self.graph_ops.list_relationships(
            from_entity_id=from_entity_id, to_entity_id=to_entity_id,
            relationship_type=relationship_type, include_history=include_history, at=at,
        )
        if not result.success:
            raise Exception(result.error)
        return result.result

    async def _handle_get_connected(
        self,
        entity_id: str,
        relationship_type: Optional[str] = None,
        direction: str = "both",
        at: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = await self.graph_ops.get_connected(
            entity_id, relationship_type=relationship_type, direction=direction, at=at
        )
        if not result.success:
            raise Exception(result.error)
        return result.result

    async def _handle_end_relationship(
        self,
        relationship_id: str,
        reason: Optional[str] = None,
        user_id: Optional[str] = None,
        at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """End an edge's interval -- the delete. The index caches `at = now`,
        so a retired edge leaves it here, in the same code path as the write
        (ADR-003 decision 2)."""
        result = await self.graph_ops.end_relationship_tool(
            relationship_id, reason=reason, user_id=user_id or "mcp-user", at=at
        )
        if not result.success:
            raise Exception(result.error)
        await self.graph_ops.db.commit()
        if not result.result.get("already_ended"):
            if self.index_service is not None:
                await self.index_service.relationship_ended(self.graph_ops.db, relationship_id)
            else:
                self.graph.remove_relationship(relationship_id)
        return result.result

    async def _handle_list_entities(
        self, entity_type: Optional[str] = None, limit: int = 100, offset: int = 0,
        at: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = await self.graph_ops.list_entities(entity_type=entity_type, limit=limit,
                                                    offset=offset, at=at)
        if not result.success:
            raise Exception(result.error)
        return result.result

    async def _handle_get_graph_diff(self, since: str, until: Optional[str] = None) -> Dict[str, Any]:
        result = await self.graph_ops.get_graph_diff(since, until)
        if not result.success:
            raise Exception(result.error)
        return result.result

    async def _handle_get_statistics(self) -> Dict[str, Any]:
        """Entity and relationship counts by type."""
        result = await self.graph_ops.get_statistics_tool()
        if not result.success:
            raise Exception(result.error)
        return result.result
