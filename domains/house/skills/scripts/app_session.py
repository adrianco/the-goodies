#!/usr/bin/env python3
"""
app_session.py — Session state for /app-walk.

A session captures an in-progress cataloguing activity for a mobile/web app
(e.g. Alexa, Tuya, Hayward Omni, HomeKit). It records:

- App metadata (name, platform, ecosystem)
- Devices the app controls, with cross-refs to FunkyGibbon entities
- Routines, automations, and scenes within the app
- Screenshots attached during the conversation
- A running transcript for the audit trail

Sessions live in `$FG_SESSIONS_DIR/app-sessions/<uuid>.json` until committed,
then move to `$FG_SESSIONS_DIR/app-sessions/archive/<uuid>.json`.
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
SESSIONS_DIR = os.path.join(STATE_ROOT, "app-sessions")
ARCHIVE_DIR = os.path.join(SESSIONS_DIR, "archive")
SCREENSHOTS_DIR = os.path.join(SESSIONS_DIR, "screenshots")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class AppSession:
    """In-memory representation of an app-walk session."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    # ------------------------------------------------------------------ #
    # Factory methods                                                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def create(cls, app_name: str, platform: str, ecosystem: str) -> "AppSession":
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        session_id = str(uuid.uuid4())
        data: Dict[str, Any] = {
            "id": session_id,
            "status": "open",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "app_name": app_name,
            "platform": platform,       # ios | android | web | macos
            "ecosystem": ecosystem,     # alexa | apple | tuya | hayward | generic
            "fg_entity_id": None,       # set after commit
            "diffs": [],
            "screenshots": [],          # [{screenshot_id, source_path, screen_name, description}]
            "transcript": [],
        }
        session = cls(data)
        session._save()
        return session

    @classmethod
    def load(cls, session_id: str) -> "AppSession":
        path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if not os.path.exists(path):
            path = os.path.join(ARCHIVE_DIR, f"{session_id}.json")
        with open(path) as f:
            return cls(json.load(f))

    @classmethod
    def find_open_for_app(cls, app_name: str) -> List["AppSession"]:
        if not os.path.exists(SESSIONS_DIR):
            return []
        results = []
        for fname in os.listdir(SESSIONS_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(SESSIONS_DIR, fname)) as f:
                    d = json.load(f)
                if (
                    d.get("status") == "open"
                    and d.get("app_name", "").lower() == app_name.lower()
                ):
                    results.append(cls(d))
            except Exception:
                pass
        return results

    @classmethod
    def list_open(cls) -> List["AppSession"]:
        if not os.path.exists(SESSIONS_DIR):
            return []
        results = []
        for fname in os.listdir(SESSIONS_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(SESSIONS_DIR, fname)) as f:
                    d = json.load(f)
                if d.get("status") == "open":
                    results.append(cls(d))
            except Exception:
                pass
        return results

    # ------------------------------------------------------------------ #
    # Properties                                                            #
    # ------------------------------------------------------------------ #

    @property
    def id(self) -> str:
        return self._data["id"]

    @property
    def app_name(self) -> str:
        return self._data["app_name"]

    @property
    def platform(self) -> str:
        return self._data["platform"]

    @property
    def ecosystem(self) -> str:
        return self._data["ecosystem"]

    @property
    def status(self) -> str:
        return self._data["status"]

    @property
    def created_at(self) -> str:
        return self._data["created_at"]

    @property
    def diffs(self) -> List[Dict[str, Any]]:
        return self._data["diffs"]

    @property
    def screenshots(self) -> List[Dict[str, Any]]:
        return self._data["screenshots"]

    # ------------------------------------------------------------------ #
    # Diffs                                                                 #
    # ------------------------------------------------------------------ #

    def add_diff(self, diff: Dict[str, Any]) -> int:
        """Append a diff. Returns the index."""
        self._data["diffs"].append(diff)
        self._save()
        return len(self._data["diffs"]) - 1

    def remove_diff(self, idx: int) -> None:
        self._data["diffs"].pop(idx)
        self._save()

    def replace_diff(self, idx: int, new_diff: Dict[str, Any]) -> None:
        self._data["diffs"][idx] = new_diff
        self._save()

    # ------------------------------------------------------------------ #
    # Screenshots                                                           #
    # ------------------------------------------------------------------ #

    def attach_screenshot(
        self,
        source_path: str,
        screen_name: str,
        description: str = "",
    ) -> str:
        """Copy screenshot into the session's screenshot dir and record it."""
        import shutil
        shot_id = str(uuid.uuid4())[:8]
        ext = os.path.splitext(source_path)[1] or ".jpg"
        dest = os.path.join(SCREENSHOTS_DIR, f"{self.id}-{shot_id}{ext}")
        shutil.copy2(source_path, dest)
        entry = {
            "screenshot_id": shot_id,
            "source_path": dest,
            "screen_name": screen_name,
            "description": description,
        }
        self._data["screenshots"].append(entry)
        self._save()
        return shot_id

    # ------------------------------------------------------------------ #
    # Transcript                                                            #
    # ------------------------------------------------------------------ #

    def log(self, role: str, text: str) -> None:
        """role: 'user' | 'agent'"""
        self._data["transcript"].append({
            "role": role,
            "text": text,
            "ts": _now_iso(),
        })
        self._save()

    # ------------------------------------------------------------------ #
    # Status                                                                #
    # ------------------------------------------------------------------ #

    def set_status(self, status: str) -> None:
        self._data["status"] = status
        self._data["updated_at"] = _now_iso()
        if status in ("committed", "discarded"):
            self._archive()
        else:
            self._save()

    def set_fg_entity_id(self, entity_id: str) -> None:
        self._data["fg_entity_id"] = entity_id
        self._save()

    # ------------------------------------------------------------------ #
    # Persistence                                                           #
    # ------------------------------------------------------------------ #

    def _save(self) -> None:
        self._data["updated_at"] = _now_iso()
        path = os.path.join(SESSIONS_DIR, f"{self.id}.json")
        with open(path, "w") as f:
            json.dump(self._data, f, indent=2)

    def _archive(self) -> None:
        src = os.path.join(SESSIONS_DIR, f"{self.id}.json")
        dst = os.path.join(ARCHIVE_DIR, f"{self.id}.json")
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        if os.path.exists(src):
            os.rename(src, dst)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


