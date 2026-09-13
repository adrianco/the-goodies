---
name: vehicle-walk
description: Interactive vehicle cataloguing — the user stands by a car, motorcycle or bicycle and conversationally records what it is, what is fitted to it, which tools and spares serve it, where it is kept, what was bought when, and what has been done to it; produces a reviewable diff that commits to a FunkyGibbon vehicles server over MCP. The vehicles domain's counterpart of /room-walk.
metadata:
  user_invocable: "true"
---

# /vehicle-walk

Catalogue one vehicle at a time — the machine, its parts, the tools and spares
that serve it, its purchase and its service history — through a guided
conversation. Nothing writes to FunkyGibbon until the user reviews a diff and
confirms. Same shape as the house's `/room-walk`: session file on disk, diffs
accumulated, review, `confirm`, commit read back before the session archives.

## When to use

- the user says "let's do the Outback" / "walk the garage" / `/vehicle-walk [vehicle]`
- a new vehicle, part, or tool has arrived and needs recording
- after a service or a repair, to record what was done and what came off

For a one-line edit to something already catalogued (odometer, an alias, a
part that came off), do it directly with the tools; a walk is for discovery.

## Required helpers

The house's shared scripts work unchanged against a vehicles server — the
client is domain-blind. Copy `domains/house/skills/scripts/` to
`.claude/scripts/` and point it at the vehicles endpoint:

- `fg_client.py` — FunkyGibbon over MCP tools. Set `FUNKYGIBBON_URL` to the
  vehicles server (e.g. `http://localhost:8001`) and `FUNKYGIBBON_TOKEN` to a
  client token; auth is shared with the house server, so the same token works.
- `room_session.py` — session state. Use it as-is with `room_name` = the
  vehicle's name and `mode="walk"`; the session file is what makes the walk
  resumable and auditable.
- `render_review.py` — the review markdown.
- `image_compress.py` — photos are always downsampled before upload.

There is no `vehicle_commit.py` yet: apply the diffs with `fg_client` calls
directly at commit time (Phase 4) and read every created entity back with a
fresh `FGClient()` before archiving the session — that read-back is the rule,
not the script.

## Before you start

Confirm the server is the **vehicles** domain: `fg.get_statistics()` counts
`vehicle` / `part` / `tool`, and `fg.call("get_parts_on_vehicle", ...)` exists.
If you see `room` and `device`, you are on the house server — stop and say so.

## The conversation shape

### Phase 1 — Orient

1. **Resolve the vehicle.**
   ```python
   import sys; sys.path.insert(0, '.claude/scripts')
   from fg_client import FGClient
   fg = FGClient()
   vehicles = fg.list_entities("vehicle")
   ```
   Exact name match (case-insensitive) wins; if ambiguous, ask; if absent,
   offer to create it: "No vehicle called X. New vehicle, or did you mean [...]?"

2. **Check for open sessions** with `RoomSession.find_open_for_room(vehicle_name)`
   and offer to resume.

3. **Create the session** with a snapshot of what the graph already holds:
   ```python
   snapshot = {
       "parts": fg.call("get_parts_on_vehicle", vehicle_id=vid)["parts"],
       "tools": fg.call("get_tools_for_vehicle", vehicle_id=vid)["items"],
       "issues": fg.call("get_open_issues", vehicle_id=vid)["issues"],
       "history": fg.call("get_vehicle_history", vehicle_id=vid)["events"],
   }
   session = RoomSession.create(room_entity_id=vid, room_name=vehicle_name,
                                mode="walk", initial_snapshot=snapshot)
   ```

4. **Report** what is known: "The **Outback** has 2 parts recorded, 1 open
   issue (rear brake squeal), last service 2025-08-22. What's changed?"

### Phase 2 — Discovery loop

Everything the user says becomes a diff via `session.add_diff(...)`. Use the
vocabulary's key names so the tools can answer later:

**The vehicle itself** (new, or details to fill in):
```python
session.add_diff({"action": "create_vehicle", "draft": {
    "name": "Zero SR/F",
    "content": {"kind": "motorcycle", "make": "Zero", "model": "SR/F", "year": 2023,
                "registration": "M0T0EV", "odometer": 4300, "odometer_unit": "mi",
                "aliases": ["the Zero", "the electric bike"]},
    "located_in": "<location-id>",          # a bay, shed, shelf; create one if new
}})
```
One `vehicle` type; `content.kind` says car / motorcycle / bicycle / ebike /
trailer. The server refuses invented types.

**How it was acquired:**
```python
session.add_diff({"action": "create_purchase", "draft": {
    "name": "Zero purchase",
    "content": {"date": "2023-06-20", "vendor": "Zero Motorcycles SF", "price": 21000, "currency": "USD"},
    "items": ["<vehicle-id or draft:idx>"],  # purchased_via item -> purchase
    "receipt": "<photo_id>",                  # attach_document -> invoice, optional
}})
```

