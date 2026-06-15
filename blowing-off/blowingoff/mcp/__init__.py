"""
MCP (Model Context Protocol) for Blowing-Off.

Provides a local MCP client (LocalMCPClient) over local graph operations, and a
stdio MCP *server* (blowingoff.mcp.server) that exposes the 12 knowledge-graph
tools to MCP clients — mirroring the TypeScript KittenKong MCP server.
"""

from .client import LocalMCPClient

__all__ = ['LocalMCPClient']
