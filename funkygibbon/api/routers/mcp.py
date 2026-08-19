"""
MCP API Router

This module provides REST endpoints for MCP tool execution.
"""

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ...database import get_db
from ...repositories.graph_impl import SQLGraphOperations
from ...graph.index import GraphIndex
from ...mcp.server import FunkyGibbonMCPServer
from ..dependencies import get_graph_index


class MCPToolCall(BaseModel):
    """Schema for MCP tool execution request"""
    arguments: Dict[str, Any]


# Create router
router = APIRouter(prefix="/mcp", tags=["mcp"])


async def get_mcp_server(
    db: AsyncSession = Depends(get_db),
    graph: GraphIndex = Depends(get_graph_index)
) -> FunkyGibbonMCPServer:
    """Build the MCP server for this request.

    Constructed per request rather than cached in a module global: the server
    binds a database session, and a cached instance kept serving the *first*
    request's session forever. The graph index it wraps is the application's one
    index (ADR-003) -- the same object every time, kept current by write-through
    and the drift check -- so there is nothing expensive to cache here.
    """
    return FunkyGibbonMCPServer(graph, SQLGraphOperations(db))


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
    mcp: FunkyGibbonMCPServer = Depends(get_mcp_server),
    db: AsyncSession = Depends(get_db),
):
    """Execute an MCP tool and return results.

    The commit is the point. `get_db` never commits and the graph operations
    only *flush*, so until now every write through this endpoint was rolled
    back when the session closed: create_entity and create_relationship
    returned success and persisted nothing. (update_entity appeared to work
    only because it commits internally.) The graph router has always committed
    explicitly -- these two routers simply disagreed, and MCP was the one that
    lost. That is a plausible reason callers reached for the REST API and built
    their own helper instead.

    FastAPI caches dependencies per request, so this is the same session the
    tool just wrote through.
    """
    result = await mcp.handle_tool_call(tool_name, tool_call.arguments)

    if "error" in result:
        await db.rollback()
        raise HTTPException(status_code=400, detail=result["error"])

    await db.commit()
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
