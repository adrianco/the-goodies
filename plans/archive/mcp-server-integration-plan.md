# MCP Server Integration Plan

## Overview
This document provides a detailed plan for integrating Model Context Protocol (MCP) server capabilities into FunkyGibbon, enabling AI assistants to interact with the smart home knowledge graph through standardized tools.

## Architecture Overview

### MCP Server Components
1. **Tool Registry**: Defines available MCP tools and their schemas
2. **Request Handler**: Processes incoming MCP requests
3. **Response Builder**: Formats responses according to MCP spec
4. **Graph Interface**: Connects MCP tools to graph operations
5. **Security Layer**: Validates and authorizes tool usage

## Implementation Plan

### Phase 1: Core MCP Infrastructure (Days 1-2)

#### 1.1 MCP Protocol Models
```python
# funkygibbon/mcp/models.py
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from enum import Enum

class MCPError(BaseModel):
    """MCP error response"""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

class MCPToolParameter(BaseModel):
    """Tool parameter definition"""
    name: str
    type: str
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Optional[Any] = None

class MCPTool(BaseModel):
    """MCP tool definition"""
    name: str
    description: str
    parameters: List[MCPToolParameter]
    returns: Dict[str, Any]
    examples: Optional[List[Dict[str, Any]]] = None

class MCPRequest(BaseModel):
    """Incoming MCP request"""
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any]
    id: Optional[str] = None

class MCPResponse(BaseModel):
    """MCP response"""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[MCPError] = None
    id: Optional[str] = None
```

#### 1.2 Tool Registry
```python
# funkygibbon/mcp/registry.py
class ToolRegistry:
    """Registry of available MCP tools"""
    
    def __init__(self):
        self.tools: Dict[str, MCPTool] = {}
        self.handlers: Dict[str, Callable] = {}
        
    def register_tool(self, tool: MCPTool, handler: Callable):
        """Register a tool with its handler"""
        self.tools[tool.name] = tool
        self.handlers[tool.name] = handler
        
    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get tool definition"""
        return self.tools.get(name)
        
    def list_tools(self) -> List[MCPTool]:
        """List all available tools"""
        return list(self.tools.values())
```

### Phase 2: Core Tool Implementations (Days 2-4)

#### 2.1 Graph Query Tools
```python
# funkygibbon/mcp/tools/graph_query.py
from typing import List, Dict, Any
from ...graph import GraphIndex
from ...models import EntityType, RelationshipType

class GraphQueryTools:
    """MCP tools for querying the knowledge graph"""
    
    def __init__(self, graph: GraphIndex):
        self.graph = graph
    
    async def get_devices_in_room(self, room_name: str) -> Dict[str, Any]:
        """
        Get all devices located in a specific room.
        
        Returns:
        {
            "room": {"id": "...", "name": "..."},
            "devices": [
                {"id": "...", "name": "...", "type": "...", "state": {...}}
            ]
        }
        """
        # Find room entity
        room = await self.graph.find_entity_by_name(room_name, EntityType.ROOM)
        if not room:
            return {"error": f"Room '{room_name}' not found"}
        
        # Get devices in room
        devices = await self.graph.get_related_entities(
            room.id, RelationshipType.LOCATED_IN, reverse=True
        )
        
        return {
            "room": room.to_dict(),
            "devices": [d.to_dict() for d in devices if d.entity_type == EntityType.DEVICE]
        }
    
    async def find_device_controls(self, device_name: str) -> Dict[str, Any]:
        """
        Get available controls and current state for a device.
        
        Returns:
        {
            "device": {"id": "...", "name": "..."},
            "controls": [
                {"name": "power", "type": "boolean", "value": true},
                {"name": "brightness", "type": "integer", "value": 75}
            ],
            "services": ["lightbulb", "color_temperature"]
        }
        """
        device = await self.graph.find_entity_by_name(device_name, EntityType.DEVICE)
        if not device:
            return {"error": f"Device '{device_name}' not found"}
        
        # Extract control information from device content
        controls = []
        services = []
        
        if "services" in device.content:
            for service in device.content["services"]:
                services.append(service["type"])
                for char in service.get("characteristics", []):
                    controls.append({
                        "name": char["type"],
                        "type": char.get("format", "unknown"),
                        "value": char.get("value"),
                        "writable": char.get("perms", []).count("pw") > 0
                    })
        
        return {
            "device": device.to_dict(),
            "controls": controls,
            "services": services
        }
    
    async def get_room_connections(self, from_room: str, 
                                  to_room: Optional[str] = None) -> Dict[str, Any]:
        """
        Find doors and passages between rooms.
        
        Returns:
        {
            "from_room": {"id": "...", "name": "..."},
            "connections": [
                {
                    "to_room": {"id": "...", "name": "..."},
                    "via": {"id": "...", "name": "...", "type": "door"},
                    "path": ["room1", "door1", "room2"]
                }
            ]
        }
        """
        from_entity = await self.graph.find_entity_by_name(from_room, EntityType.ROOM)
        if not from_entity:
            return {"error": f"Room '{from_room}' not found"}
        
        if to_room:
            # Find specific path
            to_entity = await self.graph.find_entity_by_name(to_room, EntityType.ROOM)
            if not to_entity:
                return {"error": f"Room '{to_room}' not found"}
            
            path = await self.graph.find_path(from_entity.id, to_entity.id)
            return {
                "from_room": from_entity.to_dict(),
                "to_room": to_entity.to_dict(),
                "path": path
            }
        else:
            # Find all connections
            connections = await self.graph.get_room_connections(from_entity.id)
            return {
                "from_room": from_entity.to_dict(),
                "connections": connections
            }
```

