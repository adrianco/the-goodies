#!/usr/bin/env python3
"""
room_session.py — Session state for /room-walk and /room-edit.

A session captures an in-progress cataloguing or editing activity for a
specific room. It holds:

- Identifying info (UUID, room entity id, room name, mode)
- A snapshot of the room's current state at session start (for replay + diff)
- A list of pending diffs (create/update/move/delete/add_alias/status_change/...)
- Attached photo paths (pre-compression on disk, uploaded as blobs at commit)
- A running transcript (what the user said, what the agent said) — for the audit
  trail stored as a 'note' entity on commit

Sessions live in `$FG_SESSIONS_DIR/room-sessions/<uuid>.json` until committed,
then move to `$FG_SESSIONS_DIR/room-sessions/archive/<uuid>.json`.

Sessions never expire. This is the audit log.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
STATE_ROOT = os.environ.get("FG_SESSIONS_DIR", os.path.join(PROJECT_DIR, ".fg-sessions"))
SESSIONS_DIR = os.path.join(STATE_ROOT, "room-sessions")
ARCHIVE_DIR = os.path.join(SESSIONS_DIR, "archive")
PHOTOS_DIR = os.path.join(SESSIONS_DIR, "photos")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class RoomSession:
    """In-memory representation of a walk or edit session.

    Diff actions (populate self.diffs):
      {action: "create_device", draft: {name, content, located_in_room_id, aliases, photos: [paths]}}
      {action: "create_door",   draft: {name, content, connects_to: [room_ids]}}
      {action: "create_keypad", draft: {name, content, located_in_room_id, buttons: [...]}}
      {action: "create_button", draft: {name, content, part_of_keypad_id, controls: [device_ids], triggered_by_task_id}}
      {action: "create_task_auto", draft: {name, content.system.task_id}}
      {action: "create_room",   draft: {name, content, parent_home_id}}

      {action: "update_device", entity_id, patch: {name?, content_merges?, aliases_add?, aliases_remove?}}
      {action: "rename_entity", entity_id, new_name}
      {action: "add_alias",     entity_id, alias}
      {action: "remove_alias",  entity_id, alias}
      {action: "set_status",    entity_id, status, reason?}
      {action: "move_to_room",  entity_id, new_room_id}
      {action: "delete_entity", entity_id, reason?}
      {action: "add_note",      parent_entity_id, note_text}
      {action: "attach_photo",  parent_entity_id, photo_path, description?}
    """

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        if data is None:
            data = {
                "id": str(uuid.uuid4()),
                "mode": "walk",  # 'walk' | 'edit'
                "room_entity_id": None,
                "room_name": None,
                "status": "open",  # 'open' | 'reviewing' | 'committed' | 'discarded'
                "started_at": _now_iso(),
                "last_updated": _now_iso(),
                "started_by": os.environ.get("USER", "agent"),
                "initial_snapshot": None,  # {room, devices, doors, keypads, aliases}
                "diffs": [],
                "transcript": [],  # [{t, role, text}]
                "last_review_url": None,
            }
        self.data = data

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        room_entity_id: Optional[str],
        room_name: str,
        mode: str = "walk",
        initial_snapshot: Optional[Dict[str, Any]] = None,
    ) -> "RoomSession":
        s = cls()
        s.data["mode"] = mode
        s.data["room_entity_id"] = room_entity_id
        s.data["room_name"] = room_name
        s.data["initial_snapshot"] = initial_snapshot or {}
        s._ensure_dirs()
        s.save()
        return s

    @classmethod
    def load(cls, session_id: str) -> "RoomSession":
        path = cls._path_for(session_id)
        with open(path, "r") as f:
            data = json.load(f)
        return cls(data)

    @classmethod
    def find_open_for_room(cls, room_name: str) -> List["RoomSession"]:
        """Find open sessions for a given room (by name)."""
        out = []
        cls._ensure_dirs_static()
        for fname in os.listdir(SESSIONS_DIR):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(SESSIONS_DIR, fname)
            if os.path.isdir(path):
                continue
            try:
                with open(path, "r") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if (
                data.get("status") == "open"
                and (data.get("room_name") or "").lower() == room_name.lower()
            ):
                out.append(cls(data))
        return out

    @classmethod
    def list_all(cls, include_archived: bool = False) -> List[Dict[str, Any]]:
        """List sessions as dicts (summary only)."""
        cls._ensure_dirs_static()
        out = []
        dirs = [SESSIONS_DIR]
        if include_archived:
            dirs.append(ARCHIVE_DIR)
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for fname in sorted(os.listdir(d)):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(d, fname)
                if os.path.isdir(path):
                    continue
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    out.append({
                        "id": data.get("id"),
                        "mode": data.get("mode"),
                        "room_name": data.get("room_name"),
                        "status": data.get("status"),
                        "started_at": data.get("started_at"),
                        "diffs_count": len(data.get("diffs") or []),
                        "archived": os.path.basename(d) == "archive",
                    })
                except (OSError, json.JSONDecodeError):
                    continue
        return out

    # ── Persistence ──────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_dirs_static() -> None:
        for d in (SESSIONS_DIR, ARCHIVE_DIR, PHOTOS_DIR):
            os.makedirs(d, exist_ok=True)

    def _ensure_dirs(self) -> None:
        self._ensure_dirs_static()

    @staticmethod
    def _path_for(session_id: str) -> str:
        p = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if os.path.exists(p):
            return p
        # maybe archived
        ap = os.path.join(ARCHIVE_DIR, f"{session_id}.json")
        if os.path.exists(ap):
            return ap
        return p  # will raise on open

    def save(self) -> None:
        self.data["last_updated"] = _now_iso()
        self._ensure_dirs()
        path = self._path_for(self.data["id"])
        if self.data.get("status") == "committed" or self.data.get("status") == "discarded":
            path = os.path.join(ARCHIVE_DIR, f"{self.data['id']}.json")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, path)

    def archive(self) -> None:
        """Move session to archive (called internally by commit/discard)."""
        src = os.path.join(SESSIONS_DIR, f"{self.data['id']}.json")
        dst = os.path.join(ARCHIVE_DIR, f"{self.data['id']}.json")
        if os.path.exists(src):
            os.replace(src, dst)

    # ── Mutations ────────────────────────────────────────────────────────────

    def add_diff(self, diff: Dict[str, Any]) -> None:
        # Assign an index so the review can reference "diff #3"
        diff.setdefault("idx", len(self.data["diffs"]))
        diff.setdefault("added_at", _now_iso())
        self.data["diffs"].append(diff)
        self.data["last_review_url"] = None  # review URL is stale now
        self.save()

    def remove_diff(self, idx: int) -> None:
        self.data["diffs"] = [d for d in self.data["diffs"] if d.get("idx") != idx]
        self.data["last_review_url"] = None
        self.save()

    def replace_diff(self, idx: int, new_diff: Dict[str, Any]) -> None:
        new_diff["idx"] = idx
        new_diff.setdefault("added_at", _now_iso())
        self.data["diffs"] = [
            new_diff if d.get("idx") == idx else d for d in self.data["diffs"]
        ]
        self.data["last_review_url"] = None
        self.save()

    def log(self, role: str, text: str) -> None:
        """Append a transcript entry. role: 'user' | 'agent' | 'system'."""
        self.data["transcript"].append({
            "t": _now_iso(),
            "role": role,
            "text": text[:4000],  # cap to keep state files reasonable
        })
        self.save()

    def attach_photo(
        self,
        source_path: str,
        parent_hint: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        """Copy a photo into the session's photo dir, return the session-local path.

        Photos are referenced by diffs; the actual blob upload happens at commit.
        """
        if not os.path.exists(source_path):
            raise FileNotFoundError(source_path)
        self._ensure_dirs()
        photo_id = f"{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}"
        ext = os.path.splitext(source_path)[1].lower() or ".jpg"
        dest_dir = os.path.join(PHOTOS_DIR, self.data["id"])
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, photo_id + ext)
        # Hardlink if same volume, else copy
        try:
            os.link(source_path, dest)
        except OSError:
            import shutil
            shutil.copy2(source_path, dest)
        # Record in session-level photo index
        photos = self.data.setdefault("photos", {})
        photos[photo_id] = {
            "id": photo_id,
            "source_path": source_path,
            "session_path": dest,
            "parent_hint": parent_hint,
            "description": description,
            "added_at": _now_iso(),
        }
        self.save()
        return photo_id

    def set_status(self, status: str) -> None:
        assert status in ("open", "reviewing", "committed", "discarded")
        self.data["status"] = status
        # Write to the active-sessions location so the data-with-new-status lands on disk,
        # THEN move the file to archive. Order matters — save() below decides path based
        # on status, so we skip that dispatch for this call.
        self._ensure_dirs()
        self.data["last_updated"] = _now_iso()
        active_path = os.path.join(SESSIONS_DIR, f"{self.data['id']}.json")
        archive_path = os.path.join(ARCHIVE_DIR, f"{self.data['id']}.json")
        target = archive_path if status in ("committed", "discarded") else active_path
        tmp = target + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, target)
        # If moving to archive, remove the active copy
        if target == archive_path and os.path.exists(active_path):
            os.remove(active_path)

    def set_review_url(self, url: str) -> None:
        self.data["last_review_url"] = url
        self.data["last_review_at"] = _now_iso()
        self.data["status"] = "reviewing"
        self.save()

    # ── Convenience accessors ────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def room_name(self) -> str:
        return self.data.get("room_name") or ""

    @property
    def mode(self) -> str:
        return self.data.get("mode") or "walk"

    @property
    def diffs(self) -> List[Dict[str, Any]]:
        return list(self.data.get("diffs") or [])

    def summary(self) -> Dict[str, Any]:
        diffs = self.diffs
        counts: Dict[str, int] = {}
        for d in diffs:
            counts[d.get("action", "?")] = counts.get(d.get("action", "?"), 0) + 1
        return {
            "id": self.id,
            "mode": self.mode,
            "room_name": self.room_name,
            "status": self.data.get("status"),
            "started_at": self.data.get("started_at"),
            "diff_count": len(diffs),
            "by_action": counts,
            "photo_count": len(self.data.get("photos") or {}),
        }


# ── CLI ──────────────────────────────────────────────────────────────────────


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").add_argument("--archived", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("id")
    show.add_argument("--full", action="store_true")

    discard = sub.add_parser("discard")
    discard.add_argument("id")

    args = p.parse_args()

    if args.cmd == "list":
        for s in RoomSession.list_all(include_archived=args.archived):
            suffix = " [archived]" if s.get("archived") else ""
            print(
                f"  {s['id'][:8]}… {s['mode']:<5} {s['room_name']:<25} "
                f"{s['status']:<11} {s['diffs_count']:>3}d {s.get('started_at','?')[:16]}{suffix}"
            )
    elif args.cmd == "show":
        s = RoomSession.load(args.id)
        if args.full:
            print(json.dumps(s.data, indent=2))
        else:
            print(json.dumps(s.summary(), indent=2))
    elif args.cmd == "discard":
        s = RoomSession.load(args.id)
        s.set_status("discarded")
        print(f"Discarded {s.id}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