# ------------------------------------------------------------------ #
# CLI helper                                                            #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="app_session.py helper")
    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="List open sessions")
    p_create = sub.add_parser("create", help="Create a new session")
    p_create.add_argument("app_name")
    p_create.add_argument("--platform", default="ios")
    p_create.add_argument("--ecosystem", default="generic")
    p_show = sub.add_parser("show", help="Show a session")
    p_show.add_argument("session_id")

    args = parser.parse_args()

    if args.cmd == "list":
        sessions = AppSession.list_open()
        if not sessions:
            print("No open sessions.")
        for s in sessions:
            print(f"  {s.id[:8]}… {s.app_name} ({s.platform}/{s.ecosystem}) "
                  f"{len(s.diffs)} diffs  created {s.created_at}")
    elif args.cmd == "create":
        s = AppSession.create(args.app_name, args.platform, args.ecosystem)
        print(f"Created session {s.id} for {s.app_name}")
    elif args.cmd == "show":
        s = AppSession.load(args.session_id)
        print(json.dumps(s.to_dict(), indent=2))
    else:
        parser.print_help()


def get_launch_url(app_slug: str) -> Optional[str]:
    """Optional: a tappable launch link for an app, if you maintain one.

    Reads the JSON file named by $FG_APP_LAUNCH_URLS ({"<slug>": "<url>", ...}).
    Returns None when the file or the slug is absent — callers then just tell
    the user to open the app by hand.
    """
    path = os.environ.get("FG_APP_LAUNCH_URLS", "")
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f).get(app_slug)
    except Exception:
        return None


def list_launch_urls() -> dict:
    path = os.environ.get("FG_APP_LAUNCH_URLS", "")
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}
