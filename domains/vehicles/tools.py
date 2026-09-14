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


async def _current_location(ops, entity_id: str, moment):
    for rel in await ops.get_relationships(from_id=entity_id, rel_type="located_in", at=moment):
        place = await ops.get_entity(rel.to_entity_id, at=moment)
        if place is not None:
            return place, rel
    return None, None


async def where_is(ops, item_id: str, at: Optional[str] = None) -> ToolResult:
    """Where a part or tool is: on a vehicle (and where that is), on a shelf, or unknown.

    The answer is read off the two interval edges: an open ``fitted_to`` says it
    is on a vehicle, and that vehicle's open ``located_in`` says where; an open
    ``located_in`` on the item itself says it is on a shelf. Both are as-of
    aware, so "where was that gearbox in 2019" is the same question.
    """
    try:
        moment = _parse_at(at)
        item = await ops.get_entity(item_id, at=moment)
        if item is None or _type_of(item) not in ("part", "tool"):
            return ToolResult(False, None, f"Part/tool {item_id} not found")
        answer: Dict[str, Any] = {"item_id": item_id, "item": {"id": item.id, "name": item.name, "type": _type_of(item)},
                                  "status": "unknown", "as_of": at}
        for rel in await ops.get_relationships(from_id=item_id, rel_type="fitted_to", at=moment):
            vehicle = await ops.get_entity(rel.to_entity_id, at=moment)
            if vehicle is None:
                continue
            answer.update({"status": "fitted", "vehicle": {"id": vehicle.id, "name": vehicle.name},
                           "since": _iso(rel.valid_from)})
            place, _ = await _current_location(ops, vehicle.id, moment)
            if place is not None:
                answer["location"] = {"id": place.id, "name": place.name}
            return ToolResult(True, answer)
        place, rel = await _current_location(ops, item_id, moment)
        if place is not None:
            answer.update({"status": "stored", "location": {"id": place.id, "name": place.name},
                           "since": _iso(rel.valid_from)})
        return ToolResult(True, answer)
    except Exception as e:
        return ToolResult(False, None, str(e))


async def get_part_history(ops, part_id: str, kind: Optional[str] = None, at: Optional[str] = None) -> ToolResult:
    """A part's life, and what its vehicles went through while it was on them.

    ``fittings`` lists every ``fitted_to`` interval (vehicle, from, to) and
    ``storage`` every ``located_in`` interval. ``events`` are the vehicle's
    events whose ``when`` falls inside a fitting, plus any event that names
    the part directly via ``involved`` -- filtered by ``kind`` if given, so
    "how many races did that gearbox run" is ``count`` with ``kind=race``.
    """
    try:
        moment = _parse_at(at)
        part = await ops.get_entity(part_id, at=moment)
        if part is None or _type_of(part) != "part":
            return ToolResult(False, None, f"Part {part_id} not found")

        fittings: List[Dict[str, Any]] = []
        for rel in await ops.get_relationships(from_id=part_id, rel_type="fitted_to", include_all_versions=True):
            started = _as_aware(rel.valid_from) if rel.valid_from is not None else None
            if moment is not None and started is not None and started > moment:
                continue
            vehicle = await ops.get_entity(rel.to_entity_id, at=moment)
            if vehicle is None:
                continue
            fittings.append({"vehicle": {"id": vehicle.id, "name": vehicle.name},
                             "from": _iso(rel.valid_from), "to": _iso(rel.valid_to), "edge": _rel_dict(rel)})
        storage: List[Dict[str, Any]] = []
        for rel in await ops.get_relationships(from_id=part_id, rel_type="located_in", include_all_versions=True):
            place = await ops.get_entity(rel.to_entity_id, at=moment)
            if place is not None:
                storage.append({"location": {"id": place.id, "name": place.name},
                                "from": _iso(rel.valid_from), "to": _iso(rel.valid_to)})

        seen: Dict[str, Dict[str, Any]] = {}
        # Events naming the part directly (the service that fitted it, the repair that used it).
        for rel in await ops.get_relationships(to_id=part_id, rel_type="involved", at=moment):
            event = await ops.get_entity(rel.from_entity_id, at=moment)
            if event is not None and _type_of(event) == "event":
                seen[event.id] = _event_dict(event)
        # Events on each vehicle while the part was fitted.
        for fit in fittings:
            lo = (fit["from"] or "")[:10]
            hi = (fit["to"] or "9999-12-31")[:10]
            for event in await _events_for(ops, fit["vehicle"]["id"], moment):
                when = (event.content or {}).get("when") or ""
                if lo <= when[:10] <= hi:
                    seen[event.id] = _event_dict(event)
        events = [e for e in seen.values() if not kind or e["kind"] == kind]
        events.sort(key=lambda e: (e["when"] or "", e["kind"] or ""))
        return ToolResult(True, {
            "part_id": part_id,
            "anchor": {"id": part.id, "name": part.name, "type": "part"},
            "fittings": fittings, "storage": storage,
            "events": events, "count": len(events), "kind": kind, "as_of": at,
        })
    except Exception as e:
        return ToolResult(False, None, str(e))
