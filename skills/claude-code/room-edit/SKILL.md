---
name: room-edit
description: Edit a previously-catalogued room — rename, add/remove aliases, move devices between rooms, fix typos, mark devices inoperable, remove dead entries. Same review-before-commit pattern as /room-walk.
metadata:
  user_invocable: "true"
---

# /room-edit

Targeted edits to an already-catalogued room. Loads the current state, walks through changes the user wants, produces a review, commits on confirm.

If the room has never been catalogued, tell the user to use `/room-walk` instead.


## When to use

- "Fix the Living Room" / "Edit [room]" / `/room-edit [room]`
- You need to rename a device, add an alias, mark something inoperable
- A device was catalogued in the wrong room — needs moving
- Removing a device that's been physically removed from the house
- Updating quirks/notes on an existing device

For adding new devices you just discovered, `/room-walk` is better (it's discovery-first). If you want to do both in one flow, start with `/room-walk` — it can also fix mis-located devices along the way.

## Helpers (shared with /room-walk)

Under `.claude/scripts/` (from `skills/claude-code/scripts/`):
- `fg_client.py` — FunkyGibbon client over MCP tools (the-goodies ≥ v0.7.0; the graph REST API no longer exists). Writes are tombstones/interval edges: nothing is ever destroyed.
- *(optional)* a lighting probe script, only if an edit needs a light flashed to identify it
- `room_session.py` — session state
- `render_review.py` — review generator (publishes to `REVIEW_POST_URL` if set, else writes a file)
- `room_commit.py` — applies diffs
- `image_compress.py` — new-photo handling

## Conversation shape

### Phase 1 — Snapshot

1. **Resolve the room** via fg_client:
   ```python
   import sys; sys.path.insert(0, '.claude/scripts')
   from fg_client import FGClient
   fg = FGClient()
   rooms = fg.list_entities("room")
   ```
   Handle ambiguity / missing rooms the same way `/room-walk` does. If the room has no devices (`list_devices_in_room` empty), suggest: "That room has no catalogued devices. Did you mean `/room-walk` instead?"

2. **Check for open sessions**:
   ```python
   open_sessions = RoomSession.find_open_for_room(room_name)
   ```
   Offer to resume if any exists.

3. **Build the snapshot**:
   ```python
   import sys; sys.path.insert(0, '.claude/scripts')
   from fg_client import FGClient
   fg = FGClient()
   room = fg.find_entity_by_name("room", room_name)
   devices = fg.list_devices_in_room(room["id"])
   doors = fg.list_doors_for_room(room["id"])
   ```

4. **Create the session in edit mode**:
   ```python
   session = RoomSession.create(
       room_entity_id=room["id"], room_name=room["name"],
       mode="edit", initial_snapshot={"devices": devices, "doors": doors},
   )
   ```

5. **Present the current state** to the user on your messaging channel. Keep it concise:
   > "**Living Room** currently has 5 devices and 2 doors:
   >   • Front Drape (Lutron) — aliases: 'west drape'
   >   • Rear Drape (Lutron)
   >   • Overhead Light (lighting load 1781) — aliases: 'ceiling'
   >   • Floor Plug (lighting load 1799)
   >   • Big Picture Light (lighting load 1781)
   >
   > Doors: Living Room to Hall (manual), Living Room to Patio (exterior, smart Schlage)
   >
   > Room aliases: 'main room', 'big room'
   >
   > What would you like to change?"

### Phase 2 — Edit loop

Parse the user's requests into diffs. Common patterns:

**Rename**:
> "Call the Big Picture Light 'Fireplace Picture Light' instead"
```python
session.add_diff({
    "action": "rename_entity",
    "entity_id": "<device-id>",
    "old_name": "Big Picture Light",
    "new_name": "Fireplace Picture Light",
})
```

**Add alias**:
> "Also call it 'the painting light'"
```python
session.add_diff({
    "action": "add_alias",
    "entity_id": "<device-id>",
    "alias": "the painting light",
})
```

**Remove alias**:
```python
session.add_diff({
    "action": "remove_alias",
    "entity_id": "<device-id>",
    "alias": "obsolete name",
})
```

**Move to another room**:
> "The Big Picture Light is actually in the Dining Room, not here"
```python
dining = fg.find_entity_by_name("room", "Dining Room")
session.add_diff({
    "action": "move_to_room",
    "entity_id": "<device-id>",
    "new_room_id": dining["id"],
})
```

**Mark inoperable** (device is broken/dead but stays in the graph for history):
> "The Owner LIFX doesn't work anymore"
```python
session.add_diff({
    "action": "set_status",
    "entity_id": "<device-id>",
    "status": "inoperable",
    "reason": "bulb died 2026-04-12",
})
```

**Delete** (device physically gone, remove from graph — versioning preserves history):
> "The old Echo Dot is gone, we threw it out"
```python
session.add_diff({
    "action": "delete_entity",
    "entity_id": "<device-id>",
    "reason": "physically removed from house",
})
```

**Update content** (system metadata, notes, etc.):
```python
session.add_diff({
    "action": "update_device",
    "entity_id": "<device-id>",
    "patch": {
        "content_merges": {"notes": "Replaced LED strip in 2026-04"},
        "aliases_add": ["new alias"],
        "aliases_remove": ["old alias"],
    },
})
```

**Attach a new photo**:
```python
photo_id = session.attach_photo(source_path="/tmp/photo.jpg",
                                 description="After replacement")
session.add_diff({
    "action": "attach_photo",
    "entity_id": "<device-id>",
    "photo_id": photo_id,
    "description": "After replacement",
})
```

**Add a note entity** documenting history:
```python
session.add_diff({
    "action": "add_note",
    "entity_id": "<device-id>",
    "note_text": "Replaced in March 2026 because of failing capacitor. Old one kept in garage shelf 3.",
})
```

### Phase 2.5 — Ambiguity handling

If the user's reference is ambiguous ("the drape"), list candidates and ask:
> "I have Front Drape and Rear Drape — which one?"

If the user refers to a device by alias and you find multiple matches, same treatment.

If the user wants a light flashed to confirm which device it is ("the one by the window") and you have a lighting probe:
```python
from vantage_probe import VantageProbe
v = VantageProbe()
v.flash_load(vid, duration=3.0)
```

### Phase 3 — Review

Same as `/room-walk`:
```python
from render_review import post_session_review
view = post_session_review(session)
# Send view['tunnelUrl'] on your messaging channel, wait for 'confirm'
```

The review groups updates into clear sections: renames, aliases, moves, status changes, deletes, content updates.

### Phase 4 — Edit or Confirm

On `confirm`:
```bash
python3 .claude/scripts/room_commit.py <session.id>
```

On `discard`:
```python
session.set_status("discarded")
```

On change requests, modify diffs and regenerate the review.

### Phase 5 — Handoff

After commit:
- Record a brief summary wherever your agent keeps handoff notes (if it has them)
- Add a one-line entry to your agent's long-term memory, e.g. `2026-04-13: Living Room — catalogued 5 new devices, 1 keypad (6 buttons), 2 doors. Session abc123…`
- message the commit summary

## Important differences from /room-walk

- **Starts from existing state** — no discovery prompts about "what else is here?"
- **Smaller diff types** dominate — mostly update/rename/move/status, rarely creates
- **Deletes are explicit** and show up clearly in the review with "DELETE" callouts
- **Deletes are tombstones** (the-goodies ≥ v0.7.0): a `deleted: true` version is appended and history survives; a move ends the old `located_in` interval and opens a new one

## Constraints (same as /room-walk)

- Never touch the database directly — MCP tools only
- Never commit without review + confirm
- Photos downsampled before upload
- Sessions never auto-expire
- Transcript preserved in the session file (audit trail)
- Commit creates a `note` entity linked `documented_by` to the room with the session summary; notes on a *device* are kept in the device's `content.notes` until the vocabulary allows a device→note edge (issue #91)

## What success looks like

- Each rename/move/status-change reflected in FunkyGibbon
- Entity versions have new `parent_versions` entries capturing the history
- A note on the room documents the edit session
- Your agent's memory has a one-line log entry
- Session archived
- the user got a confirmation message: "Edited: N renames, M moves, K status changes, 0 errors"
