"""
Blowing-Off MCP Server

A stdio MCP server that exposes the home knowledge-graph tools backed by the
Blowing-Off local cache. It mirrors the TypeScript port's KittenKong MCP server
(rolandcanyon-cmd/the-goodies-typescript): on startup it connects to a
FunkyGibbon server, syncs the graph into the local database, keeps it fresh with
background sync, and serves the same 12 tools to any MCP client (e.g. Claude
Desktop / Claude Code).

Run as:
    python -m blowingoff.mcp.server

Configuration (environment):
    FUNKYGIBBON_URL            server URL (default http://localhost:8000)
    FUNKYGIBBON_AUTH_TOKEN     bearer token (preferred; from `funkygibbon setup-auth`)
    FUNKYGIBBON_PASSWORD       admin password (used if no token; default "admin")
    SYNC_INTERVAL_SECONDS      background sync interval (default 60)
    BLOWINGOFF_DB              local cache db path (default blowingoff.db)

Example Claude Code mcpServers entry:
    "blowingoff": {
      "command": "python",
      "args": ["-m", "blowingoff.mcp.server"],
      "env": {"FUNKYGIBBON_URL": "http://localhost:8000",
              "FUNKYGIBBON_AUTH_TOKEN": "<token>"}
    }
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from ..client import BlowingOffClient

_ENTITY_TYPES = ("home, room, device, zone, door, window, procedure, manual, "
                 "note, schedule, automation")

# The 12 knowledge-graph tools, matching the KittenKong MCP server surface.
TOOLS: List[types.Tool] = [
    types.Tool(
        name="search_entities",
        description="Search for entities in the home knowledge graph by name or content",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "entity_types": {"type": "array", "items": {"type": "string"},
                                 "description": f"Optional filter by type: {_ENTITY_TYPES}"},
                "limit": {"type": "number", "description": "Max results (default 10)"},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_entity_details",
        description="Get full details for a specific entity by ID, including all relationships",
        inputSchema={
            "type": "object",
            "properties": {"entity_id": {"type": "string", "description": "Entity ID"}},
            "required": ["entity_id"],
        },
    ),
    types.Tool(
        name="create_entity",
        description="Create a new entity in the knowledge graph",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "description": f"Type: {_ENTITY_TYPES}"},
                "name": {"type": "string", "description": "Entity name"},
                "content": {"type": "object", "description": "Entity properties (arbitrary JSON)"},
                "user_id": {"type": "string", "description": "User ID (optional, defaults to mcp-user)"},
            },
            "required": ["entity_type", "name", "content"],
        },
    ),
    types.Tool(
        name="update_entity",
        description="Update an existing entity — creates a new immutable version",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity ID to update"},
                "changes": {"type": "object", "description": "Fields to update in content"},
                "user_id": {"type": "string", "description": "User ID (optional)"},
            },
            "required": ["entity_id", "changes"],
        },
    ),
    types.Tool(
        name="create_relationship",
        description="Create a directed relationship between two entities",
        inputSchema={
            "type": "object",
            "properties": {
                "from_entity_id": {"type": "string", "description": "Source entity ID"},
                "to_entity_id": {"type": "string", "description": "Target entity ID"},
                "relationship_type": {"type": "string",
                                      "description": "e.g. located_in, controls, documented_by, connected_to"},
                "properties": {"type": "object", "description": "Optional relationship properties"},
                "user_id": {"type": "string", "description": "User ID (optional)"},
            },
            "required": ["from_entity_id", "to_entity_id", "relationship_type"],
        },
    ),
    types.Tool(
        name="get_devices_in_room",
        description="Get all devices located in a specific room",
        inputSchema={
            "type": "object",
            "properties": {"room_id": {"type": "string", "description": "Room entity ID"}},
            "required": ["room_id"],
        },
    ),
    types.Tool(
        name="find_device_controls",
        description="Get available controls, automations, and procedures for a device",
        inputSchema={
            "type": "object",
            "properties": {"device_id": {"type": "string", "description": "Device entity ID"}},
            "required": ["device_id"],
        },
    ),
    types.Tool(
        name="get_room_connections",
        description="Find doors, windows, and passages connecting a room to adjacent spaces",
        inputSchema={
            "type": "object",
            "properties": {"room_id": {"type": "string", "description": "Room entity ID"}},
            "required": ["room_id"],
        },
    ),
    types.Tool(
        name="find_path",
        description="Find the relationship path between two entities in the graph",
        inputSchema={
            "type": "object",
            "properties": {
                "from_entity_id": {"type": "string", "description": "Starting entity ID"},
                "to_entity_id": {"type": "string", "description": "Target entity ID"},
                "max_depth": {"type": "number", "description": "Maximum path depth (default 5)"},
            },
            "required": ["from_entity_id", "to_entity_id"],
        },
    ),
    types.Tool(
        name="find_similar_entities",
        description="Find entities similar to a given entity based on type and content",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Reference entity ID"},
                "threshold": {"type": "number", "description": "Similarity threshold 0–1 (default 0.5)"},
                "limit": {"type": "number", "description": "Max results (default 10)"},
            },
            "required": ["entity_id"],
        },
    ),
    types.Tool(
        name="get_procedures_for_device",
        description="Get all procedures, manuals, and instructions for a device",
        inputSchema={
            "type": "object",
            "properties": {"device_id": {"type": "string", "description": "Device entity ID"}},
            "required": ["device_id"],
        },
    ),
    types.Tool(
        name="get_automations_in_room",
        description="Get all automation rules and schedules associated with a room",
        inputSchema={
            "type": "object",
            "properties": {"room_id": {"type": "string", "description": "Room entity ID"}},
            "required": ["room_id"],
        },
    ),
]


def result_payload(result: Any) -> Any:
    """Reduce a client.execute_mcp_tool result to the payload to return: the
    tool's ``result`` on success, an ``{"error": ...}`` object otherwise."""
    if isinstance(result, dict) and result.get("success"):
        return result.get("result")
    if isinstance(result, dict):
        return {"error": result.get("error", "tool failed")}
    return result


def build_server(client: BlowingOffClient) -> Server:
    """Build the MCP Server wired to a (connected) Blowing-Off client."""
    server = Server("blowingoff", "0.2.0")

    @server.list_tools()
    async def list_tools() -> List[types.Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
        result = await client.execute_mcp_tool(name, **(arguments or {}))
        payload = result_payload(result)
        return [types.TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]

    return server


async def serve() -> None:
    server_url = os.environ.get("FUNKYGIBBON_URL", "http://localhost:8000")
    token = os.environ.get("FUNKYGIBBON_AUTH_TOKEN") or None
    password = os.environ.get("FUNKYGIBBON_PASSWORD", "admin")
    interval = int(os.environ.get("SYNC_INTERVAL_SECONDS", "60"))
    db_path = os.environ.get("BLOWINGOFF_DB", "blowingoff.db")

    client = BlowingOffClient(db_path)
    # Prefer a bearer token (from `funkygibbon setup-auth`); fall back to password.
    await client.connect(
        server_url,
        auth_token=token,
        password=None if token else password,
        client_id="blowingoff-mcp-server",
    )
    # Initial sync, then keep the local cache fresh in the background.
    try:
        await client.sync()
    except Exception as exc:  # don't fail startup if the first sync hiccups
        print(f"blowingoff MCP server: initial sync warning: {exc}", file=sys.stderr)
    await client.start_background_sync(interval)

    server = build_server(client)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"blowingoff MCP server fatal error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
