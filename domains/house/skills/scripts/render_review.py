#!/usr/bin/env python3
"""
render_review.py — Render a session draft as markdown for user review.

If REVIEW_POST_URL is set, the markdown is POSTed there as
{"title": ..., "markdown": ...} with an optional REVIEW_POST_TOKEN bearer, and
the JSON response is returned (expected to carry a URL in "tunnelUrl",
"localUrl" or "url"). Otherwise the markdown is written to
$FG_SESSIONS_DIR/reviews/<session>.md and {"path": ...} is returned — send
the user the file, or paste it into your channel.

Reads:
- A session id (from room_session)
- Optionally a current snapshot fetched live from FunkyGibbon (via fg_client)

Writes:
- A markdown review document that describes, in plain language, exactly what
  will happen if the session commits
- Posts it to REVIEW_POST_URL (if set) or writes it to a file

The review document ALWAYS begins with a prominent banner explaining that
nothing has been written yet. The user must reply `confirm` for the commit
phase to run.

Usage:
    from render_review import build_review_markdown, post_review

    md = build_review_markdown(session)
    view = post_review(title, md)
    print(view["tunnelUrl"])
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
STATE_ROOT = os.environ.get("FG_SESSIONS_DIR", os.path.join(PROJECT_DIR, ".fg-sessions"))
REVIEW_POST_URL = os.environ.get("REVIEW_POST_URL", "")
REVIEW_POST_TOKEN = os.environ.get("REVIEW_POST_TOKEN", "")


def post_review(title: str, markdown: str, session_id: str = "review") -> Dict[str, Any]:
    """Publish the review: POST to REVIEW_POST_URL if configured, else write a file."""
    if REVIEW_POST_URL:
        body = json.dumps({"title": title, "markdown": markdown}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if REVIEW_POST_TOKEN:
            headers["Authorization"] = f"Bearer {REVIEW_POST_TOKEN}"
        req = urllib.request.Request(REVIEW_POST_URL, data=body, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    out_dir = os.path.join(STATE_ROOT, "reviews")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{session_id}.md")
    with open(path, "w") as f:
        f.write(markdown)
    return {"path": path}


def _header(session) -> List[str]:
    lines = [
        f"# {session.mode.title()}: {session.room_name}",
        "",
        "> ⚠️ **Preview only — no changes have been written to FunkyGibbon.**",
        "> Reply `confirm` to commit, or describe what you want changed.",
        "",
        f"**Session:** `{session.id[:8]}…`",
        f"**Started:** {session.data.get('started_at','?')}",
        f"**Diffs pending:** {len(session.diffs)}",
        "",
    ]
    return lines


def _render_draft_device(draft: Dict[str, Any]) -> List[str]:
    name = draft.get("name", "(unnamed)")
    system = draft.get("content", {}).get("system") or draft.get("content", {}).get("systems")
    aliases = draft.get("content", {}).get("aliases") or []
    out = [f"- **{name}**"]
    if system:
        if isinstance(system, list):
            system_desc = ", ".join(
                f"{s.get('kind','?')} (" + ", ".join(f"{k}={v}" for k, v in s.items() if k != "kind") + ")"
                for s in system
            )
        else:
            system_desc = f"{system.get('kind','?')} (" + ", ".join(
                f"{k}={v}" for k, v in system.items() if k != "kind"
            ) + ")"
        out.append(f"  - System: {system_desc}")
    if aliases:
        out.append(f"  - Aliases: {', '.join(aliases)}")
    status = draft.get("content", {}).get("status")
    if status and status != "operational":
        out.append(f"  - Status: **{status}**")
    notes = draft.get("content", {}).get("notes")
    if notes:
        out.append(f"  - Notes: {notes}")
    if draft.get("photos"):
        out.append(f"  - Photos attached: {len(draft['photos'])}")
    return out


def _render_draft_door(draft: Dict[str, Any]) -> List[str]:
    name = draft.get("name", "(unnamed)")
    content = draft.get("content", {})
    out = [f"- **{name}** (door)"]
    if content.get("is_lock_smart"):
        out.append("  - Smart lock")
    elif content.get("manual_lock_type"):
        out.append(f"  - Manual: {content['manual_lock_type']}")
    if content.get("is_exterior"):
        out.append("  - Exterior")
    if draft.get("connects_to"):
        out.append(f"  - Connects rooms: {len(draft['connects_to'])}")
    return out


def _render_draft_keypad(draft: Dict[str, Any]) -> List[str]:
    name = draft.get("name", "(unnamed keypad)")
    content = draft.get("content", {})
    out = [f"- **{name}** (keypad)"]
    bc = (content.get("system") or {}).get("button_count") or content.get("button_count")
    if bc:
        out.append(f"  - {bc} buttons")
    if draft.get("photos"):
        out.append(f"  - Keypad photos: {len(draft['photos'])}")
    if draft.get("buttons"):
        out.append(f"  - Buttons:")
        for b in draft["buttons"]:
            action = ""
            if b.get("controls"):
                action = f" controls → {len(b['controls'])} load(s)"
            elif b.get("triggered_by"):
                action = f" triggers task"
            out.append(f"    - *{b.get('name','(unnamed)')}*{action}")
    return out


def _render_draft_room(draft: Dict[str, Any]) -> List[str]:
    name = draft.get("name", "(unnamed)")
    content = draft.get("content", {})
    aliases = content.get("aliases") or []
    out = [f"- **{name}** (new room)"]
    if content.get("source_type"):
        out.append(f"  - Source: {content['source_type']}")
    if aliases:
        out.append(f"  - Aliases: {', '.join(aliases)}")
    return out


def _render_update_diff(d: Dict[str, Any]) -> List[str]:
    action = d["action"]
    eid = (d.get("entity_id") or "?")[:8]
    if action == "rename_entity":
        return [f"- Rename `{eid}…`: *{d.get('old_name','?')}* → **{d.get('new_name','?')}**"]
    if action == "add_alias":
        return [f"- Add alias to `{eid}…`: *{d.get('alias')}*"]
    if action == "remove_alias":
        return [f"- Remove alias from `{eid}…`: *{d.get('alias')}*"]
    if action == "set_status":
        reason = f" — {d.get('reason')}" if d.get("reason") else ""
        return [f"- Mark `{eid}…` as **{d.get('status')}**{reason}"]
    if action == "move_to_room":
        return [f"- Move `{eid}…` → room `{(d.get('new_room_id') or '?')[:8]}…`"]
    if action == "delete_entity":
        reason = f" — {d.get('reason')}" if d.get("reason") else ""
        return [f"- **Delete** `{eid}…`{reason}"]
    if action == "update_device":
        patch = d.get("patch") or {}
        bits = []
        if patch.get("name"):
            bits.append(f"name → *{patch['name']}*")
        if patch.get("content_merges"):
            bits.append(f"content changes: {list(patch['content_merges'].keys())}")
        if patch.get("aliases_add"):
            bits.append(f"+aliases {patch['aliases_add']}")
        if patch.get("aliases_remove"):
            bits.append(f"-aliases {patch['aliases_remove']}")
        return [f"- Update `{eid}…`: {'; '.join(bits) or '(no-op)'}"]
    if action == "add_note":
        return [f"- Attach note to `{eid}…`: *{(d.get('note_text','') or '')[:80]}*"]
    if action == "attach_photo":
        desc = d.get("description") or ""
        return [f"- Attach photo to `{eid}…`{': ' + desc if desc else ''}"]
    return [f"- {action}: {json.dumps({k: v for k, v in d.items() if k not in ('action','idx','added_at')}, default=str)}"]


def build_review_markdown(session) -> str:
    """Render a session's diffs + transcript + snapshot into markdown."""
    lines: List[str] = []
    lines += _header(session)

    # ── Summary ──
    counts: Dict[str, int] = {}
    for d in session.diffs:
        counts[d["action"]] = counts.get(d["action"], 0) + 1
    if counts:
        lines.append("## Summary")
        for action, n in sorted(counts.items()):
            pretty = action.replace("_", " ")
            lines.append(f"- **{n}×** {pretty}")
        lines.append("")

    # ── Group diffs by category ──
    creates_device: List[Dict[str, Any]] = []
    creates_door: List[Dict[str, Any]] = []
    creates_keypad: List[Dict[str, Any]] = []
    creates_room: List[Dict[str, Any]] = []
    creates_task: List[Dict[str, Any]] = []
    updates: List[Dict[str, Any]] = []
    for d in session.diffs:
        a = d["action"]
        if a == "create_device":
            creates_device.append(d)
        elif a == "create_door":
            creates_door.append(d)
        elif a == "create_keypad":
            creates_keypad.append(d)
        elif a == "create_room":
            creates_room.append(d)
        elif a == "create_task_auto":
            creates_task.append(d)
        else:
            updates.append(d)

    if creates_room:
        lines.append("## New Rooms")
        for d in creates_room:
            lines += _render_draft_room(d.get("draft", {}))
        lines.append("")

    if creates_device:
        lines.append("## New Devices")
        for d in creates_device:
            lines += _render_draft_device(d.get("draft", {}))
        lines.append("")

    if creates_keypad:
        lines.append("## New Keypads")
        for d in creates_keypad:
            lines += _render_draft_keypad(d.get("draft", {}))
        lines.append("")

    if creates_door:
        lines.append("## New Doors")
        for d in creates_door:
            lines += _render_draft_door(d.get("draft", {}))
        lines.append("")

    if creates_task:
        lines.append("## New Task Automations")
        for d in creates_task:
            draft = d.get("draft", {})
            lines.append(f"- **{draft.get('name','(unnamed)')}**")
        lines.append("")

    if updates:
        lines.append("## Updates")
        for d in updates:
            lines += _render_update_diff(d)
        lines.append("")

    # ── Photos attached this session ──
    photos = session.data.get("photos") or {}
    if photos:
        lines.append("## Photos Captured")
        lines.append(
            f"_{len(photos)} photo(s) attached during this session. "
            "They'll be attached as photo entities (has_photo) to the relevant devices on commit._"
        )
        for pid, meta in photos.items():
            desc = meta.get("description") or "(no description)"
            hint = meta.get("parent_hint") or ""
            lines.append(f"- `{pid[:12]}…` {desc}{' — for ' + hint if hint else ''}")
        lines.append("")

    # ── Initial snapshot footer (what was already there) ──
    snap = session.data.get("initial_snapshot") or {}
    if snap:
        lines.append("## What was already in this room at session start")
        for key in ("devices", "doors", "keypads"):
            items = snap.get(key) or []
            if items:
                lines.append(f"- {len(items)} {key}")
        lines.append("")

    # ── Transcript ──
    transcript = session.data.get("transcript") or []
    if transcript:
        lines.append("## Transcript")
        lines.append("")
        for entry in transcript[-50:]:  # keep the review readable
            role = entry.get("role", "?")
            text = entry.get("text", "").replace("\n", " ")
            icon = "👤" if role == "user" else "🤖" if role == "agent" else "ℹ️"
            lines.append(f"{icon} **{role}:** {text}")
        lines.append("")

    # ── Footer ──
    lines.append("---")
    lines.append("")
    lines.append("Reply `confirm` to apply these changes, or describe what you'd like changed.")
    return "\n".join(lines)


