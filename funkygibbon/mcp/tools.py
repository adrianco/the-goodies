"""MCP tool definitions for FunkyGibbon.

The schemas themselves live in :mod:`inbetweenies.mcp.catalog` -- one
definition rendered for both transports. They used to be maintained here *and*
in the stdio server, by hand, with nothing keeping the two in step.

``MCP_TOOLS`` keeps the shape ``GET /api/v1/mcp/tools`` has always returned
(a ``parameters`` key, not the MCP spec's ``inputSchema``), so this indirection
changes nothing a caller can observe.
"""

from typing import Any, Dict, List

from inbetweenies.mcp.catalog import MCP_TOOLS as _CATALOG_REST

MCP_TOOLS: List[Dict[str, Any]] = _CATALOG_REST

__all__ = ["MCP_TOOLS"]
