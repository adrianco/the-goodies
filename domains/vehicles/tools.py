"""The vehicles domain's one handler tool (ADR-012 §2).

Everything else the domain asks is a walk and lives in the manifest as data.
A vehicle's *history* is several walks stitched into one dated timeline, which
is logic -- so it is a handler, taking the ``ops`` it runs against exactly as
the engine's generic executor hands it over.
"""

from typing import Any, Dict, List, Optional

from inbetweenies.mcp.tools import ToolResult, _parse_at, _rel_dict
from inbetweenies.models.relationship import _as_aware


def _type_of(entity) -> str:
    return getattr(entity.entity_type, "value", entity.entity_type)


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


async def get_vehicle_history(ops, vehicle_id: str, at: Optional[str] = None) -> ToolResult:
    """One timeline: purchase, services, parts on and off, issues.

    Every event carries ``when`` (ISO-8601) so the caller can sort or filter;
    the list is returned oldest first. Parts contribute two events per
    interval -- fitted at ``valid_from``, removed at ``valid_to`` when closed --
    which is the interval model read as a story.
    """
    try:
        moment = _parse_at(at)
        vehicle = await ops.get_entity(vehicle_id, at=moment)
        if vehicle is None or _type_of(vehicle) != "vehicle":
            return ToolResult(False, None, f"Vehicle {vehicle_id} not found")

        events: List[Dict[str, Any]] = []

        for rel in await ops.get_relationships(from_id=vehicle_id, rel_type="purchased_via", at=moment):
            purchase = await ops.get_entity(rel.to_entity_id, at=moment)
            if purchase is not None:
                content = purchase.content or {}
                events.append({"when": content.get("date"), "kind": "purchased",
                               "entity": purchase.to_dict()})

        for rel in await ops.get_relationships(to_id=vehicle_id, rel_type="service_for", at=moment):
            record = await ops.get_entity(rel.from_entity_id, at=moment)
            if record is not None:
                content = record.content or {}
                events.append({"when": content.get("performed_at"), "kind": "serviced",
                               "entity": record.to_dict()})

        # Parts: every interval ever, so a part that came off still tells its
        # story. As of `at`, only intervals that had started by then.
        for rel in await ops.get_relationships(to_id=vehicle_id, rel_type="fitted_to",
                                               include_all_versions=True):
            # SQLite hands back naive UTC; compare on the aware axis.
            started = _as_aware(rel.valid_from) if rel.valid_from is not None else None
            ended = _as_aware(rel.valid_to) if rel.valid_to is not None else None
            if moment is not None and started is not None and started > moment:
                continue
            part = await ops.get_entity(rel.from_entity_id, at=moment)
            if part is None:
                continue
            events.append({"when": _iso(rel.valid_from), "kind": "part_fitted",
                           "entity": part.to_dict(), "edge": _rel_dict(rel)})
            if ended is not None and (moment is None or ended <= moment):
                events.append({"when": _iso(rel.valid_to), "kind": "part_removed",
                               "entity": part.to_dict(), "edge": _rel_dict(rel)})

        for rel in await ops.get_relationships(to_id=vehicle_id, rel_type="issue_for", at=moment):
            issue = await ops.get_entity(rel.from_entity_id, at=moment)
            if issue is not None:
                content = issue.content or {}
                events.append({"when": content.get("opened_at"), "kind": "issue_opened",
                               "entity": issue.to_dict()})
                if content.get("status") == "resolved" and content.get("resolved_at"):
                    events.append({"when": content.get("resolved_at"), "kind": "issue_resolved",
                                   "entity": issue.to_dict()})

        events.sort(key=lambda e: (e["when"] or "", e["kind"]))
        return ToolResult(True, {
            "vehicle_id": vehicle_id,
            "anchor": {"id": vehicle.id, "name": vehicle.name, "type": "vehicle"},
            "events": events,
            "count": len(events),
            "as_of": at,
        })
    except Exception as e:
        return ToolResult(False, None, str(e))