def post_session_review(session) -> Dict[str, Any]:
    """Build markdown, POST to /view, and record the review URL on the session."""
    md = build_review_markdown(session)
    mode = "Walk" if session.mode == "walk" else "Edit"
    title = f"Room {mode} Review: {session.room_name}"
    view = post_review(title, md, session_id=session.id)
    session.set_review_url(view.get("tunnelUrl") or view.get("localUrl") or view.get("url") or view.get("path") or "")
    return view


# ── CLI ──────────────────────────────────────────────────────────────────────


def _cli() -> int:
    import argparse

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from room_session import RoomSession

    p = argparse.ArgumentParser()
    p.add_argument("session_id", help="UUID or prefix of a session")
    p.add_argument("--post", action="store_true", help="publish (REVIEW_POST_URL or a file) instead of printing markdown")
    args = p.parse_args()

    # Resolve session id by prefix
    all_sessions = RoomSession.list_all(include_archived=True)
    matches = [s for s in all_sessions if s["id"].startswith(args.session_id)]
    if not matches:
        print(f"No session matching '{args.session_id}'", file=sys.stderr)
        return 2
    if len(matches) > 1:
        print(f"Ambiguous prefix '{args.session_id}' — matches {len(matches)}", file=sys.stderr)
        return 2
    s = RoomSession.load(matches[0]["id"])

    if args.post:
        view = post_session_review(s)
        print(view.get("tunnelUrl") or view.get("localUrl") or view.get("url") or view.get("path"))
    else:
        print(build_review_markdown(s))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
