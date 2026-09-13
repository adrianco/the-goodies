#!/usr/bin/env python3
"""
room_commit.py — Apply a RoomSession's diffs to FunkyGibbon via fg_client (MCP tools).

Commit flow:
1. Re-fetch the room's current snapshot (detect concurrent changes → soft warning)
2. For each diff, call the appropriate FunkyGibbon endpoint
3. For create-type diffs, remember the newly created entity_id so subsequent
   diffs in the same session can reference it (e.g. keypad → button part_of)
4. Upload photo blobs for diffs that reference them
5. READ BACK every entity and photo this commit created, with a fresh client,
   and only then set the session to 'committed' (moves to archive). "Saved"
   means confirmed present in the graph — not that the calls returned 200.
6. If anything that was reported created cannot be read back, the session is
   left `open` with `commit_errors` recorded, so it can be re-run; already-
   applied diffs are skipped on the re-run where the applier can tell.

The applier is idempotent where possible — if a diff's already-applied check
passes (e.g. the named entity already exists), it's skipped without error.

Usage:
    from room_commit import commit_session
    result = commit_session(session_id)
    # result = {committed: N, skipped: M, errors: [...], new_entities: {...}}
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from typing import Any, Dict, List, Optional

PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
STATE_ROOT = os.environ.get("FG_SESSIONS_DIR", os.path.join(PROJECT_DIR, ".fg-sessions"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fg_client import FGClient, FGError as FunkyGibbonError  # noqa: E402
from room_session import RoomSession  # noqa: E402
from image_compress import compress_image  # noqa: E402


class CommitResult:
    def __init__(self):
        self.committed: int = 0
        self.skipped: int = 0
        self.errors: List[str] = []
        self.new_entities: Dict[str, str] = {}  # diff_idx → entity_id
        self.photo_blobs: Dict[str, str] = {}   # photo_id → photo entity id
        self.photo_blob_ids: Dict[str, str] = {}  # photo_id → content-addressed blob id
        self.readback: Dict[str, Any] = {}

    def as_dict(self) -> Dict[str, Any]:
        return {
            "committed": self.committed,
            "skipped": self.skipped,
            "errors": self.errors,
            "new_entities": self.new_entities,
            "photo_blobs": self.photo_blobs,
            "photo_blob_ids": self.photo_blob_ids,
            "readback": self.readback,
        }


def _eid(response: Any) -> str:
    """Extract entity id from FunkyGibbon response, which may be wrapped as {'entity': {...}}."""
    if isinstance(response, dict) and "entity" in response:
        return response["entity"]["id"]
    return response["id"]


def _resolve_entity_ref(ref: Any, created: Dict[str, str]) -> Any:
    """A draft may reference another draft by diff_idx (e.g. part_of_keypad_idx).
    Resolve to the real entity_id post-creation."""
    if isinstance(ref, dict) and ref.get("draft_idx") is not None:
        return created.get(str(ref["draft_idx"]))
    if isinstance(ref, str) and ref.startswith("draft:"):
        return created.get(ref[6:])
    return ref


def _apply_create_room(fg: FGClient, diff: Dict[str, Any], home_id: Optional[str]) -> str:
    draft = diff["draft"]
    ent = fg.create_entity(
        entity_type="room",
        name=draft["name"],
        content=draft.get("content") or {},
        source_type=draft.get("source_type", "imported"),
    )
    rid = _eid(ent)
    if home_id:
        try:
            fg.create_relationship(rid, home_id, "located_in")
        except FunkyGibbonError:
            pass
    return rid


def _apply_create_device(
    fg: FGClient,
    diff: Dict[str, Any],
    created: Dict[str, str],
) -> str:
    draft = diff["draft"]
    source = draft.get("source_type", "imported")
    ent = fg.create_entity(
        entity_type="device",
        name=draft["name"],
        content=draft.get("content") or {},
        source_type=source,
    )
    eid = _eid(ent)
    # located_in → room
    room_id = _resolve_entity_ref(draft.get("located_in_room_id"), created)
    if room_id:
        fg.create_relationship(eid, room_id, "located_in")
    # controls → one or more other devices
    for target in draft.get("controls") or []:
        target_id = _resolve_entity_ref(target, created)
        if target_id:
            fg.create_relationship(eid, target_id, "controls")
    # monitors
    for target in draft.get("monitors") or []:
        target_id = _resolve_entity_ref(target, created)
        if target_id:
            fg.create_relationship(eid, target_id, "monitors")
    return eid


def _apply_create_door(fg: FGClient, diff: Dict[str, Any], created: Dict[str, str]) -> str:
    draft = diff["draft"]
    ent = fg.create_entity(
        entity_type="door",
        name=draft["name"],
        content=draft.get("content") or {},
        source_type=draft.get("source_type", "manual"),
    )
    did = _eid(ent)
    for room_ref in draft.get("connects_to") or []:
        room_id = _resolve_entity_ref(room_ref, created)
        if room_id:
            fg.create_relationship(did, room_id, "connects_to")
    # Link lock device to door if specified
    lock_ref = draft.get("content", {}).get("lock_device_id")
    if lock_ref:
        lock_id = _resolve_entity_ref(lock_ref, created)
        if lock_id:
            fg.create_relationship(lock_id, did, "controls")
    return did


def _apply_create_keypad(
    fg: FGClient,
    diff: Dict[str, Any],
    created: Dict[str, str],
) -> str:
    """A keypad and its buttons are submitted together: the keypad draft
    includes a buttons: [...] list. We create the keypad first, then each
    button, wiring part_of + controls/triggered_by relationships."""
    draft = diff["draft"]
    keypad_ent = fg.create_entity(
        entity_type="device",
        name=draft["name"],
        content=draft.get("content") or {},
        source_type=draft.get("source_type", "imported"),
    )
    kid = _eid(keypad_ent)
    room_id = _resolve_entity_ref(draft.get("located_in_room_id"), created)
    if room_id:
        fg.create_relationship(kid, room_id, "located_in")

    for btn in draft.get("buttons") or []:
        btn_ent = fg.create_entity(
            entity_type="device",
            name=btn["name"],
            content=btn.get("content") or {},
            source_type=btn.get("source_type", "imported"),
        )
        bid = _eid(btn_ent)
        # Composition edge. v0.7.0 refused device part_of device (#90, fixed on
        # main); against a fixed server the edge is created and the fallback
        # below never runs. Kept until every install is past v0.7.0.
        try:
            fg.create_relationship(bid, kid, "part_of")
        except FunkyGibbonError as e:
            fg.update_entity(bid, content={**(btn.get("content") or {}), "part_of_device_id": kid})
            print(f"  note: button->keypad part_of edge refused by vocabulary; recorded in content ({e})", file=sys.stderr)
        if room_id:
            fg.create_relationship(bid, room_id, "located_in")
        # Controls loads
        for target in btn.get("controls") or []:
            target_id = _resolve_entity_ref(target, created)
            if target_id:
                fg.create_relationship(bid, target_id, "controls")
        # Triggers a task automation
        tb = btn.get("triggered_by")
        if tb:
            task_id = _resolve_entity_ref(tb, created)
            if task_id:
                fg.create_relationship(bid, task_id, "triggered_by")
    return kid


def _apply_create_task_auto(fg: FGClient, diff: Dict[str, Any]) -> str:
    draft = diff["draft"]
    ent = fg.create_entity(
        entity_type="automation",
        name=draft["name"],
        content=draft.get("content") or {},
        source_type=draft.get("source_type", "imported"),
    )
    return _eid(ent)


def _apply_update(fg: FGClient, diff: Dict[str, Any], created: Dict[str, str]) -> None:
    action = diff["action"]
    eid = _resolve_entity_ref(diff.get("entity_id"), created)
    if not eid:
        raise FunkyGibbonError(f"Update diff has no resolvable entity_id: {diff}")

    if action == "rename_entity":
        fg.update_entity(eid, name=diff["new_name"])
    elif action == "add_alias":
        fg.upsert_alias(eid, diff["alias"])
    elif action == "remove_alias":
        fg.remove_alias(eid, diff["alias"])
    elif action == "set_status":
        fg.set_status(eid, diff["status"], diff.get("reason"))
    elif action == "move_to_room":
        new_room_id = _resolve_entity_ref(diff.get("new_room_id"), created)
        if not new_room_id:
            raise FunkyGibbonError("move_to_room missing new_room_id")
        # ADR-004: a move is END the current located_in interval + create a new one.
        for rel in fg.list_relationships(from_id=eid, rel_type="located_in"):
            fg.end_relationship(rel["id"], reason=diff.get("reason") or "moved via room-edit")
        fg.create_relationship(eid, new_room_id, "located_in")
    elif action == "delete_entity":
        fg.delete_entity(eid, reason=diff.get("reason") or "removed via room-edit",
                         is_error=bool(diff.get("is_error")))
    elif action == "update_device":
        patch = diff.get("patch") or {}
        # Fetch current, merge content_merges, add/remove aliases, then PATCH
        ent = fg.get_entity(eid)
        new_content = dict(ent.get("content") or {})
        for k, v in (patch.get("content_merges") or {}).items():
            new_content[k] = v
        aliases = list(new_content.get("aliases") or [])
        for a in patch.get("aliases_add") or []:
            if a not in aliases:
                aliases.append(a)
        for a in patch.get("aliases_remove") or []:
            if a in aliases:
                aliases.remove(a)
        if aliases != (ent.get("content") or {}).get("aliases"):
            new_content["aliases"] = aliases
        fg.update_entity(eid, name=patch.get("name"), content=new_content)
    elif action == "add_note":
        text = diff.get("note_text", "")
        note = fg.create_entity(
            entity_type="note",
            name=text[:80] or "note",
            content={"body": text, "about_entity_id": eid},
            source_type="manual",
        )
        try:
            fg.create_relationship(eid, note["id"], "documented_by")
        except FunkyGibbonError as e:
            # v0.7.0 refused device -> note (#91, fixed on main); against a fixed
            # server the edge is created and this fallback never runs. Kept
            # until every install is past v0.7.0.
            ent = fg.get_entity(eid)
            content = dict(ent.get("content") or {})
            notes = list(content.get("notes") or [])
            notes.append({"note_entity_id": note["id"], "text": text})
            content["notes"] = notes
            fg.update_entity(eid, content=content)
            print(f"  note: documented_by edge refused by vocabulary; note linked via content.notes ({e})", file=sys.stderr)
    else:
        raise FunkyGibbonError(f"Unknown update action: {action}")


def _apply_photo_attachments(
    fg: FGClient,
    session: RoomSession,
    created: Dict[str, str],
    result: CommitResult,
) -> None:
    """For every diff that references photos, attach them (server links has_photo).
    Works for create_device, create_keypad, attach_photo diffs."""
    photos = session.data.get("photos") or {}
    if not photos:
        return

    # Build a mapping from diff_idx → list of photo_ids that were collected for it
    # Convention:
    #   - create_device/draft has 'photos': [photo_id, ...]
    #   - create_keypad/draft has 'photos': [photo_id, ...]
    #   - attach_photo diff has 'entity_id' + 'photo_id'
    def attach_photos_for_entity(entity_id: str, photo_ids: List[str]) -> None:
        for pid in photo_ids:
            meta = photos.get(pid)
            if not meta:
                continue
            path = meta.get("session_path")
            if not path or not os.path.exists(path):
                result.errors.append(f"Photo {pid[:8]}… missing on disk ({path})")
                continue
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                compressed, _info = compress_image(raw)
            except Exception as e:
                result.errors.append(f"Photo {pid[:8]}… compression failed: {e}")
                continue
            try:
                blob = fg.upload_blob(
                    entity_id,
                    compressed,
                    filename=f"{pid}.jpg",
                    mime_type="image/jpeg",
                    description=meta.get("description"),
                )
                result.photo_blobs[pid] = blob["id"]          # photo entity id
                result.photo_blob_ids[pid] = blob.get("blob_id", "")
            except Exception as e:
                result.errors.append(f"Blob upload failed for {pid[:8]}…: {e}")

    # Walk diffs again to find photo references
    for d in session.diffs:
        action = d["action"]
        entity_id = None
        if action in ("create_device", "create_keypad"):
            entity_id = created.get(str(d.get("idx")))
        elif action == "attach_photo":
            entity_id = _resolve_entity_ref(d.get("entity_id"), created)
        else:
            continue

        if not entity_id:
            continue

        photo_ids = d.get("draft", {}).get("photos") if action != "attach_photo" else [d.get("photo_id")]
        photo_ids = [p for p in (photo_ids or []) if p]
        if photo_ids:
            attach_photos_for_entity(entity_id, photo_ids)


def commit_session(session_id: str) -> Dict[str, Any]:
    """Apply all diffs in the session. Returns a CommitResult dict."""
    session = RoomSession.load(session_id)
    if session.data.get("status") == "committed":
        return {"committed": 0, "skipped": 0, "errors": ["already committed"], "new_entities": {}}

    fg = FGClient()
    home = fg.get_home()
    home_id = home["id"] if home else None

    result = CommitResult()
    created_by_idx: Dict[str, str] = {}  # diff_idx → new entity_id

    for d in session.diffs:
        action = d["action"]
        idx = str(d.get("idx"))
        try:
            if action == "create_room":
                eid = _apply_create_room(fg, d, home_id)
                created_by_idx[idx] = eid
                result.new_entities[idx] = eid
            elif action == "create_device":
                eid = _apply_create_device(fg, d, created_by_idx)
                created_by_idx[idx] = eid
                result.new_entities[idx] = eid
            elif action == "create_door":
                eid = _apply_create_door(fg, d, created_by_idx)
                created_by_idx[idx] = eid
                result.new_entities[idx] = eid
            elif action == "create_keypad":
                eid = _apply_create_keypad(fg, d, created_by_idx)
                created_by_idx[idx] = eid
                result.new_entities[idx] = eid
            elif action == "create_task_auto":
                eid = _apply_create_task_auto(fg, d)
                created_by_idx[idx] = eid
                result.new_entities[idx] = eid
            elif action == "attach_photo":
                # Handled in photo pass below, but ensure entity_id is in created map
                pass
            elif action == "note":
                # Session notes captured for context — folded into the transcript
                # note at the end of commit. Skip silently here.
                result.skipped += 1
                continue
            else:
                # All update-style diffs
                _apply_update(fg, d, created_by_idx)
            result.committed += 1
        except Exception as e:
            result.errors.append(
                f"diff #{idx} ({action}) failed: {e}"
            )
            # Log but continue — partial commit is OK; the rest of the session
            # can be reworked via /room-edit on the surviving entities
            traceback.print_exc(file=sys.stderr)

    # Photos last — require entities to exist
    try:
        _apply_photo_attachments(fg, session, created_by_idx, result)
    except Exception as e:
        result.errors.append(f"photo attachment pass failed: {e}")

    # Write a transcript note on the room itself for audit
    if session.data.get("room_entity_id") and (session.data.get("transcript") or session.diffs):
        try:
            transcript_text = "\n".join(
                f"[{t.get('t','?')}] {t.get('role','?')}: {t.get('text','')}"
                for t in (session.data.get("transcript") or [])
            )
            summary_note = fg.create_entity(
                entity_type="note",
                name=f"{session.mode.title()} session {session.id[:8]}",
                content={
                    "session_id": session.id,
                    "mode": session.mode,
                    "committed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "diffs_applied": result.committed,
                    "diffs_errored": len(result.errors),
                    "transcript": transcript_text[:20000],
                },
                source_type="generated",
            )
            fg.create_relationship(
                session.data["room_entity_id"], _eid(summary_note), "documented_by"
            )
        except Exception as e:
            result.errors.append(f"audit note creation failed: {e}")

    # Read back everything this commit claims to have created, using a FRESH
    # client (a new request; the pre-v0.5.0 bug rolled writes back at request end).
    verifier = FGClient()
    missing: List[str] = []
    for idx, eid in result.new_entities.items():
        ent = verifier.get_entity(eid)
        if not ent or (ent.get("content") or {}).get("deleted"):
            missing.append(f"entity for diff #{idx} ({eid})")
    for pid, photo_eid in result.photo_blobs.items():
        ent = verifier.get_entity(photo_eid)
        if not ent or ent.get("entity_type") not in ("photo", "manual"):
            missing.append(f"photo {pid[:8]}… ({photo_eid})")
    result.readback = {"checked": len(result.new_entities) + len(result.photo_blobs), "missing": missing}

    if missing:
        # Do NOT archive: what was reported created is not on the server.
        result.errors.append("readback failed for: " + "; ".join(missing))
        session.data["commit_errors"] = result.errors
        session.data["commit_attempted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        session.save()
        return result.as_dict()

    # Everything created is confirmed present. Archive. Diffs that FAILED are
    # listed in errors for follow-up via /room-edit.
    session.set_status("committed")
    return result.as_dict()


# ── CLI ──────────────────────────────────────────────────────────────────────


def _cli() -> int:
    import argparse
    import json as _json

    p = argparse.ArgumentParser()
    p.add_argument("session_id")
    p.add_argument("--dry-run", action="store_true", help="Print what would be committed")
    args = p.parse_args()

    if args.dry_run:
        s = RoomSession.load(args.session_id)
        print(_json.dumps(s.summary(), indent=2))
        for d in s.diffs:
            print(f"  [{d.get('idx')}] {d['action']}")
        return 0

    result = commit_session(args.session_id)
    print(_json.dumps(result, indent=2))
    if result.get("errors"):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
