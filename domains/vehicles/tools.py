"""The vehicles domain's handler tools (ADR-012 §2, ADR-016).

Everything else the domain asks is a walk and lives in the manifest as data.
These two read the *timeline* — events, part intervals, moves between
locations — which is several walks stitched into one dated list, and that is
logic. They take the ``ops`` they run against exactly as the engine's generic
executor hands it over.
"""

from typing import Any, Dict, List, Optional

from inbetweenies.mcp.tools import ToolResult, _parse_at, _rel_dict
from inbetweenies.models.relationship import _as_aware


def _type_of(entity) -> str:
    return getattr(entity.entity_type, "value", entity.entity_type)


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else value


def _event_dict(event) -> Dict[str, Any]:
    content = event.content or {}
    return {
        "when": content.get("when"),
        "kind": content.get("kind"),
        "entity": event.to_dict(),
    }


async def _events_for(ops, vehicle_id: str, moment) -> List[Any]:
    found = []
    for rel in await ops.get_relationships(to_id=vehicle_id, rel_type="happened_to", at=moment):
        event = await ops.get_entity(rel.from_entity_id, at=moment)
        if event is not None and _type_of(event) == "event" and not getattr(event, "is_tombstone", False):
            found.append(event)
    return found


async def _vehicle(ops, vehicle_id: str, moment):
    vehicle = await ops.get_entity(vehicle_id, at=moment)
    if vehicle is None or _type_of(vehicle) != "vehicle":
        return None
    return vehicle


async def get_events(ops, vehicle_id: str, kind: Optional[str] = None, since: Optional[str] = None,
                     until: Optional[str] = None, at: Optional[str] = None) -> ToolResult:
    """The events recorded for a vehicle, oldest first, filtered by kind and date.

    Dates compare as ISO-8601 strings on the event's own ``when`` -- the date
    the thing happened, which is the axis a logbook is read on -- not on
    when the event was recorded. ``at`` (ADR-004 §3) is the other axis: the
    events as they were *known* at that instant.
    """
    try:
        moment = _parse_at(at)
        vehicle = await _vehicle(ops, vehicle_id, moment)
        if vehicle is None:
            return ToolResult(False, None, f"Vehicle {vehicle_id} not found")
        events = []
        for event in await _events_for(ops, vehicle_id, moment):
            content = event.content or {}
            when = content.get("when") or ""
            if kind and content.get("kind") != kind:
                continue
            if since and when[:len(since)] < since:
                continue
            if until and when[:len(until)] > until:
                continue
            events.append(_event_dict(event))
        events.sort(key=lambda e: (e["when"] or "", e["kind"] or ""))
        return ToolResult(True, {
            "vehicle_id": vehicle_id,
            "anchor": {"id": vehicle.id, "name": vehicle.name, "type": "vehicle"},
            "events": events,
            "count": len(events),
            "kind": kind, "since": since, "until": until, "as_of": at,
        })
    except Exception as e:
        return ToolResult(False, None, str(e))


async def get_vehicle_history(ops, vehicle_id: str, at: Optional[str] = None) -> ToolResult:
    """One timeline: every event, every part on and off, every move.

    Every entry carries ``when`` (ISO-8601) so the caller can sort or filter;
    the list is returned oldest first. Part intervals contribute two entries
    each -- fitted at ``valid_from``, removed at ``valid_to`` when closed --
    and location intervals likewise (``moved_in`` / ``moved_out``), which is
    the interval model read as a story.
    """
    try:
        moment = _parse_at(at)
        vehicle = await _vehicle(ops, vehicle_id, moment)
        if vehicle is None:
            return ToolResult(False, None, f"Vehicle {vehicle_id} not found")

        entries: List[Dict[str, Any]] = []
        for event in await _events_for(ops, vehicle_id, moment):
            entries.append(_event_dict(event))

        # Intervals: every one ever, so a part that came off or a yard it left
        # still tells its story. As of `at`, only intervals that had started.
        async def intervals(rel_type, incoming, start_kind, end_kind):
            rels = await ops.get_relationships(
                **({"to_id": vehicle_id} if incoming else {"from_id": vehicle_id}),
                rel_type=rel_type, include_all_versions=True)
            for rel in rels:
                started = _as_aware(rel.valid_from) if rel.valid_from is not None else None
                ended = _as_aware(rel.valid_to) if rel.valid_to is not None else None
                if moment is not None and started is not None and started > moment:
                    continue
                other_id = rel.from_entity_id if incoming else rel.to_entity_id
                other = await ops.get_entity(other_id, at=moment)
                if other is None:
                    continue
                entries.append({"when": _iso(rel.valid_from), "kind": start_kind,
                                "entity": other.to_dict(), "edge": _rel_dict(rel)})
                if ended is not None and (moment is None or ended <= moment):
                    entries.append({"when": _iso(rel.valid_to), "kind": end_kind,
                                    "entity": other.to_dict(), "edge": _rel_dict(rel)})

        await intervals("fitted_to", True, "part_fitted", "part_removed")
        await intervals("located_in", False, "moved_in", "moved_out")

        entries.sort(key=lambda e: (e["when"] or "", e["kind"] or ""))
        return ToolResult(True, {
            "vehicle_id": vehicle_id,
            "anchor": {"id": vehicle.id, "name": vehicle.name, "type": "vehicle"},
            "events": entries,
            "count": len(entries),
            "as_of": at,
        })
    except Exception as e:
        return ToolResult(False, None, str(e))
