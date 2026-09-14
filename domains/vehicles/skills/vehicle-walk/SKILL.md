---
name: vehicle-walk
description: Interactive vehicle cataloguing — the user stands by a car, EV, bike, race car or restoration with a phone and talks; photos and the transcript become dated events, parts and locations on the vehicle's permanent record, from pre-purchase evaluation to after-sale. Same review-then-confirm mechanism as /room-walk, with prompt packs per kind of vehicle and per stage of its life. Writes to a FunkyGibbon vehicles server over MCP.
metadata:
  user_invocable: "true"
---

# /vehicle-walk

Catalogue one vehicle at a time through a guided conversation. The record is
a **knowledge history**: what the vehicle is, and everything that happened to
it, on a date, with evidence. Nothing writes to FunkyGibbon until the user
reviews a diff and confirms; after commit every created entity is read back
before the session archives.

This is the house's `/room-walk` mechanism unchanged (ADR-016 §1.1): session
file on disk, diffs accumulated, review, `confirm`, read-back. What differs is
the questions asked, which come from a **kind pack** (car / EV / bike / race
car / restoration) and a **stage pack** (evaluating / owning / selling / after).

## When to use

- "let's do the Roadster" / "walk the Lemons car" / `/vehicle-walk [vehicle]`
- a vehicle you are looking at and might buy (stage: evaluating)
- after a service, a race, a modification, a trip worth remembering
- a vehicle you have sold, or seen again since (stage: after)

For a one-line fact (an odometer reading, a fuel stop) call the tools
directly; a walk is for discovery and for evidence.

## Required helpers

The house's shared scripts work unchanged against a vehicles server; the
client is domain-blind and auth is shared. Copy `domains/house/skills/scripts/`
to `.claude/scripts/` and point it at the vehicles endpoint:

- `fg_client.py` — `FUNKYGIBBON_URL` = the vehicles server (e.g. `http://localhost:8001`),
  `FUNKYGIBBON_TOKEN` = a client token (the house's token works).
- `room_session.py` — session state; use `room_name` = the vehicle's name.
- `render_review.py`, `image_compress.py` — review markdown; photos are always downsampled.

There is no `vehicle_commit.py` yet: apply diffs with `fg_client` calls at
commit (Phase 4) and read every created entity back with a fresh `FGClient()`.

## Before you start

Confirm the server is the **vehicles** domain: `fg.get_statistics()` counts
`vehicle` / `part` / `event`, and `get_vehicle_history` is in the tool list.
If you see `room` and `device`, you are on the house server — stop and say so.

## The vocabulary you write (ADR-016 §2)

Everything you record is one of three things:

| You write | When |
|---|---|
| `vehicle`, `part`, `tool` | a thing — the machine, a component with identity (fitted or on a shelf), workshop kit |
| `location` | a place things are kept for a period — **may be off-site**: a storage yard, the restorer's, a trailer |
| `event` | **something that happened to the vehicle on a date**, with `kind`, `when`, `odometer` or `hours`, `cost`, `where`, `text`, `source` (walk / feed) |

`event.kind` is open. Use these where they fit and invent one when they do
not: `evaluation` · `purchase` · `transfer` · `service` · `repair` ·
`modification` · `inspection` · `fuel` · `charge` · `odometer` ·
`software_update` · `recall` · `condition_report` · `track_day` · `race` ·
`rally` · `show` · `road_trip` · `sale` · `sighting`.

Edges: `happened_to` (event → vehicle), `involved` (event → the parts it
fitted or displaced, the tool it used, the place), `fitted_to` (part →
vehicle, **an interval**: ending it is how a part comes off), `replaced`
(new part → old), `located_in` (interval), `documented_by` (→ `note` or
`document`), `has_photo`.

**The volume rule (ADR-016 §1.2):** record what a person would write in the
car's logbook. Fuel and fast-charge purchases, yes. Every drive, no — a trip
is an event only when it is a *named* one. If the vehicle has an app or an
OVMS box, the feed's facts arrive summarised (one `charge` event per fast
charge; one `odometer` or `condition_report` per month); do not transcribe
telemetry.

## The conversation shape

### Phase 1 — Orient

1. **Resolve the vehicle** with `fg.list_entities("vehicle")` and the aliases
   in `content.aliases`. If absent, ask: new vehicle, or evaluating one?
