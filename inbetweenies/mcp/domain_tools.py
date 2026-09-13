"""Run a domain's declared tools against any GraphOperations (ADR-012 §2).

A domain declares its query tools as data (:class:`inbetweenies.domain.DomainTool`):
an anchor entity, a relationship walk, a type filter. This module is the one
place that turns such a declaration into a schema for the catalog and into an
execution against whatever ``GraphOperations`` the caller has -- FunkyGibbon's
SQL store, a replica's local store, or a test double. The engine therefore runs
``get_devices_in_room`` and ``get_parts_on_vehicle`` with the same code and
different constants, which is the whole point: a new domain adds tools without
adding engine code.

Every walk is as-of aware (ADR-004 §3): ``at`` is threaded through each
``get_entity`` / ``get_relationships`` call, so "what was fitted to the car
in March" is the same query as "what is fitted now".
"""

from typing import Any, Dict, List

from ..domain import DomainManifest, DomainTool, Walk
from .catalog import ToolSpec, _AT_PARAM
from .tools import ToolResult, _parse_at


def domain_tool_spec(tool: DomainTool) -> ToolSpec:
    """The catalog entry for a declared tool."""
    kinds = "/".join(tool.anchor_types) if tool.anchor_types else "entity"
    properties: Dict[str, Any] = {
        tool.anchor: {"type": "string", "description": f"The id of the {kinds}"},
    }
    for name, schema in tool.extra_params.items():
        properties[name] = dict(schema)
    properties["at"] = _AT_PARAM
    return ToolSpec(
        name=tool.name,
        description=tool.description,
        parameters={
            "type": "object",
            "properties": properties,
            "required": [tool.anchor, *tool.required],
        },
    )


def domain_tool_specs(manifest: DomainManifest) -> List[ToolSpec]:
    return [domain_tool_spec(t) for t in manifest.tools]


def _type_of(entity) -> str:
    return getattr(entity.entity_type, "value", entity.entity_type)


def _matches(entity, hop: Walk) -> bool:
    if hop.target_types and _type_of(entity) not in hop.target_types:
        return False
    content = entity.content or {}
    return all(content.get(k) == v for k, v in hop.where.items())


async def _hop(ops, frontier: List[Any], hop: Walk, moment) -> List[Any]:
    """Every live entity one ``hop`` away from any entity in ``frontier``."""
    found: Dict[str, Any] = {}
    for current in frontier:
        edges = []
        if hop.direction in ("incoming", "both"):
            edges += [(rel.from_entity_id, rel) for rel in
                      await ops.get_relationships(to_id=current.id, rel_type=hop.relationship, at=moment)]
        if hop.direction in ("outgoing", "both"):
            edges += [(rel.to_entity_id, rel) for rel in
                      await ops.get_relationships(from_id=current.id, rel_type=hop.relationship, at=moment)]
        for other_id, _ in edges:
            if other_id in found:
                continue
            other = await ops.get_entity(other_id, at=moment)
            # A tombstoned endpoint is not part of the graph even if the edge
            # that reaches it is still open (same rule as find_path).
            if other is None or getattr(other, "is_tombstone", False):
                continue
            if _matches(other, hop):
                found[other_id] = other
    return list(found.values())


async def run_domain_tool(ops, tool: DomainTool, arguments: Dict[str, Any]) -> ToolResult:
    """Execute one declared tool against ``ops``.

    A handler tool is simply called. A walk tool resolves the anchor, checks
    its type, follows each hop in turn, and returns the final frontier sorted
    by name so results are stable across stores.
    """
    try:
        if tool.handler is not None:
            result = await tool.handler(ops, **arguments)
            return result if isinstance(result, ToolResult) else ToolResult(True, result)

        args = dict(arguments)
        at = args.pop("at", None)
        anchor_id = args.pop(tool.anchor, None)
        if anchor_id is None:
            return ToolResult(False, None, f"{tool.name} requires {tool.anchor}")
        if args:
            return ToolResult(False, None, f"{tool.name} does not accept {sorted(args)}")

        moment = _parse_at(at)
        anchor = await ops.get_entity(anchor_id, at=moment)
        if anchor is None or getattr(anchor, "is_tombstone", False) or (
            tool.anchor_types and _type_of(anchor) not in tool.anchor_types
        ):
            kinds = "/".join(tool.anchor_types) or "entity"
            return ToolResult(False, None, f"{kinds.capitalize()} {anchor_id} not found")

        frontier = [anchor]
        for hop in tool.walk:
            frontier = await _hop(ops, frontier, hop, moment)
        frontier.sort(key=lambda e: ((e.name or ""), e.id))

        return ToolResult(True, {
            tool.anchor: anchor_id,
            "anchor": {"id": anchor.id, "name": anchor.name, "type": _type_of(anchor)},
            tool.result_key: [e.to_dict() for e in frontier],
            "count": len(frontier),
            "as_of": at,
        })
    except Exception as e:  # the tool contract: failures are results, not raises
        return ToolResult(False, None, str(e))
