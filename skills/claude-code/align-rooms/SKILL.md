---
name: align-rooms
description: Align room/area naming across HA, HomeKit, and FunkyGibbon — shows mismatches, asks which system is canonical (or auto-detects the most complete), then applies renames and creates missing rooms.
metadata:
  user_invocable: "true"
---

# /align-rooms

Synchronise room names across Home Assistant, HomeKit, and FunkyGibbon. Nothing writes until you review and confirm.

## When to use

- After adding areas in Home Assistant that don't yet exist in HomeKit or FunkyGibbon
- When HomeKit rooms have different names than HA areas
- First-time setup: populating FunkyGibbon rooms from HA (the most complete source)
- After renaming rooms in any single system and wanting to propagate changes

## Required scripts / helpers

- a HomeKit room export, if you have one (e.g. a script reading `~/Library/HomeKit/core.sqlite`, which needs Full Disk Access) — *not included*
- the Home Assistant REST API (`HA_URL`, `HA_TOKEN`)
- FunkyGibbon via the MCP-backed client `.claude/scripts/fg_client.py` (the graph REST API was removed in the-goodies v0.7.0; auth is a client token, handled by the client)

## HA configuration

Set `HA_URL` (e.g. `http://homeassistant.local:8123`) and `HA_TOKEN` (a long-lived access token) in the environment.

## Phase 1 — Gather data

### 1a. HA areas

```python
import json, os, subprocess
ha_url = os.environ["HA_URL"]
ha_token = os.environ["HA_TOKEN"]

result = subprocess.run([
    'curl', '-s',
    '-H', f'Authorization: Bearer {ha_token}',
    '-X', 'POST',
    '-H', 'Content-Type: application/json',
    '-d', '{"template": "{% set areas_list = namespace(items=[]) %}{% for area_id in areas() %}{% set areas_list.items = areas_list.items + [{\\\"id\\\": area_id, \\\"name\\\": area_name(area_id)}] %}{% endfor %}{{ areas_list.items | tojson }}"}',
    f'{ha_url}/api/template'
], capture_output=True, text=True)

ha_areas = json.loads(result.stdout)
# -> [{"id": "entrance_hall", "name": "Entrance Hall"}, ...]
```

### 1b. HomeKit rooms

Load your HomeKit export (skip HomeKit entirely if you have none — the comparison then runs HA vs FunkyGibbon):

```python
import json
hk_data = json.load(open(os.environ.get("HOMEKIT_DUMP", "homekit-dump.json")))
hk_rooms = [
    {"name": r["name"], "uuid": r.get("uuid"), "accessory_count": len(r.get("accessories", []))}
    for r in hk_data.get("rooms", [])
    if r.get("name")  # skip None/unnamed
]
```

### 1c. FunkyGibbon rooms

```python
import sys; sys.path.insert(0, '.claude/scripts')
from fg_client import FGClient
fg = FGClient()
fg_rooms = fg.list_entities("room")   # current rooms; tombstoned ones excluded
```

## Phase 2 — Compare

Build a comparison table. Match by lowercased name (exact, then fuzzy).

```python
def normalize(name):
    return name.lower().strip()

ha_by_norm = {normalize(a["name"]): a for a in ha_areas}
hk_by_norm = {normalize(r["name"]): r for r in hk_rooms}
fg_by_norm = {normalize(r["name"]): r for r in fg_rooms}

all_norms = sorted(set(list(ha_by_norm.keys()) + list(hk_by_norm.keys()) + list(fg_by_norm.keys())))

comparison = []
for norm in all_norms:
    ha = ha_by_norm.get(norm)
    hk = hk_by_norm.get(norm)
    fg = fg_by_norm.get(norm)
    comparison.append({
        "norm": norm,
        "ha": ha["name"] if ha else None,
        "hk": hk["name"] if hk else None,
        "fg": fg["name"] if fg else None,
    })
```