2. **Check for open sessions** (`RoomSession.find_open_for_room(name)`); offer to resume.
3. **Snapshot** what the graph holds and create the session:
   ```python
   snapshot = {
       "history": fg.call("get_vehicle_history", vehicle_id=vid)["events"],
       "parts":   fg.call("get_parts_on_vehicle", vehicle_id=vid)["parts"],
       "tools":   fg.call("get_tools_for_vehicle", vehicle_id=vid)["items"],
   }
   session = RoomSession.create(room_entity_id=vid, room_name=name, mode="walk", initial_snapshot=snapshot)
   ```
4. **Choose the packs.** Ask (or infer from `content.kind` and `status`):
   kind = car / ev / bike / race_car / restoration; stage = evaluating /
   owning / selling / after. Say which you are using.
5. **Report** what is known: "The **Boxster** has 9 events recorded, last a
   fuel stop on 6 Sep at 91,400; 3 parts fitted. What's new?"

### Phase 2 — Discovery loop

Every answer becomes a diff via `session.add_diff(...)`. The pack only changes
which questions you ask and which `event.kind`s you offer.

**The vehicle itself** (first walk, or details to fill in):
```python
session.add_diff({"action": "create_vehicle", "draft": {
    "name": "2009 Porsche Boxster S",
    "content": {"kind": "car", "make": "Porsche", "model": "Boxster S (987.2)", "year": 2009,
                "identity": {"vin": "WP0CB2…", "registration": "6BOX STR"},
                "aliases": ["the Boxster", "Dad's car"], "status": "owned",
                "odometer": 91400, "odometer_unit": "mi",
                "spec": {"engine": "3.4 DFI flat-six", "gearbox": "6-speed manual", "colour": "Arctic Silver"}},
    "located_in": "<location-id or draft:idx>",
}})
```
One `vehicle` type; `content.kind` says which. `identity` holds whatever
numbers exist — for a race car that may be a logbook number, with the shell's
VIN on the shell *part*. A trailer is a vehicle too.

**An event** — the workhorse:
```python
session.add_diff({"action": "create_event", "draft": {
    "name": "Clutch", "content": {"kind": "service", "when": "2016-03-12", "odometer": 48000,
                                   "cost": 2350, "currency": "USD", "where": "independent, Mountain View",
                                   "text": "Clutch and flywheel; everyone learned to drive stick on the old one.",
                                   "source": "walk"},
    "happened_to": "<vehicle-id>",
    "involved": ["draft:7"],           # the clutch kit part created in diff 7
    "photos": ["<photo_id>"], "documents": ["<photo_id of the invoice>"],
}})
```

**A part fitted / removed / kept:**
```python
session.add_diff({"action": "create_part", "draft": {"name": "OVMS v3 module",
    "content": {"category": "telematics", "version": "v3"}, "fitted_to": "<vehicle-id>",
    "replaces": "<old-part-id>", "photos": ["<photo_id>"]}})
session.add_diff({"action": "remove_part", "part_id": "<old-part-id>",
                  "reason": "replaced by v3", "now_located_in": "<shelf-or-yard-id>"})
```
`remove_part` **ends** the `fitted_to` interval at commit — never deletes —
and adds `located_in` where it went.

**A place** (`create_location`: `kind`, address) and **a tool**
(`create_tool`: `located_in`, `compatible_with`).

**Photos**: `session.attach_photo(path, parent_hint, description)`, then
reference the id in a draft's `photos` (→ `has_photo`) or `documents` (→ a
`document` entity via `attach_document`, for receipts, titles, build sheets,
setup sheets). **Anything else** is a `note`, `documented_by` the vehicle.

Keep the transcript: `session.log("user", …)` / `session.log("agent", …)`.

### Stage packs — what to ask

- **Evaluating** (the vehicle may never be bought — record it anyway, `status: evaluating`):
  what is it, who is selling, asking price; what did the seller say; what did
  *you* see — photograph everything; inspection findings; the decision and
  why. Events: `evaluation`, and `inspection` if there was one. If you walk
  away: `status: not_bought`, and the record stays.
- **Owning** (default): what is on it that wasn't; what has been done since
  the last walk (services, repairs, modifications with the displaced original
  and whether it is reversible); what is wrong; where it and its parts are;
  named trips and events; fuel / charging if the user wants them kept.
- **Selling**: condition now (a `condition_report` with photos), asking and
  sale price, buyer, what went with it (parts, documents, keys), the date.
  Event: `sale`; `status: sold`. Do not tombstone the vehicle.