**What is fitted** — walk round it: tyres, chain, battery, pads, rack, lights:
```python
session.add_diff({"action": "create_part", "draft": {
    "name": "Continental TrueContact Tour (set of 4)",
    "content": {"category": "tyres", "size": "225/60R18"},
    "fitted_to": "<vehicle-id>",
    "replaces": "<old-part-id>",              # optional: replaced new -> old
    "photos": ["<photo_id>"],
}})
```

**What came off and is kept:**
```python
session.add_diff({"action": "remove_part", "part_id": "<part-id>",
                  "reason": "worn to 3/32", "now_located_in": "<shelf-id>"})
```
At commit this **ends** the `fitted_to` interval (`end_relationship`) — never
deletes it — and adds `located_in` shelf. `get_parts_on_vehicle(at=...)` still
answers for the period it was on.

**Tools and spares that serve it without being on it:**
```python
session.add_diff({"action": "create_tool", "draft": {
    "name": "Level 2 EV charger", "content": {"category": "charging", "kw": 6},
    "located_in": "<shelf-id>", "compatible_with": ["<vehicle-id>"]}})
```

**What has been done to it:**
```python
session.add_diff({"action": "create_service_record", "draft": {
    "name": "Tyre replacement",
    "content": {"performed_at": "2025-08-22T12:00:00Z", "odometer": 46800,
                "performed_by": "Tire Rack installer", "notes": "all four"},
    "service_for": "<vehicle-id>",
    "used": ["<part-id>", "<tool-id>"],       # parts fitted, tools used
    "resolves": ["<issue-id>"],               # issue -> resolved_by record
}})
```

**What is wrong with it:**
```python
session.add_diff({"action": "create_issue", "draft": {
    "name": "Rear brake squeal",
    "content": {"status": "open", "opened_at": "2025-03-01", "severity": "minor"},
    "issue_for": "<vehicle-id>"}})
```

**Photos** — `session.attach_photo(source_path, parent_hint, description)`,
then reference the id in a draft's `photos`. **Anything else** is a
`note` attached with `documented_by`.

Keep the transcript with `session.log("user", ...)` / `session.log("agent", ...)`.
Batch; when the user says "that's it", move on.

### Phase 3 — Review

`post_session_review(session)` and send the user the review (URL or file).
Ask for `confirm`, or changes. Do not commit yet.

### Phase 4 — Edit or Confirm

On `confirm`, apply the diffs in order with `fg_client`, resolving `draft:idx`
references to the ids just created:

| diff | tool calls |
|---|---|
| `create_vehicle` / `create_part` / `create_tool` / `create_purchase` / `create_service_record` / `create_issue` | `create_entity`, then the named edges with `create_relationship` |
| `remove_part` | `end_relationship` on the current `fitted_to`; `create_relationship` `located_in` |
| `resolves` | `update_entity` the issue to `status: resolved`, `resolved_at`; `create_relationship` `resolved_by` |
| photos / receipts | `attach_photo` / `attach_document` on the created entity |

Then write the transcript as a `note` linked `documented_by` to the vehicle,
and **read every created entity back with a fresh `FGClient()`**. Only if all
are present: `session.set_status("committed")`. Otherwise leave the session
open with the errors recorded and tell the user what did not land.

On changes: `session.remove_diff(idx)` / `replace_diff` / `add_diff`, re-render,
wait. On "discard": `session.set_status("discarded")` — archived, never deleted.

### Phase 5 — Handoff

`get_vehicle_history` for each vehicle touched, read back as a short timeline;
`get_open_issues` is the to-do list to leave the user with. One line in the
agent's memory: `2026-09-13: Outback — tyres replaced, 1 issue open. Session abc123…`

## Important constraints

- **Never touch the database directly.** Everything goes through the tools.
- **Never commit without review + confirm.**
- **Never delete.** A part coming off ends its `fitted_to` interval;
  `tombstone_entity` is only for something recorded in error.
- **Dates are ISO-8601 strings in `content`; odometers are a number plus `odometer_unit`.**
- If a tool call fails with "unknown entity_type" or "does not permit", the
  vocabulary is telling you the shape — re-read it, do not work around it.
- **Sessions never expire**; on resume, read the session file first.

## What success looks like

- `vehicle` / `part` / `tool` / `location` / `purchase` / `service_record` /
  `issue` entities with clean names and the key names above
- `fitted_to` intervals that tell the truth about when each part was on
- `get_vehicle_history` reads as the story the user told you
- a `note` with the transcript, linked `documented_by` to the vehicle
- the session archived, and the user told: "Committed: N entities, K photos, 0 errors"
