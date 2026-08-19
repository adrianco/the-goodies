"""
Blowing-Off MCP Server

A stdio MCP server that exposes the home knowledge-graph tools backed by the
Blowing-Off local cache. It mirrors the TypeScript port's KittenKong MCP server
(rolandcanyon-cmd/the-goodies-typescript): on startup it connects to a
FunkyGibbon server, syncs the graph into the local database, keeps it fresh with
background sync, and serves the same tools to any MCP client (e.g. Claude
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

from inbetweenies.mcp.catalog import MCP_TOOLS_SPEC

from ..client import BlowingOffClient

_ENTITY_TYPES = ("home, room, device, zone, door, window, procedure, manual, "
                 "note, schedule, automation")
# The knowledge-graph tools, built from the canonical catalog in inbetweenies.
#
# This list used to be written out here by hand, duplicating the schemas the
# REST wrapper kept in funkygibbon/mcp/tools.py. Nothing made the two agree, so
# a tool added to one was silently missing from the other -- which is how the
# surface came to lack any way to attach a photo while the REST side had one.
#
# The earlier note here argued against re-deriving these from Python signatures.
# That still holds and this does not do it: the catalog is the same explicit
# schema, written once. types.Tool takes input_schema, which is exactly what
# ToolSpec.as_mcp() renders.
TOOLS: List[types.Tool] = [
    types.Tool(
        name=spec["name"],
        description=spec["description"],
        input_schema=spec["inputSchema"],
    )
    for spec in MCP_TOOLS_SPEC
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
    """Build the MCP Server wired to a (connected) Blowing-Off client.

    MCP 2.x removed the ``@server.list_tools()`` / ``@server.call_tool()``
    decorators from the low-level ``Server``; handlers are now passed as the
    ``on_list_tools`` / ``on_call_tool`` constructor callbacks, which receive a
    ``ServerRequestContext`` plus the already-validated request params and
    return the full result model. We keep an explicit ``TOOLS`` list rather
    than moving to the high-level ``MCPServer``: these schemas are the
    specification mirrored from the KittenKong TypeScript server, not something
    to re-derive from Python signatures. They are now built from the shared
    catalog so the REST wrapper and this server cannot drift apart.
    """

    async def on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=TOOLS)

    async def on_call_tool(ctx: Any, params: Any) -> types.CallToolResult:
        arguments: Optional[Dict[str, Any]] = params.arguments
        result = await client.execute_mcp_tool(params.name, **(arguments or {}))
        payload = result_payload(result)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]
        )

    return Server(
        "blowingoff",
        version="0.3.0",  # keyword-only since MCP 2.0
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


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
