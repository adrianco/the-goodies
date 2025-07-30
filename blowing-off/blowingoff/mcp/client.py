"""
Local MCP client implementation for Blowing-Off.

This provides MCP tool functionality that works with local graph data.
"""

from typing import Dict, Any, List, Optional

from ..graph import LocalGraphOperations, LocalGraphStorage
from inbetweenies.mcp.tools import MCPTools


class LocalMCPClient:
    """
    Local MCP client that uses the shared MCPTools implementation
    with local graph storage.
    """
    
    def __init__(self, storage: Optional[LocalGraphStorage] = None):
        """Initialize with local storage"""
        self.graph_ops = LocalGraphOperations(storage)
        self.tools = {
            "get_devices_in_room": self.graph_ops.get_devices_in_room,
            "find_device_controls": self.graph_ops.find_device_controls,
            "get_room_connections": self.graph_ops.get_room_connections,
            "search_entities": self.graph_ops.search_entities_tool,
            "create_entity": self.graph_ops.create_entity_tool,
            "create_relationship": self.graph_ops.create_relationship_tool,
            "find_path": self.graph_ops.find_path_tool,
            "get_entity_details": self.graph_ops.get_entity_details_tool,
            "find_similar_entities": self.graph_ops.find_similar_entities_tool,
            "get_procedures_for_device": self.graph_ops.get_procedures_for_device_tool,
            "get_automations_in_room": self.graph_ops.get_automations_in_room_tool,
            "update_entity": self.graph_ops.update_entity_tool,
        }
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute an MCP tool locally.
        
        Args:
            tool_name: Name of the tool to execute
            **kwargs: Tool arguments
            
        Returns:
            Tool execution result
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(self.tools.keys())
            }
        
        try:
            # Execute the tool
            result = await self.tools[tool_name](**kwargs)
            
            # Convert ToolResult to dict if needed
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            else:
                return result
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_available_tools(self) -> List[str]:
        """Get list of available MCP tools"""
        return list(self.tools.keys())
    
    async def sync_with_server(self, server_data: Dict[str, Any]):
        """
        Sync local graph data with server data.
        
        Args:
            server_data: Data from server containing entities and relationships
        """
        entities = server_data.get("entities", [])
        relationships = server_data.get("relationships", [])
        
        # Convert dicts to model instances if needed
        from inbetweenies.models import Entity, EntityRelationship
        
        entity_instances = []
        for e in entities:
            if isinstance(e, dict):
                entity_instances.append(Entity(**e))
            else:
                entity_instances.append(e)
        
        relationship_instances = []
        for r in relationships:
            if isinstance(r, dict):
                relationship_instances.append(EntityRelationship(**r))
            else:
                relationship_instances.append(r)
        
        # Sync with local storage
        self.graph_ops.storage.sync_from_server(entity_instances, relationship_instances)
    
    async def demo_local_functionality(self):
        """
        Demonstrate local MCP functionality.
        
        This creates some sample data and shows how the tools work locally.
        """
        print("🔧 Demonstrating Local MCP Functionality")
        print("=" * 50)
        
        # Create a room
        result = await self.execute_tool(
            "create_entity",
            entity_type="room",
            name="Living Room",
            content={"description": "Main living area"},
            user_id="demo-user"
        )
        print(f"\n✅ Created room: {result}")
        
        if result.get("success"):
            room_id = result["result"]["entity"]["id"]
            
            # Create a device
            result = await self.execute_tool(
                "create_entity",
                entity_type="device",
                name="Smart Light",
                content={
                    "capabilities": ["on_off", "brightness", "color"],
                    "manufacturer": "Philips"
                },
                user_id="demo-user"
            )
            print(f"\n✅ Created device: {result}")
            
            if result.get("success"):
                device_id = result["result"]["entity"]["id"]
                
                # Create relationship
                result = await self.execute_tool(
                    "create_relationship",
                    from_entity_id=device_id,
                    to_entity_id=room_id,
                    relationship_type="located_in",
                    properties={"installed_date": "2024-01-15"},
                    user_id="demo-user"
                )
                print(f"\n✅ Created relationship: {result}")
                
                # Get devices in room
                result = await self.execute_tool(
                    "get_devices_in_room",
                    room_id=room_id
                )
                print(f"\n✅ Devices in room: {result}")
                
                # Search for entities
                result = await self.execute_tool(
                    "search_entities",
                    query="Smart",
                    limit=5
                )
                print(f"\n✅ Search results: {result}")
        
        print("\n" + "=" * 50)
        print("Demo complete! Local MCP tools are working.")
    
    def clear_local_data(self):
        """Clear all local graph data"""
        self.graph_ops.storage.clear()