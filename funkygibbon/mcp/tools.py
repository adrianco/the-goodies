"""MCP tool definitions for FunkyGibbon.

The schemas live in :mod:`inbetweenies.mcp.catalog` -- the engine's tools --
and a domain's own tools in its manifest (ADR-012 §2). ``tools_for(manifest)``
renders the full set in the shape ``GET /api/v1/mcp/tools`` has always
returned (a ``parameters`` key, not the MCP spec's ``inputSchema``).

There is no module-level list any more: which tools exist depends on which
domain the server is configured to serve, and a house server must not
advertise ``get_parts_on_vehicle`` any more than a vehicles server should
advertise ``get_devices_in_room``.
"""

from typing import Any, Dict, List

from inbetweenies.domain import DomainManifest
from inbetweenies.mcp.catalog import rest_tools_for


def tools_for(manifest: DomainManifest) -> List[Dict[str, Any]]:
    return rest_tools_for(manifest)


__all__ = ["tools_for"]