#### 2.2 Entity Management Tools
```python
# funkygibbon/mcp/tools/entity_management.py
class EntityManagementTools:
    """MCP tools for creating and managing entities"""
    
    async def create_entity(self, entity_type: str, name: str, 
                          properties: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new entity in the knowledge graph"""
        
    async def update_entity(self, entity_id: str, 
                          updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update entity properties (creates new version)"""
        
    async def create_relationship(self, from_entity_id: str, 
                                to_entity_id: str,
                                relationship_type: str,
                                properties: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create relationship between entities"""
```

#### 2.3 Content Management Tools
```python
# funkygibbon/mcp/tools/content_management.py
class ContentManagementTools:
    """MCP tools for managing documentation and procedures"""
    
    async def add_device_manual(self, device_id: str, title: str, 
                              content: str, format: str = "markdown") -> Dict[str, Any]:
        """Add manual/documentation for a device"""
        
    async def create_procedure(self, title: str, steps: List[str], 
                             category: str, related_entities: List[str] = None) -> Dict[str, Any]:
        """Create a step-by-step procedure"""
        
    async def add_device_image(self, device_id: str, image_data: str, 
                             caption: str = None) -> Dict[str, Any]:
        """Add image for a device (base64 encoded)"""
```

#### 2.4 Search Tools
```python
# funkygibbon/mcp/tools/search.py
class SearchTools:
    """MCP tools for searching the knowledge graph"""
    
    async def search_entities(self, query: str, 
                            entity_types: List[str] = None,
                            limit: int = 10) -> Dict[str, Any]:
        """Search for entities by name or content"""
        
    async def find_procedures(self, category: str = None,
                            related_to: str = None) -> Dict[str, Any]:
        """Find procedures by category or related entity"""
        
    async def get_entity_history(self, entity_id: str) -> Dict[str, Any]:
        """Get version history for an entity"""
```

### Phase 3: MCP Server Implementation (Days 4-5)

#### 3.1 MCP Server Core
```python
# funkygibbon/mcp/server.py
class MCPServer:
    """Main MCP server implementation"""
    
    def __init__(self, graph_index: GraphIndex):
        self.graph = graph_index
        self.registry = ToolRegistry()
        self._register_all_tools()
        
    def _register_all_tools(self):
        """Register all available tools"""
        # Graph query tools
        graph_tools = GraphQueryTools(self.graph)
        self.registry.register_tool(
            MCPTool(
                name="get_devices_in_room",
                description="Get all devices located in a specific room",
                parameters=[
                    MCPToolParameter(
                        name="room_name",
                        type="string",
                        description="Name of the room"
                    )
                ],
                returns={"type": "object"}
            ),
            graph_tools.get_devices_in_room
        )
        # ... register other tools
    
    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """Handle incoming MCP request"""
        try:
            if request.method == "tools/list":
                return self._handle_list_tools(request)
            elif request.method.startswith("tools/call/"):
                tool_name = request.method.replace("tools/call/", "")
                return await self._handle_tool_call(tool_name, request)
            else:
                return self._error_response(
                    request.id,
                    -32601,
                    f"Method not found: {request.method}"
                )
        except Exception as e:
            return self._error_response(
                request.id,
                -32603,
                f"Internal error: {str(e)}"
            )
    
    async def _handle_tool_call(self, tool_name: str, 
                               request: MCPRequest) -> MCPResponse:
        """Execute a tool and return result"""
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return self._error_response(
                request.id,
                -32602,
                f"Tool not found: {tool_name}"
            )
        
        # Validate parameters
        handler = self.registry.handlers[tool_name]
        try:
            result = await handler(**request.params)
            return MCPResponse(id=request.id, result=result)
        except TypeError as e:
            return self._error_response(
                request.id,
                -32602,
                f"Invalid parameters: {str(e)}"
            )
```