Fuzzy matching: use `difflib.get_close_matches` to find near-matches (threshold 0.75):

```python
import difflib
unmatched_hk = [r["name"] for r in hk_rooms if normalize(r["name"]) not in ha_by_norm]
for hk_name in unmatched_hk:
    close = difflib.get_close_matches(normalize(hk_name), list(ha_by_norm.keys()), n=1, cutoff=0.6)
    if close:
        ha_match = ha_by_norm[close[0]]
        print(f"  HK '{hk_name}' ≈ HA '{ha_match['name']}' (fuzzy match)")
```

## Phase 3 — Determine canonical source

**Auto-detect**: the system with the most rooms is the canonical source.

```python
counts = {"HA": len(ha_areas), "HomeKit": len(hk_rooms), "FunkyGibbon": len(fg_rooms)}
canonical = max(counts, key=counts.get)
print(f"Most complete: {canonical} ({counts[canonical]} rooms)")
```

**User override**: If the user specifies ("HA is canonical", "use HomeKit"), use that instead.

Send a message to the user:
```
HA has 44 areas, HomeKit has 9 rooms, FunkyGibbon has N rooms.
HA is the most complete — I'll use it as the source of truth.
Want me to proceed with that, or pick a different source?
```

Wait for confirmation before Phase 4.

## Phase 4 — Build the change plan

Given canonical = HA (the typical case):

### FunkyGibbon: create missing rooms

For each HA area not in FunkyGibbon (by normalized name):
```python
fg_creates = [
    a for a in ha_areas
    if normalize(a["name"]) not in fg_by_norm
]
```

### HomeKit: identify renames and missing rooms

```python
# Exact matches → no change needed
# Fuzzy matches → rename in HomeKit (HA name is canonical)
# HA areas not in HK → note as "create in Home app" (manual step)
hk_renames = []  # [{"from": hk_name, "to": ha_name}]
hk_missing = []  # HA area names not in HK at all
```

Rooms to ignore (HomeKit-only, not relevant to HA): skip if instructed by user.

### Present the plan

Report to the user on your messaging channel:
```
Here's what I'll change:

FunkyGibbon — create 38 new rooms:
  Entrance Hall, Hall, Sitting Room, ... (all 38)

HomeKit renames (3):
  "Office" → "Study"
  "Home Cinema" → "TV Lounge"
  "Hallway" → "Entrance Hall"

HomeKit missing rooms (35 HA areas not yet in HomeKit):
  These can only be added in the Home app — I'll list them
  for you to add when convenient.

Reply 'confirm' to apply FunkyGibbon + HomeKit renames,
or 'fg only' to just do FunkyGibbon, or 'show me the list'.
```

## Phase 5 — Apply changes

### 5a. FunkyGibbon room creation

For each room to create:

```python
import subprocess, json

def fg_create_room(name, ha_area_id=None):
    payload = {
        "entity_type": "room",
        "name": name,
        "content": {
            "source": "home_assistant",
            "ha_area_id": ha_area_id,
            "aliases": [],
        },
        "source_type": "manual",
        "user_id": "agent"
    }
    ent = fg.create_entity("room", payload["name"], payload["content"])
    return ent.get("id")

created_ids = {}
for area in fg_creates:
    room_id = fg_create_room(area["name"], ha_area_id=area["id"])
    if room_id:
        created_ids[area["name"]] = room_id
    else:
        print(f"  FAILED: {area['name']}")
```

### 5b. HomeKit renames via osascript (Home app automation)

HomeKit rooms can be renamed through the Home app on macOS using UI automation.
This requires Accessibility access for the process running the script.

```bash
osascript -e '
tell application "Home"
    activate
end tell
' 2>/dev/null
```

**Preferred approach** — use the `home` CLI if available:
```bash
which home 2>/dev/null && home list --rooms 2>/dev/null
```

