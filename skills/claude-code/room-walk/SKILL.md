---
name: room-walk
description: Interactive room cataloging — the user stands in a room, conversationally catalogs everything (devices, keypads, doors, non-networked items) with photo support and optional live probing of your lighting/network controllers; produces a reviewable diff that commits to FunkyGibbon (the-goodies) over MCP.
metadata:
  user_invocable: "true"
---

# /room-walk

Catalog what's physically in a room — devices, keypads, doors, sensors — through a guided conversation. Nothing writes to FunkyGibbon until you review and confirm.


## When to use

- the user says "let's walk [room]" / "I'm in [room], let's catalog it" / `/room-walk [room]`
- the user wants to document what's in a new or previously-uncatalogued area
- After a renovation or device installation

For editing an already-catalogued room (rename, remove, fix), use `/room-edit` instead.

## Required helpers

All under `.claude/scripts/` (copy them there from `skills/claude-code/scripts/`):
- `fg_client.py` — FunkyGibbon client over MCP tools (the-goodies ≥ v0.7.0; the graph REST API no longer exists). Writes are tombstones/interval edges: nothing is ever destroyed.
- *(optional, site-specific, not included)* probe scripts for your controllers — the examples below use a `vantage_probe` (lighting) and a `unifi_probe` (network); write your own or skip those steps
- `room_session.py` — session state (in `$FG_SESSIONS_DIR/room-sessions/`)
- `render_review.py` — generates the review markdown; publishes to `REVIEW_POST_URL` if set, else writes a file
- `room_commit.py` — applies diffs on confirm
- `image_compress.py` — downsamples photos before upload

All are Python 3.11+; only Pillow (`pip install pillow`) is needed beyond the standard library, for photo compression.

## The conversation shape

You run a continuous conversation with the user over your messaging channel. Between the user's messages, you keep session state on disk — every Bash call creates/updates a session file. Never commit without a review-confirmed step.

### Phase 1 — Orient

1. **Resolve the room**. Use `fg_client.py` to find the room by name:
   ```python
   import sys; sys.path.insert(0, '.claude/scripts')
   from fg_client import FGClient
   fg = FGClient()
   rooms = fg.list_entities("room")
   ```
   - If the user's room name matches exactly (case-insensitive): great.
   - If ambiguous (multiple matches), ask which one.
   - If no match, offer: "No room called X. Should I create a new room, or did you mean [list similar]?"

2. **Check for open sessions** for that room:
   ```python
   from room_session import RoomSession
   open_sessions = RoomSession.find_open_for_room(room_name)
   ```
   If one exists, ask: "You have a walk in progress for [room] from [timestamp]. Resume, or start fresh (the old one will stay in `$FG_SESSIONS_DIR/room-sessions/` for reference)?"

3. **Create the session**:
   ```python
   snapshot = {
       "devices": fg.list_devices_in_room(room_id),
       "doors": fg.list_doors_for_room(room_id),
   }
   session = RoomSession.create(room_entity_id=room_id, room_name=room_name,
                                 mode="walk", initial_snapshot=snapshot)
   ```

