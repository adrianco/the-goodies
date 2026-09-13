# Claude Code skills for The Goodies

Conversational room cataloguing for a house graph, as Claude Code skills. Written
and used at a real install; contributed here so the generic parts live next to the
server they talk to.

| Skill | What it does |
|---|---|
| `room-walk` | Stand in a room and catalogue it — devices, keypads, doors, photos — through conversation. Nothing is written until the user reviews a diff and says `confirm`. |
| `room-edit` | Targeted edits to an already-catalogued room: rename, aliases, move between rooms, mark inoperable, delete (tombstone), attach photos and notes. Same review-then-confirm flow. |
| `app-walk` | Catalogue what a phone/web app controls (devices, routines, how-tos, screenshots) into an `app` entity. |
| `align-rooms` | Reconcile room names across Home Assistant, HomeKit and The Goodies. |

## How it talks to the server

Everything goes through the **MCP tool surface** — `POST /api/v1/mcp/tools/<tool>` with a
bearer token — via `scripts/fg_client.py`. That is the client interface as of v0.7.0
(ADR-015); the graph REST API is gone. The client keeps a small, stable Python API
(`create_entity`, `list_entities`, `create_relationship`, `upload_blob`, …) so the
skills read naturally, and maps it onto the tools:

- photos → `attach_photo` (a `photo` entity linked `has_photo`), PDFs → `attach_document`
- delete → `tombstone_entity`; a move → `end_relationship` + `create_relationship` (ADR-004)
- `list_relationships` / `get_connected` / `get_blob` are exposed directly

## The one design rule: local until saved

A walk or edit accumulates **diffs in a local session file** (`$FG_SESSIONS_DIR`, default
`./.fg-sessions`) with photos staged alongside. `room_commit.py` applies them only on
`confirm`, then **reads every created entity back with a fresh client** and archives the
session only if all of it is present. A commit that cannot be verified leaves the session
open to re-run. "Saved" means confirmed in the graph, not "the calls returned 200".

## Install

```
cp -r skills/claude-code/scripts/*  <your-project>/.claude/scripts/
cp -r skills/claude-code/room-walk  <your-project>/.claude/skills/
# likewise room-edit, app-walk, align-rooms
pip install pillow          # photo compression; everything else is stdlib
```

Configuration (environment):

| Variable | Purpose | Default |
|---|---|---|
| `FUNKYGIBBON_URL` | server | `http://localhost:8000` |
| `FUNKYGIBBON_TOKEN` | client token (`setup_auth --client-token-only …`) | read from `~/.oook/config.json` / `.blowingoff.json` |
| `FG_SESSIONS_DIR` | where session files and staged photos live | `./.fg-sessions` |
| `REVIEW_POST_URL` / `REVIEW_POST_TOKEN` | optional endpoint that turns review markdown into a shareable page | write a file instead |
| `FG_APP_LAUNCH_URLS` | optional JSON `{slug: url}` of app launch links for `app-walk` | none |
| `HA_URL` / `HA_TOKEN`, `HOMEKIT_DUMP` | for `align-rooms` | — |

Site-specific probes (a lighting controller, a network controller, a HomeKit export) are
referenced by the skills as **optional examples** and are not included — bring your own or
skip those steps.

## Verify against a live server

```
python3 .claude/scripts/fg_client_selftest.py
```

23 gates: reads, writes read back from a **separate process**, a photo round-tripped
byte-for-byte through `attach_photo`/`get_blob`, a move with history retained, tombstones.
Uses throwaway entities and tombstones them at the end.

## Known vocabulary gaps (v0.7.0)

- `device part_of device` is refused although the HOUSE manifest declares it (#90) —
  `room_commit.py` records `content.part_of_device_id` on the button meanwhile.
- No device → note edge (#91) — notes about a device are kept in `content.notes`.