**Direct SQLite approach** (requires FDA + ZMKFROOM write access):
```python
import sqlite3, os
db = os.path.expanduser('~/Library/HomeKit/core.sqlite')
# IMPORTANT: stop homed before writing, restart after
# subprocess.run(['launchctl', 'unload', '/System/Library/LaunchDaemons/com.apple.homed.plist'])
# ... write ...
# subprocess.run(['launchctl', 'load', '/System/Library/LaunchDaemons/com.apple.homed.plist'])
# This is RISKY — prefer the Home app UI automation instead
```

**Safest approach** — guide the user:
If HomeKit renames are needed and neither osascript nor `home` CLI works, generate a numbered list of renames and tell the user to apply them in the Home app. Keep this list in `$FG_SESSIONS_DIR/homekit-pending-renames.json` for reference.

### 5c. HomeKit zone alignment

HomeKit Zones are groupings of rooms. HA doesn't have a direct equivalent.
Skip zone changes unless the user asks specifically.

If zones are requested:
- List current HK zones via the dump: `hk_data.get("zones", [])`
- Propose new zones based on HA area naming patterns (e.g., "Annex *" → Zone "Annex")
- Only create zones via Home app UI (no safe programmatic path)

## Phase 6 — Confirm and report

After applying:
```python
# Re-read FG to verify (fresh client = fresh requests; never trust the write's own response)
fg_rooms_after = FGClient().list_entities("room")
print(f"FunkyGibbon now has {len(fg_rooms_after)} rooms")
```

message the user:
```
Done! FunkyGibbon now has {N} rooms matching HA.
HomeKit: renamed 3 rooms via Home app automation.
Pending HomeKit additions (35 rooms only in HA) — saved to
$FG_SESSIONS_DIR/homekit-pending-additions.txt for when you want to
add them in the Home app.
```

Record a one-line summary in your agent's memory/handoff notes, e.g. `YYYY-MM-DD: align-rooms — FG populated with N rooms from HA; HomeKit renames X done, Y pending manual.`

## Default zone mapping (auto-applied when zones don't exist)

When FunkyGibbon has no zone entities, `/align-rooms` creates this default zone structure and links all rooms to their zone:

```python
DEFAULT_ZONES = {   # edit for your house — these are illustrative
    "Ground Floor": ["Entrance Hall", "Kitchen", "Living Room", "Dining Room", "Study"],
    "Upper Floor":  ["Landing", "Main Bedroom", "Main Bathroom", "Guest Bedroom"],
    "Outside":      ["Garage", "Garden", "Shed"],
}
```

To check zones:
```python
zones = fg.list_entities("zone")
```

To check which rooms are in a zone:
```python
zone = fg.get_entity(ZONE_ID, include_relationships=True)   # zone["relationships"]
```

Cache zone ids in `$FG_SESSIONS_DIR/fg-zone-ids.json` after first creation.

When a new HA area is added:
1. Create the FG room (as normal)
2. Check which zone it belongs to by name pattern match
3. Create the `located_in` relationship to the zone

## Edge cases

- **FG client error**: `fg_client` raises `FGError` with the tool name and the server's message. A 401 means the client token needs re-minting (`python -m funkygibbon.setup_auth --client-token-only --jwt-secret …` in the the-goodies checkout).
- **No HomeKit export**: run HA vs FunkyGibbon only, and say so.
- **HA unreachable**: Fails with a clear error ("Can't reach Home Assistant at $HA_URL — are you on the home network?").
- **FG server not running**: `curl -s http://localhost:8000/health` should return `{"status":"healthy"}` before attempting writes.
- **Duplicate fuzzy matches**: If two HK rooms match the same HA area, ask the user which one to keep.

## Known limitations

- HomeKit room creation (new rooms, not just renames) requires the Home app — no programmatic path.
- HomeKit zone management is Home-app-only.
- FunkyGibbon room creation works but requires the FG server to be running on port 8000.
- HomeKit direct SQLite writes are possible but risky; prefer osascript or manual guidance.
