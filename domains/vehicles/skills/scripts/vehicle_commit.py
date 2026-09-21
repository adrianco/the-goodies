#!/usr/bin/env python3
"""
vehicle_commit.py — apply a vehicle-walk session's diffs to a FunkyGibbon
vehicles server via fg_client (MCP tools). The counterpart of room_commit.py.

Same rule as the room walk: nothing is "saved" until it has been read back.
Every entity this commit creates is re-read with a FRESH client, and the
session is archived only if all of them are present; otherwise it stays open
with `commit_errors` recorded so it can be re-run.

It reuses the house's shared helpers unchanged (`fg_client.py`,
`room_session.py`, `image_compress.py`) — copy both `scripts/` directories
into `.claude/scripts/`. The vehicles endpoint comes from
`FUNKYGIBBON_VEHICLES_URL` (default http://localhost:8001); auth is shared
with the house server, so the same client token works.

Diff actions (ADR-016 §2 — a thing, a place, or something that happened):

  create_vehicle   draft: {name, content, located_in?}
  create_location  draft: {name, content}
  create_part      draft: {name, content, fitted_to?, located_in?, replaces?, compatible_with?, photos?}
  create_tool      draft: {name, content, located_in?, compatible_with?, photos?}
  create_event     draft: {name, content{kind, when, ...}, happened_to, involved?, photos?, documents?}
  remove_part      {part_id, reason?, now_located_in?}       ends fitted_to; never deletes
  move             {entity_id, to_location}                  ends located_in, opens a new one
  update_vehicle   {entity_id, name?, content_merges?}       odometer, status, aliases, spec
  attach_photo     {entity_id, photo_id}
  attach_document  {entity_id, photo_id}

Any id may be a reference to an earlier diff in the same session: "draft:<idx>".

Usage:
    python3 .claude/scripts/vehicle_commit.py <session_id> [--dry-run]
"""
from __future__ import annotations

import mimetypes
import os
import sys
import time
import traceback
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fg_client import FGClient, FGError  # noqa: E402
from room_session import RoomSession  # noqa: E402

VEHICLES_URL = os.environ.get("FUNKYGIBBON_VEHICLES_URL", "http://localhost:8001")
CREATES = {"create_vehicle": "vehicle", "create_location": "location", "create_part": "part",
           "create_tool": "tool", "create_event": "event"}


def _client() -> FGClient:
    return FGClient(server_url=VEHICLES_URL, user_id="vehicle-walk")


def _ref(value: Any, created: Dict[str, str]) -> Optional[str]:
    """Resolve "draft:<idx>" to the id that diff created; pass real ids through."""
    if isinstance(value, str) and value.startswith("draft:"):
        return created.get(value[6:])
    return value or None


def _link(fg: FGClient, from_id: Optional[str], to_id: Optional[str], rel: str, errors: List[str], what: str) -> None:
    if not from_id or not to_id:
        errors.append(f"{what}: unresolved endpoint for {rel}")
        return
    fg.create_relationship(from_id, to_id, rel)


def _end_open(fg: FGClient, from_id: str, rel: str, reason: str) -> int:
    ended = 0
    for r in fg.list_relationships(from_id=from_id, rel_type=rel):
        if not r.get("valid_to"):
            fg.end_relationship(r["id"], reason=reason)
            ended += 1
    return ended


def _apply_create(fg: FGClient, diff: Dict[str, Any], created: Dict[str, str], errors: List[str]) -> str:
    draft, idx = diff["draft"], diff.get("idx")
    entity = fg.create_entity(CREATES[diff["action"]], draft["name"], draft.get("content") or {})
    eid, what = entity["id"], f"diff #{idx} ({draft['name']})"
    for key, rel in (("located_in", "located_in"), ("fitted_to", "fitted_to"), ("happened_to", "happened_to")):
        if draft.get(key):
            _link(fg, eid, _ref(draft[key], created), rel, errors, what)
    if draft.get("replaces"):
        _link(fg, eid, _ref(draft["replaces"], created), "replaced", errors, what)
    for target in draft.get("compatible_with") or []:
        _link(fg, eid, _ref(target, created), "compatible_with", errors, what)
    for target in draft.get("involved") or []:
        _link(fg, eid, _ref(target, created), "involved", errors, what)
    return eid


def _apply_other(fg: FGClient, diff: Dict[str, Any], created: Dict[str, str], errors: List[str]) -> None:
    action = diff["action"]
    if action == "remove_part":
        part = _ref(diff.get("part_id"), created)
        if not part:
            raise FGError("remove_part has no resolvable part_id")
        # The part comes off: END the interval. It is kept as history, and
        # get_parts_on_vehicle(at=...) still answers for the time it was on.
        _end_open(fg, part, "fitted_to", diff.get("reason") or "removed via vehicle-walk")
        if diff.get("now_located_in"):
            _end_open(fg, part, "located_in", "moved via vehicle-walk")
            _link(fg, part, _ref(diff["now_located_in"], created), "located_in", errors, f"diff #{diff.get('idx')}")
    elif action == "move":
        eid = _ref(diff.get("entity_id"), created)
        if not eid:
            raise FGError("move has no resolvable entity_id")
        _end_open(fg, eid, "located_in", diff.get("reason") or "moved via vehicle-walk")
        _link(fg, eid, _ref(diff.get("to_location"), created), "located_in", errors, f"diff #{diff.get('idx')}")
    elif action == "update_vehicle":
        eid = _ref(diff.get("entity_id"), created)
        current = fg.get_entity(eid) if eid else {}
        if not current:
            raise FGError(f"update_vehicle: entity {diff.get('entity_id')} not found")
        content = dict(current.get("content") or {})
        content.update(diff.get("content_merges") or {})
        fg.update_entity(eid, name=diff.get("name"), content=content)
    elif action in ("attach_photo", "attach_document"):
        pass  # handled in the attachment pass
    else:
        raise FGError(f"unknown action: {action}")


