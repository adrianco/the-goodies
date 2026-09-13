# The vehicles domain

The second domain, and the proof that the engine is domain-blind (ADR-012).
Cars, motorcycles and bicycles; the parts fitted to them; the tools and spares
on the shelf; where each thing is kept; what was bought when; and what has been
done to each machine over its life.

**First pass.** The vocabulary is deliberately small and will be iterated. What
this package establishes is the *shape* of a domain -- a manifest, a seed, a
skill -- and that adding one touches no engine code.

## What a domain is

```
domains/vehicles/
  __init__.py                    exports VEHICLES
  manifest.py                    entity/relationship/source types, merge rules, TOOLS, skills
  tools.py                       the one handler (get_vehicle_history); everything else is a walk
  seed.py                        a small dated collection, same primitives as the house seed
  skills/vehicle-walk/SKILL.md   the guided-walk skill, counterpart of the room walk
  README.md                      this file
```

Nothing under `funkygibbon/`, `inbetweenies/` or `blowing-off/` imports it
(`tests/test_domain_isolation.py`). The engine is told which manifest to serve.

## Running it

**Standalone** -- a vehicles server, its own database file, its own port:

```bash
DATABASE_URL=sqlite+aiosqlite:///./vehicles.db python domains/vehicles/seed.py
DOMAIN_MANIFEST=domains.vehicles.manifest:VEHICLES DATABASE_URL=sqlite+aiosqlite:///./vehicles.db API_PORT=8001 python -m funkygibbon
```

**Alongside the house** -- a second process. The house keeps `funkygibbon.db`
on 8000; vehicles gets `vehicles.db` on 8001. Auth is shared (same
`JWT_SECRET`, same admin), the sync protocol is the same, and each server
advertises only its own domain's tools. A client holds one replica per domain
and syncs each against its own endpoint. This is ADR-012 §3's topology --
*separate endpoint, separate database file, separate MCP client per domain* --
delivered as two processes rather than one process mounting two domains; the
single-process mount is the later iteration and changes nothing a client sees.

A replica (blowing-off) picks its domain the same way:
`DOMAIN_MANIFEST=domains.vehicles.manifest:VEHICLES blowingoff-mcp`.

## Vocabulary

Base vocabulary -- `photo` / `has_photo`, `app` / `manages` -- is inherited and
not restated here.

| Entity type | What it is |
|---|---|
| `vehicle` | A car, motorcycle, bicycle, e-bike, trailer. One type; `content.kind` says which. |
| `part` | A component fitted to a vehicle now or once (tyres, chain, battery). |
| `tool` | Workshop equipment that serves vehicles without being fitted. |
| `location` | A bay, shelf, shed. The domain's own notion of place. |
| `purchase` | What was paid, to whom, when. May cover several items. |
| `service_record` | One dated maintenance event: service, repair, inspection. |
| `issue` | A known problem, `content.status` open or resolved. |
| `invoice` | **Attachment** (a PDF) -- this domain's `manual`. |
| `note` | Free text. |

| Relationship | Endpoints | Notes |
|---|---|---|
| `located_in` | vehicle/part/tool/location → location | Same word as the house, same meaning. |
| `fitted_to` | part → vehicle | **The interval edge.** End it when the part comes off. |
| `replaced` | part → part | The new one took the old one's place. |
| `compatible_with` | part/tool → vehicle | Serves it without being on it. |
| `purchased_via` | vehicle/part/tool → purchase | |
| `service_for` | service_record → vehicle/part | |
| `used` | service_record → tool/part | What a job fitted or used. |
| `issue_for` | issue → vehicle/part | |
| `resolved_by` | issue → service_record | |
| `documented_by` | * → note, purchase/service_record/vehicle → invoice | |
| `manages` | app → vehicle | Base rule, narrowed. |

Source types: `manual`, `imported`, `telemetry`, `generated`.

**Merge rule** (ADR-005 §2 rung 2): a vehicle's `odometer` only goes up, so two
concurrent readings merge to the higher one.

## Tools

The engine's tools, with `create_entity` / `create_relationship` / `search` /
`list_entities` offering *this* vocabulary, plus:

| Tool | Kind | Answers |
|---|---|---|
| `get_vehicles_in_location` | walk | Vehicles kept in a bay/shed. |
| `get_parts_on_vehicle` | walk | Parts fitted now -- or `at` any instant. |
| `get_tools_for_vehicle` | walk | Tools and spares compatible with it. |
| `get_items_in_location` | walk | Parts and tools on a shelf. |
| `get_service_records` | walk | Every job done to it. |
| `get_open_issues` | walk with `where={"status": "open"}` | The to-do list. |
| `get_purchases_for` | walk | What an item was bought in. |
| `get_vehicle_history` | handler | Purchase, services, parts on/off, issues -- one dated timeline. |

Seven of eight are pure declarations in `manifest.py`; the engine runs them.
The house's `get_devices_in_room` is the same mechanism with different
constants, which was the claim ADR-012 made.

## The skill

`skills/vehicle-walk/SKILL.md` is a Claude skill: a guided walk through the
garage that records each vehicle with the tools above, the way the house's
room walk records rooms. Install it by symlinking the directory into a
project's `.claude/skills/` (or a user's `~/.claude/skills/`). The manifest
names it (`VEHICLES.skills`) so a client can find a domain's skills without
knowing the repo layout.

## What is deliberately not here yet

- Cross-domain references (parts stored in a *house* room) -- ADR-012 §4.
- Blob-carrying `invoice` entities in the seed.
- A single process serving both domains -- ADR-012 §3; two processes for now.
- KittenKong (TypeScript) still hard-codes the house tools; it needs to read
  the catalog from its server the way blowing-off reads the manifest.
