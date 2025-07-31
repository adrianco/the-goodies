"""
MCP API Router

This module provides REST endpoints for MCP tool execution.
"""

from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ...database import get_db
from ...repositories.graph_impl import SQLGraphOperations
from ...graph.index import GraphIndex
from ...mcp.server import FunkyGibbonMCPServer
from ..routers.graph import get_graph_index


class MCPToolCall(BaseModel):
    """Schema for MCP tool execution request"""
    arguments: Dict[str, Any]


# Create router
router = APIRouter(prefix="/mcp", tags=["mcp"])

# MCP server instance (in production, this would be a singleton service)
_mcp_server: Optional[FunkyGibbonMCPServer] = None


async def get_mcp_server(
    db: AsyncSession = Depends(get_db),
    graph: GraphIndex = Depends(get_graph_index)
) -> FunkyGibbonMCPServer:
    """Get or create the MCP server instance"""
    global _mcp_server
    
    if _mcp_server is None:
        graph_ops = SQLGraphOperations(db)
        _mcp_server = FunkyGibbonMCPServer(graph, graph_ops)
    
    return _mcp_server


@router.get("/tools", response_model=Dict[str, Any])
async def list_available_tools(
    mcp: FunkyGibbonMCPServer = Depends(get_mcp_server)
):
    """List all available MCP tools"""
    tools = mcp.get_available_tools()
    
    return {
        "tools": tools,
        "count": len(tools)
    }


@router.post("/tools/{tool_name}", response_model=Dict[str, Any])
async def execute_mcp_tool(
    tool_name: str,
    tool_call: MCPToolCall,
    mcp: FunkyGibbonMCPServer = Depends(get_mcp_server)
):
    """Execute an MCP tool and return results"""
    result = await mcp.handle_tool_call(tool_name, tool_call.arguments)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.get("/tools/{tool_name}", response_model=Dict[str, Any])
async def get_tool_details(
    tool_name: str,
    mcp: FunkyGibbonMCPServer = Depends(get_mcp_server)
):
    """Get details about a specific MCP tool"""
    if tool_name not in mcp.tools:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    
    return mcp.tools[tool_name]