def _attach(fg: FGClient, session: RoomSession, created: Dict[str, str], result: Dict[str, Any]) -> None:
    photos = session.data.get("photos") or {}

    def send(entity_id: str, photo_id: str, as_document: bool) -> None:
        meta = photos.get(photo_id) or {}
        path = meta.get("session_path")
        if not path or not os.path.exists(path):
            result["errors"].append(f"attachment {photo_id[:8]}… missing on disk ({path})")
            return
        with open(path, "rb") as fh:
            raw = fh.read()
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        name = os.path.basename(path)
        if not as_document and mime.startswith("image/"):
            try:
                from image_compress import compress_image
                raw, _info = compress_image(raw)
                mime, name = "image/jpeg", f"{photo_id}.jpg"
            except Exception as exc:  # Pillow missing: send the original rather than nothing
                result["errors"].append(f"compression skipped for {photo_id[:8]}…: {exc}")
        elif as_document and mime != "application/pdf":
            result["errors"].append(f"document {photo_id[:8]}… is {mime}, not a PDF; attached as a photo instead")
        try:
            att = fg.upload_blob(entity_id, raw, filename=name, mime_type=mime, description=meta.get("description"))
            result["attachments"][photo_id] = att["id"]
        except Exception as exc:
            result["errors"].append(f"attachment {photo_id[:8]}… failed: {exc}")

    for d in session.diffs:
        action = d["action"]
        if action in CREATES:
            eid = created.get(str(d.get("idx")))
            draft = d.get("draft") or {}
            for pid in draft.get("photos") or []:
                if eid:
                    send(eid, pid, False)
            for pid in draft.get("documents") or []:
                if eid:
                    send(eid, pid, True)
        elif action in ("attach_photo", "attach_document"):
            eid = _ref(d.get("entity_id"), created)
            if eid and d.get("photo_id"):
                send(eid, d["photo_id"], action == "attach_document")


def commit_session(session_id: str) -> Dict[str, Any]:
    session = RoomSession.load(session_id)
    if session.data.get("status") == "committed":
        return {"committed": 0, "errors": ["already committed"], "new_entities": {}}

    fg = _client()
    stats = fg.get_statistics()
    if "room" in (stats.get("entity_types") or {}) or "device" in (stats.get("entity_types") or {}):
        return {"committed": 0, "new_entities": {},
                "errors": [f"{VEHICLES_URL} is a HOUSE server (it has rooms/devices); set FUNKYGIBBON_VEHICLES_URL"]}

    result: Dict[str, Any] = {"committed": 0, "errors": [], "new_entities": {}, "attachments": {}, "readback": {}}
    created: Dict[str, str] = {}

    for d in session.diffs:
        idx = str(d.get("idx"))
        try:
            if d["action"] in CREATES:
                created[idx] = result["new_entities"][idx] = _apply_create(fg, d, created, result["errors"])
            else:
                _apply_other(fg, d, created, result["errors"])
            result["committed"] += 1
        except Exception as exc:
            result["errors"].append(f"diff #{idx} ({d.get('action')}) failed: {exc}")
            traceback.print_exc(file=sys.stderr)

    try:
        _attach(fg, session, created, result)
    except Exception as exc:
        result["errors"].append(f"attachment pass failed: {exc}")

    # The transcript, as a note on the vehicle this walk was about.
    vehicle_id = _ref(session.data.get("room_entity_id"), created) or next(
        (created[str(d.get("idx"))] for d in session.diffs
         if d["action"] == "create_vehicle" and str(d.get("idx")) in created), None)
    if vehicle_id and (session.data.get("transcript") or session.diffs):
        try:
            text = "\n".join(f"[{t.get('t', '?')}] {t.get('role', '?')}: {t.get('text', '')}"
                             for t in session.data.get("transcript") or [])
            note = fg.create_entity("note", f"Vehicle walk {session.id[:8]}", {
                "session_id": session.id, "committed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "diffs_applied": result["committed"], "transcript": text[:20000]})
            fg.create_relationship(vehicle_id, note["id"], "documented_by")
            result["new_entities"]["transcript"] = note["id"]
        except Exception as exc:
            result["errors"].append(f"transcript note failed: {exc}")

    # Read back with a FRESH client: "saved" means present in the graph.
    verifier = _client()
    missing = [f"{key} ({eid})" for key, eid in list(result["new_entities"].items()) + list(result["attachments"].items())
               if not verifier.get_entity(eid)]
    result["readback"] = {"checked": len(result["new_entities"]) + len(result["attachments"]), "missing": missing}
    if missing:
        result["errors"].append("readback failed for: " + "; ".join(missing))
        session.data["commit_errors"] = result["errors"]
        session.save()
        return result

    session.set_status("committed")
    return result


def _cli() -> int:
    import argparse
    import json
    p = argparse.ArgumentParser()
    p.add_argument("session_id")
    p.add_argument("--dry-run", action="store_true", help="print what would be committed")
    args = p.parse_args()
    if args.dry_run:
        s = RoomSession.load(args.session_id)
        for d in s.diffs:
            print(f"  [{d.get('idx')}] {d['action']}: {(d.get('draft') or {}).get('name', d.get('entity_id') or d.get('part_id') or '')}")
        return 0
    result = commit_session(args.session_id)
    print(json.dumps(result, indent=2))
    return 2 if result.get("errors") else 0


if __name__ == "__main__":
    sys.exit(_cli())
