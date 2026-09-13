#!/usr/bin/env python3
"""
app_commit.py — Apply an app-walk session's diffs to FunkyGibbon.

Usage:
    python3 app_commit.py <session_id>

Writes:
  - One "app" entity in FunkyGibbon (entity_type="app")
  - Screenshots attached as photo entities (has_photo) to the app entity
  - A note entity with the full transcript
"""
from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
STATE_ROOT = os.environ.get("FG_SESSIONS_DIR", os.path.join(PROJECT_DIR, ".fg-sessions"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_session import AppSession
from fg_client import FGClient, FGError
from image_compress import compress_image


def commit(session_id: str) -> dict:
    session = AppSession.load(session_id)
    if session.status != "open":
        raise ValueError(f"Session {session_id} is {session.status}, not open.")

    fg = FGClient()

    # Build app entity content from diffs
    devices_list = []
    routines_list = []
    how_to_notes = []

    for diff in session.diffs:
        action = diff.get("action")
        if action == "add_device":
            devices_list.append(diff.get("device", {}))
        elif action == "add_routine":
            routines_list.append(diff.get("routine", {}))
        elif action == "add_how_to":
            how_to_notes.append(diff.get("note", ""))

    app_content = {
        "platform": session.platform,
        "ecosystem": session.ecosystem,
        "devices": devices_list,
        "routines": routines_list,
        "how_to_notes": how_to_notes,
        "screenshot_blob_ids": [],
    }

    # Create or update the app entity first (screenshots need the entity id)
    existing = fg.find_entity_by_name("app", session.app_name)
    if existing:
        app_entity = fg.update_entity(existing["id"], content=app_content)
        app_entity_id = existing["id"]
        created = False
    else:
        app_entity = fg.create_entity(
            entity_type="app",
            name=session.app_name,
            content=app_content,
        )
        app_entity_id = app_entity["id"]
        created = True

    session.set_fg_entity_id(app_entity_id)

    # Upload screenshots linked to the app entity
    uploaded_count = 0
    for shot in session.screenshots:
        src = shot["source_path"]
        if not os.path.exists(src):
            continue
        try:
            with open(src, "rb") as f:
                raw = f.read()
            compressed_bytes, _ = compress_image(raw)
            blob = fg.upload_blob(
                app_entity_id,
                compressed_bytes,
                f"{shot['screen_name']}.jpg",
                mime_type="image/jpeg",
            )
            app_content["screenshot_blob_ids"].append({
                "blob_id": blob["id"],
                "screen_name": shot["screen_name"],
                "description": shot.get("description", ""),
            })
            uploaded_count += 1
        except Exception as e:
            print(f"  Warning: screenshot upload failed: {e}", file=sys.stderr)

    # Patch the app entity with populated screenshot_blob_ids if any were uploaded
    if uploaded_count > 0:
        app_content_patch = dict(app_content)
        fg.update_entity(app_entity_id, content=app_content_patch)

    # Write transcript as a note linked to the app entity
    transcript_md = "\n".join(
        f"**{e['role'].upper()}** ({e['ts']}): {e['text']}"
        for e in session.to_dict().get("transcript", [])
    )
    if transcript_md:
        fg.create_entity(
            entity_type="note",
            name=f"{session.app_name} App Walk Transcript — {session.created_at}",
            content={
                "text": transcript_md,
                "linked_entity_id": app_entity_id,
                "session_id": session.id,
            },
        )

    # Read back with a fresh client before archiving: "saved" means present on the server.
    verifier = FGClient()
    if not verifier.get_entity(app_entity_id):
        raise FGError(f"app entity {app_entity_id} not readable after commit — session left open")
    session.set_status("committed")

    return {
        "app_entity_id": app_entity_id,
        "created": created,
        "devices_recorded": len(devices_list),
        "routines_recorded": len(routines_list),
        "screenshots_uploaded": uploaded_count,
        "session_id": session.id,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: app_commit.py <session_id>")
        sys.exit(1)

    result = commit(sys.argv[1])
    print(json.dumps(result, indent=2))