- **After**: where it is now if known, sightings, later auctions or
  restorations by others. Events: `sighting`.

### Kind packs — what else to ask

- **Car**: factory spec and options; service history (dates, odometer, who);
  the apps and feeds it has and which of their facts to keep.
- **New car / EV**: build sheet and window sticker (documents); warranty and
  battery certificate; software version (`software_update` events from the
  app); charging habits — fast charges as `charge` events, home charging one
  `odometer` event a month with kWh.
- **Bike**: frame and groupset in `spec`; wheelsets and tyres as parts with
  intervals; fit numbers; rides that were events (`rally`, `road_trip`).
- **Race car**: identity is a set of numbers over time — logbook number in
  `identity`, the shell as a part with a VIN; engines and gearboxes as parts;
  setup sheets as documents on `race` / `track_day` events; hours not miles
  (`hours`); the spares pile as parts `located_in` the yard and
  `compatible_with` the car; the trailer as a vehicle with its own location.
- **Restoration**: originality of each part (`content.originality`:
  original / period_correct / reproduction); provenance documents; phases as
  `condition_report` events with many photos; where the displaced originals
  are; who is doing the work and what it cost per phase.

### Country packs — the admin that differs

The collection straddles the US and the UK; the record does not care, but the
questions do. Set `content.country` on the vehicle and on locations, keep
money per event in its own `currency`, and volumes in the unit the receipt
used (`gallons` / `litres`).

- **US**: title (a document) and which state; state registration and plate
  in `identity.registration` + `state`; smog/emissions checks as `inspection`
  events where the state requires them; miles.
- **UK**: the registration mark is the working identity
  (`identity.registration`, `registration_country: UK`); V5C logbook as a
  document; **MOT history is a public feed** (DVLA) — each test is an
  `inspection` event with `test: MOT`, `result`, `advisories`, odometer, from
  `source: feed`; road tax and SORN status as `transfer`-style events
  (`status: SORN`); miles on the odometer, litres at the pump.

### Phase 3 — Review

`post_session_review(session)`; send the review; ask for `confirm` or changes. Do not commit yet.

### Phase 4 — Edit or Confirm

On `confirm`, apply diffs in order with `fg_client`, resolving `draft:idx`
references to the ids just created:

| diff | tool calls |
|---|---|
| `create_vehicle` / `create_part` / `create_tool` / `create_location` | `create_entity`, then `located_in` / `fitted_to` / `replaced` / `compatible_with` with `create_relationship` |
| `create_event` | `create_entity(event)`, then `happened_to`, each `involved`, then photos / documents |
| `remove_part` | `end_relationship` on the current `fitted_to`; `create_relationship` `located_in` |
| `update_vehicle` | `update_entity` (odometer, status, aliases, spec) |

Then write the transcript as a `note` linked `documented_by` to the vehicle,
and **read every created entity back with a fresh `FGClient()`**. Only if all
are present: `session.set_status("committed")`. Otherwise leave the session
open with the errors recorded and say what did not land.

On changes: `session.remove_diff(idx)` / `replace_diff` / `add_diff`,
re-render, wait. On "discard": `session.set_status("discarded")`.

### Phase 5 — Handoff

`get_vehicle_history` for each vehicle touched, read back as a short timeline
("since we last walked it: …"). One line in the agent's memory:
`2026-09-14: Boxster — clutch and top recorded, 2 documents. Session abc123…`

## Important constraints

- **Never touch the database directly.** Everything goes through the tools.
- **Never commit without review + confirm.**
- **Never delete.** A part coming off ends its interval; a sold vehicle gets
  a `sale` event; `tombstone_entity` is only for something recorded in error.
- **Dates are ISO-8601 in `content.when`; odometers are a number plus `odometer_unit` (or `hours`).**
- **Logbook, not data logger.** If you find yourself transcribing a feed,
  stop and summarise it into one event.
- If a tool call fails with "unknown entity_type" or "does not permit", the
  vocabulary is telling you the shape — re-read it, do not work around it.
- **Sessions never expire**; on resume, read the session file first.

## What success looks like

- the vehicle with `identity`, `aliases`, `spec`, `status`, an odometer
- dated `event`s with evidence, oldest first, that read as the story the user told
- `fitted_to` and `located_in` intervals that tell the truth about when
- a `note` with the transcript, `documented_by` the vehicle
- the session archived, and the user told: "Committed: N entities, K photos, 0 errors"
