# The vehicles domain

The second domain, and the proof that the engine is domain-blind (ADR-012).
A **walk-first knowledge history graph** for a collection of cars, bikes and
race cars (ADR-016): every vehicle gets a permanent, append-only record of its
life — from the pre-purchase evaluation to long after the sale — added to by
walking round it with a phone.

**Capture-first, on purpose.** The vocabulary below is deliberately loose;
the entities that deserve their own type are derived from real walks, not
designed first (ADR-016 §4). What is *not* loose is the temporal spine:
`event.when`, `fitted_to`'s interval, `located_in`'s interval.

## What a domain is

```
domains/vehicles/
  __init__.py                    exports VEHICLES
  manifest.py                    entity/relationship/source types, merge rules, TOOLS, skills
  tools.py                       the two timeline handlers (get_events, get_vehicle_history)
  seed.py                        the example lifecycles, same primitives as the house seed
  skills/vehicle-walk/SKILL.md   the walk, with kind / stage / country prompt packs
  README.md                      this file
```

Nothing under `funkygibbon/`, `inbetweenies/` or `blowing-off/` imports it
(`tests/test_domain_isolation.py`). The engine is told which manifest to serve.

## Running it

A vehicles server is its own process, database file and port (ADR-018);
auth is shared with the house server, so one client token works on both:

```bash
DATABASE_URL=sqlite+aiosqlite:///./vehicles.db python domains/vehicles/seed.py
DOMAIN_MANIFEST=domains.vehicles.manifest:VEHICLES DATABASE_URL=sqlite+aiosqlite:///./vehicles.db API_PORT=8001 python -m funkygibbon
```

A replica (blowing-off) picks its domain the same way:
`DOMAIN_MANIFEST=domains.vehicles.manifest:VEHICLES blowingoff-mcp`.

## Vocabulary

Everything a walk captures is a *thing*, a *place*, or *something that
happened to a thing on a date, with evidence*. Base vocabulary — `photo` /
`has_photo`, `app` / `manages` — is inherited and not restated.

| Entity type | What it is |
|---|---|
| `vehicle` | The machine across its whole life. `kind` (car / ev / motorcycle / bicycle / race_car / trailer), `identity` (VIN, frame number, registration mark, a race logbook number — whichever exist), `aliases`, `spec` (free-form factory spec), `status` (evaluating / owned / sold / not_bought), `odometer` + `odometer_unit` (mi / km / hours), `country`. |
| `part` | A component with identity, fitted for a period or on a shelf. A race car's shell and engines are parts. |
| `tool` | Workshop equipment. |
| `location` | Where things are kept, for a period — a garage, a storage yard, a trailer, a lock-up in another country. **May be off-site.** |
| `event` | **Something that happened to a vehicle on a date.** `kind` is open (evaluation, purchase, transfer, service, repair, modification, inspection, fuel, charge, odometer, software_update, recall, condition_report, track_day, race, rally, show, road_trip, sale, sighting …), plus `when`, `odometer` / `hours`, `cost` + `currency`, `where`, `text`, `source` (walk / feed). |
| `document` | **Attachment** (PDF/scan): invoice, build sheet, title, V5C, certificate, setup sheet, period photo. |
| `note` | Transcribed speech, free text. |

| Relationship | Endpoints | Notes |
|---|---|---|
| `located_in` | vehicle/part/tool/location → location | **Interval.** |
| `fitted_to` | part → vehicle | **The interval edge.** End it when the part comes off. |
| `replaced` | part → part | The new one took the old one's place. |
| `compatible_with` | part/tool → vehicle | Spares and tools that serve it. |
| `happened_to` | event → vehicle / part | |
| `involved` | event → part / tool / location | What a service fitted, what a modification displaced, the tool a repair used. |
| `documented_by` | * → note / document | |
| `manages` | app → vehicle | Base rule, narrowed. An app's writes are `source: feed` events. |

**US and UK**: `country` on vehicles and locations, `identity.registration_country`
(+ `state` in the US), `currency` per event, volumes in the receipt's unit
(`gallons` / `litres`). The admin that differs — title / smog versus V5C /
MOT / tax / SORN — is in the walk's country pack, not the vocabulary.

**Merge rule** (ADR-005 §2 rung 2): a vehicle's `odometer` only goes up.

**The volume rule** (ADR-016 §1.2): this is a logbook, not a data logger.
Fuel and fast-charge purchases are events; trips are not unless they are
named events; app and OVMS feeds are summarised into logbook-grade facts
before they are written.

## Tools

The engine's 18, with `create_entity` / `create_relationship` / `search` /
`list_entities` offering *this* vocabulary, plus:

| Tool | Kind | Answers |
|---|---|---|
| `get_vehicles_in_location` | walk | Vehicles kept in a place — or `at` any instant. |
| `get_parts_on_vehicle` | walk | Parts fitted now — or `at` any instant. |
| `get_tools_for_vehicle` | walk | Tools and spares compatible with it. |
| `get_items_in_location` | walk | Parts and tools on a shelf / in a yard. |
| `get_events` | handler | Events oldest first, filtered by `kind`, `since`, `until` on the event's own date. |
| `get_vehicle_history` | handler | The whole life: every event, every part on/off, every move — one dated timeline. |

`get_modifications`, `get_current_spec`, `get_service_due` arrive when their
event kinds are promoted (ADR-016 §4).

## The examples in the seed

| Vehicle | What it stresses |
|---|---|
| 2026 Mini Cooper SE | A new EV with an app feed: only logbook-grade facts arrive. |
| 2010 Tesla Roadster Sport + OVMS | Third-party telemetry summarised into monthly battery condition reports; the OVMS module is a part with a v2 → v3 history. |
| E30 Lemons car #4471-L | Off-site with its trailer and spares; no single VIN — shell and engines are parts with intervals; hours not miles. |
| 2009 Porsche Boxster S | A gas car in the family since new: seventeen years of history and a transfer inside the family. |
| 1998 Lotus Elise S1 *(illustrative)* | UK-registered: registration mark as identity, MOT history as a feed, GBP, litres, SORN. |

`docs/vehicles-proposal.md` works them through in plain language, for friends
with collections.

## The skill

`skills/vehicle-walk/SKILL.md`: the room walk's mechanism unchanged (session
file → diffs → review → `confirm` → read-back), with prompt packs per kind
(car / EV / bike / race car / restoration), per lifecycle stage (evaluating /
owning / selling / after) and per country (US / UK). It reuses the house's
`fg_client.py` unchanged. Not yet used on a real garage — that is the next step.

## What is deliberately not here yet

- Typed `modification` / `service` / `sale` entities and their tools — after the walks (ADR-016 §4).
- Cross-domain references (a location that *is* a house room) — ADR-017.
- A `vehicle_commit.py`; the walk applies its diffs with `fg_client` directly.
- KittenKong (TypeScript) still hard-codes the house tools — ADR-018 §3.