4. **Load your smart-home inventories** — query every system you have integrated for this room's footprint. Everything in this step is optional and site-specific; the shapes below are examples of what such probes return. Skip what you don't have.

   **HomeKit** (if you have an export of HomeKit rooms/accessories — e.g. a script reading `~/Library/HomeKit/core.sqlite`, which needs Full Disk Access): filter it to this room. HomeKit room names may differ from FunkyGibbon room names — check adjacent rooms too.

   **Lighting controller** (example: a Vantage probe exposing loads and keypads):
   ```python
   from vantage_probe import VantageProbe
   v = VantageProbe()
   v.load_inventory()
   vantage_loads = v.find_loads_in_area(room_name)  # fuzzy area match
   vantage_stations = v.find_stations_in_area(room_name)
   ```

   **Network controller** (example: a UniFi probe listing clients near the room's access point):
   ```python
   from unifi_probe import UniFi
   from fg_client import FGClient
   u = UniFi()
   u.load_inventory()
   fg = FGClient()
   all_fg_devices = fg.list_entities('device')
   # Build a set of MACs already catalogued in any room
   catalogued_macs = set()
   for d in all_fg_devices:
       net = d.get('content', {}).get('network', {})
       if net.get('mac') and d.get('located_in_room_id'):
           catalogued_macs.add(net['mac'].lower())
   candidates = u.clients_near(room_name)
   # Exclude already-catalogued devices
   new_candidates = [
       e for e in candidates
       if e['client']['mac_address'].lower() not in catalogued_macs
   ]
   already_placed = [e for e in candidates if e not in new_candidates]
   # Mention excluded count but don't surface them
   # e.g. "3 devices on this AP are already catalogued in other rooms — skipping those"
   candidates = new_candidates
   ```

   **Home Assistant** (if you run it; set `HA_TOKEN`):
   ```bash
   curl -s "$HA_URL/api/states" -H "Authorization: Bearer $HA_TOKEN" 2>/dev/null | python3 -c "import json,sys; [print(e['entity_id'], e['state']) for e in json.load(sys.stdin) if '<room>' in e.get('attributes',{}).get('friendly_name','').lower()]"
   ```

   **Amazon Alexa / Google Home / other hubs**: Check if the user has mentioned these for this home. If configured, query them. Otherwise note "not configured".

5. **Report findings** to the user on your messaging channel:
   > "We're in **[room]**. FunkyGibbon has N devices here: [names]. [Each probe you ran: what it found.] Anything missing or wrong?"

### Phase 2 — Discovery loop

Drive entirely by the user's input. For each thing the user mentions, add a diff via `session.add_diff(...)`. Common patterns:

**New device already known to a controller** (example: a Vantage load not yet in FunkyGibbon):
the user: "there's a fountain at the entry, Vantage calls it POUNTAIN"
```python
session.add_diff({
    "action": "create_device",
    "draft": {
        "name": "Entry Fountain",
        "content": {
            "system": {"kind": "vantage", "vid": 2454, "area_vid": 2448,
                       "original_name": "ENTRY POUNTAIN"},
            "aliases": ["the fountain", "entry water feature"],
            "status": "operational",
            "notes": "Vantage name has a typo — cleaned to Entry Fountain",
        },
        "located_in_room_id": room_id,
    },
})
```

**Probe a load to identify it** (if your lighting probe supports it — full flash, 3s by default):
```python
v.flash_load(1781, duration=3.0)
```
Narrate: "Flashing load 1781 for 3 seconds — tell me which light that is."

**New device with no controller integration** (Alexa, Tuya, HomeKit-only, etc.):
the user: "there's an Echo Dot on the side table"
```python
session.add_diff({
    "action": "create_device",
    "draft": {
        "name": "Side Table Echo Dot",
        "content": {
            "system": {"kind": "alexa", "model": "Echo Dot 5th gen"},
            "aliases": ["the Echo", "Alexa"],
            "control_status": "catalogued_only",  # no integration yet
            "status": "operational",
        },
        "located_in_room_id": room_id,
    },
})
```

**Photo attachment** — the user sends a photo on your messaging channel:
The photo will be available as a file (Read tool can show it to you).
```python
photo_id = session.attach_photo(
    source_path=photo_file_path,
    parent_hint="entry keypad",
    description="6-button keypad by front door"
)
```
Then reference it in a draft via `"photos": [photo_id]`.

**Sending a photo back to the user** — use whatever your messaging channel provides for images.

**Keypad** — the user photographs the keypad; vision extracts button labels:
```python
# After reading the image and identifying labels
session.add_diff({
    "action": "create_keypad",
    "draft": {
        "name": "Living Room Entry Keypad",
        "content": {
            "aliases": ["the switch by the door"],
            "system": {"kind": "vantage", "vid": 2103,
                       "station_type": "Keypad", "button_count": 6},
        },
        "located_in_room_id": room_id,
        "photos": [photo_id],
        "buttons": [
            {
                "name": "Overhead",
                "content": {
                    "label_raw": "OVERHEAD",
                    "system": {"kind": "vantage", "vid": 2105,
                               "keypad_vid": 2103, "position": 1},
                },
                "controls": ["<existing-load-entity-id>"],  # if known
            },
            # ... more buttons
        ],
    },
})
```
For each button, interactively probe/ask (if you have a lighting probe): "Button 2 is labeled 'CANS'. I'll flash load 2231 — tell me if that's the cans."

   Note: at the-goodies v0.7.0 the HOUSE manifest refuses `device part_of device` (issue #90). `room_commit.py` records the composition as `content.part_of_device_id` on each button and attaches the edge once the vocabulary allows it.

**Door**:
the user: "there's a door to the garage with a Schlage lock"
```python
session.add_diff({
    "action": "create_door",
    "draft": {
        "name": "Living Room to Garage Door",
        "content": {
            "aliases": ["garage door"],
            "is_lock_smart": True,
            "lock_device_id": "<schlage-entity-id-from-homekit>",
            "is_exterior": False,
        },
        "connects_to": [room_id, "<garage-room-id>"],
    },
})
```

**Mis-located existing device** — if FunkyGibbon has a device in a different room but the user says it's here:
```python
session.add_diff({
    "action": "move_to_room",
    "entity_id": "<existing-device-id>",
    "new_room_id": room_id,
})
```

**Inoperable / replaced device**:
```python
session.add_diff({
    "action": "set_status",
    "entity_id": "<existing-device-id>",
    "status": "inoperable",
    "reason": "dead, needs replacement",
})
```

**Cross-reference from your network controller** (example: UniFi clients near the room's AP/switch):

```python
from unifi_probe import UniFi
u = UniFi()
u.load_inventory()

# Find clients near the AP that matches this room (AP names often include
# room names: "AP Family Room TV", "AP Study", etc.)
candidates = u.clients_near(room_name)
for entry in candidates:
    c = entry["client"]
    print(f"  {c['name']} ({c['ip_address']}, {c['mac_address']}) via {entry['ap_name']}")
```

Report candidates to the user:
> "I see these devices on the Family Room AP: Apple TV (10.0.0.74), a weather station (10.0.0.166), the wall oven (10.0.0.25), a freezer, a water heater. Which of these should I catalog in this room?"

For each that the user confirms, include the network metadata in the device's content:
```python
session.add_diff({
    "action": "create_device",
    "draft": {
        "name": "Apple TV 4K (Family Room)",
        "content": {
            "system": {"kind": "homekit", "accessory_id": "..."},
            "network": {
                "mac": "50:de:06:b0:03:15",
                "ipv4_hint": "10.0.0.74",
                "unifi_client_id": "...",
                "ap": "AP Family Room TV",
            },
            "aliases": ["Apple TV", "family room TV"],
        },
        "located_in_room_id": room_id,
    },
})
```

MAC is stable, IP is a hint (DHCP). Store both.

### Phase 2.5 — Iterate

Between diffs, keep transcribing:
```python
session.log("user", "<what the user said>")
session.log("agent", "<what you said back>")
```

Don't send a review after every single diff — batch. When the user indicates they're done (says "that's it", "done", "wrap it up", "let's review") or you've covered the obvious, move to Phase 3.

### Phase 3 — Review

1. **Post the review**:
   ```python
   from render_review import post_session_review
   view = post_session_review(session)
   ```
2. **Send the review** to the user: `view` carries a URL (`tunnelUrl`/`localUrl`/`url`) when `REVIEW_POST_URL` is configured, otherwise `view["path"]` is a markdown file — send the link, or the content. Ask them to reply `confirm` to commit, or say what to change.

3. **Wait** for the user's response. Don't commit anything yet.

### Phase 4 — Edit or Confirm

If the user says "confirm" (or "yes", "do it", "commit"):
```bash
python3 .claude/scripts/room_commit.py <session.id>
```
Then message the result: number of entities created, any errors, and if applicable, how many photos were attached.

If the user requests changes ("rename X to Y", "remove that door"):
- Parse the change, modify the session diffs via `session.remove_diff(idx)` / `session.replace_diff(idx, new_diff)` / `session.add_diff(...)`
- Regenerate and post the review again
- Wait for confirm

If the user says "discard" or "cancel":
```python
session.set_status("discarded")
```
The session is archived (never deleted) but won't be applied.

### Phase 5 — Handoff

After commit:
- Record a brief summary wherever your agent keeps handoff notes (if it has them)
- Add a one-line entry to your agent's long-term memory, e.g. `2026-04-13: Living Room — catalogued 5 new devices, 1 keypad (6 buttons), 2 doors. Session abc123…`
- message the user with the commit summary and session UUID

## Important constraints

- **Never touch the database directly.** Always go through `fg_client.py` (MCP tools) — the graph REST API no longer exists.
- **Never commit without the review + confirm cycle.** Even if the user is impatient.
- **If you probe lights**, full flash is fine in daytime; if the user asks for gentle flash ("it's dark / the baby's asleep"), lower the duration and level for that session.
- **Photos are always downsampled** before upload (`image_compress.compress_image`). Don't skip this — the default compresses to ~100KB JPEG.
- **Sessions never expire.** If you find an open session for a room, ask before clobbering — archived sessions are audit trail, never auto-purged.
- **Keep the transcript** (`session.log()`) so the review and the saved note both have context.
- **Be willing to wait.** the user may leave the room and come back. Session state persists across agent restarts. On resume, read the session file to pick up where you left off.

## What success looks like

End of a successful walk:
- FunkyGibbon has new `device`/`door`/`room` entities with clean names, aliases, system metadata, and `photo` attachments
- Relationships (`located_in`, `connects_to`, `controls`, and `part_of` where the vocabulary allows) are in place
- A `note` entity captures the session transcript, linked `documented_by` to the room
- Your agent's memory has a one-line log entry
- Session JSON is archived in `$FG_SESSIONS_DIR/room-sessions/archive/`
- the user got a confirmation message with numbers: "Committed: N entities created, K photos uploaded, 0 errors"