#### 3.2 FastAPI Integration
```python
# funkygibbon/api/routers/mcp.py
from fastapi import APIRouter, Depends, HTTPException
from ...mcp import MCPServer, MCPRequest, MCPResponse

router = APIRouter()

@router.post("/")
async def handle_mcp_request(
    request: MCPRequest,
    mcp_server: MCPServer = Depends(get_mcp_server)
) -> MCPResponse:
    """Handle MCP protocol requests"""
    return await mcp_server.handle_request(request)

@router.get("/tools")
async def list_tools(mcp_server: MCPServer = Depends(get_mcp_server)):
    """List available MCP tools"""
    return {
        "tools": [tool.dict() for tool in mcp_server.registry.list_tools()]
    }

@router.get("/tools/{tool_name}")
async def get_tool_info(
    tool_name: str,
    mcp_server: MCPServer = Depends(get_mcp_server)
):
    """Get detailed information about a specific tool"""
    tool = mcp_server.registry.get_tool(tool_name)
    if not tool:
        raise HTTPException(404, f"Tool not found: {tool_name}")
    return tool.dict()
```

### Phase 4: Testing and Documentation (Days 5-6)

#### 4.1 Tool Testing
```python
# tests/mcp/test_tools.py
import pytest
from funkygibbon.mcp import MCPServer

@pytest.mark.asyncio
async def test_get_devices_in_room(mcp_server, sample_graph):
    """Test device query tool"""
    request = MCPRequest(
        method="tools/call/get_devices_in_room",
        params={"room_name": "Living Room"},
        id="test-1"
    )
    
    response = await mcp_server.handle_request(request)
    assert response.error is None
    assert "devices" in response.result
    assert len(response.result["devices"]) > 0
```

#### 4.2 Tool Documentation
```markdown
# MCP Tools Documentation

## get_devices_in_room
Get all devices located in a specific room.

**Parameters:**
- `room_name` (string, required): Name of the room

**Returns:**
```json
{
  "room": {
    "id": "uuid",
    "name": "Living Room"
  },
  "devices": [
    {
      "id": "uuid",
      "name": "Ceiling Light",
      "type": "lightbulb",
      "state": {...}
    }
  ]
}
```

**Example:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call/get_devices_in_room",
  "params": {
    "room_name": "Living Room"
  },
  "id": "1"
}
```
```

### Phase 5: Advanced Features (Week 2)

#### 5.1 Streaming Support
```python
# funkygibbon/mcp/streaming.py
class StreamingMCPServer(MCPServer):
    """MCP server with streaming support"""
    
    async def handle_streaming_request(self, request: MCPRequest):
        """Handle requests that return streaming responses"""
        if request.method == "tools/call/monitor_device":
            async for update in self._monitor_device(request.params):
                yield MCPResponse(
                    id=request.id,
                    result={"type": "stream", "data": update}
                )
```

#### 5.2 Batch Operations
```python
# funkygibbon/mcp/batch.py
class BatchMCPRequest(BaseModel):
    """Batch MCP request"""
    requests: List[MCPRequest]
    
class BatchMCPResponse(BaseModel):
    """Batch MCP response"""
    responses: List[MCPResponse]
```

## Security Considerations

### Authentication
- API key validation for MCP endpoints
- User context propagation to tools
- Rate limiting per API key

### Authorization
- Tool-level permissions
- Entity-level access control
- Audit logging for all tool calls

### Input Validation
- Strict parameter validation
- SQL injection prevention
- Size limits for binary content

## Performance Optimization

### Caching
- Cache tool definitions
- Cache frequently accessed entities
- Implement ETag support

### Async Operations
- All tools use async/await
- Connection pooling for database
- Background task processing

## Monitoring and Analytics

### Metrics to Track
- Tool usage frequency
- Response times per tool
- Error rates and types
- Popular query patterns

### Logging
```python
# funkygibbon/mcp/logging.py
import structlog

logger = structlog.get_logger()

class LoggingMCPServer(MCPServer):
    """MCP server with comprehensive logging"""
    
    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        logger.info("mcp_request", method=request.method, id=request.id)
        start = time.time()
        
        try:
            response = await super().handle_request(request)
            logger.info("mcp_response", 
                       method=request.method,
                       duration=time.time() - start,
                       success=response.error is None)
            return response
        except Exception as e:
            logger.error("mcp_error", 
                        method=request.method,
                        error=str(e))
            raise
```

## Success Criteria

1. **Functionality**: All defined tools work correctly
2. **Performance**: <50ms response time for simple queries
3. **Reliability**: >99.9% uptime for MCP endpoints
4. **Usability**: Clear documentation and examples
5. **Security**: No unauthorized data access

## Timeline

### Week 1
- Days 1-2: Core MCP infrastructure
- Days 2-4: Tool implementations
- Days 4-5: Server implementation and API integration

### Week 2
- Days 1-2: Testing and documentation
- Days 3-4: Advanced features
- Day 5: Performance optimization and monitoring

## Next Steps

1. Deploy MCP server to staging environment
2. Test with AI assistants (Claude, GPT-4)
3. Gather feedback and iterate on tools
4. Add domain-specific tools based on usage
5. Consider MCP federation for multi-home support