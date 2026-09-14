# ADR-016: The vehicles domain — a walk-first knowledge history graph

**Status:** Accepted in principle · 2026-09-14 · Owner decisions of 2026-09-14
recorded in §1; the vocabulary in §2 is a deliberately loose *capture*
vocabulary and will be revised from real walks (§4) before this ADR is marked
Implemented. A first pass with a tighter, guessed vocabulary shipped
2026-09-13 in `1225b32` (v0.8.0) and is superseded by this text.

## Context

ADR-012 named vehicles as the second domain and the proof that the engine is
domain-blind. The first pass proved that (and fixed the engine where it was
not — every write path still coerced through house enums, the house tools
were engine methods, `domains/` was not packaged; all fixed in v0.8.0, none of
it vehicles-specific). What it got wrong was the *subject*: it modelled a
garage of daily drivers with a parts shelf, from imagination.

The owner's description of the actual use (2026-09-14):

- The collection is cars, bikes and race cars, some new, some collector
  restorations. Storage may not be at the house.
- Each vehicle needs nicknames, a detailed specification, and its
  modifications from stock.
- **The room-walk mechanism is the main data entry method**: stand by the
  vehicle with a phone, take pictures, talk; the transcript becomes notes;
  nothing is written until reviewed and confirmed.
- **Full history**: the pre-purchase evaluation (including vehicles looked at
  and not bought), ownership, sale, and the historical record *after* sale.
- Newer cars have apps and possible data feeds.
- **FunkyGibbon is the knowledge history graph, not the logging backend for
  high-volume data.** Fuel and fast-charge purchase history is useful; trip
  records belong elsewhere unless a trip is a special event.
- The details are not known yet. The right way to find the entities and
  relationships is to do a few example walks of each kind and then work them
  out — not to design them first.

## Decision

### 1. Principles (the durable part)

1. **Walk-first.** The vehicle walk — the room walk's mechanism unchanged:
   session file on disk, diffs accumulated, review, `confirm`, every created
   entity read back before the session archives — is the primary way data
   enters. Photos and transcribed notes are first-class outputs of a walk,
   not afterthoughts. Import scripts and feeds are secondary and must produce
   the same shapes a walk would.
2. **A knowledge history graph, with a volume boundary.** The graph holds
   *facts about the vehicle's life*: what it is, what happened to it, when,
   where, at what cost, with what evidence. It does not hold telemetry. The
   test for a feed record is *would a person write this in the car's
   logbook?* — an odometer reading on a service date yes; every drive no. A
   fuel or charging purchase is a logbook entry (money, place, odometer, a
   few hundred a year); a trip is not unless it is a named event (a rally, a
   track day, the drive home from the seller). App integrations summarise
   before they write.
3. **Full lifecycle, append-only.** A vehicle's record starts before purchase
   (an evaluation: viewing, inspection, the decision — including *not*
   buying, which leaves an entity with an evaluation and no purchase) and
   continues after sale (where it went, later sightings, a later auction).
   Nothing is deleted; a sold vehicle is a vehicle with a `sale` event, not a
   tombstone.
4. **Derive the vocabulary from examples.** Ship a loose capture vocabulary
   (§2), do real walks of each kind (§4), then promote what recurs with
   structure into proper entities and relationships — the way ADR-013 cleaned
   up the house from live data rather than from its seed. Until then, resist
   modelling.
5. **One walk skill, many prompt packs.** Cars, bikes, race cars and
   restorations differ in the *questions asked*, not in the mechanism. One
   `vehicle-walk` with per-kind and per-lifecycle-stage prompt packs (§3), so
   the mechanism cannot drift across four skills.

### 2. Capture vocabulary (loose on purpose)

Everything a walk captures is one of: *a thing*, *a place*, *something that
happened to a thing on a date, with evidence*. So:

| Type | Role | Notes |
|---|---|---|
| `vehicle` | The machine, across its whole life | `content.kind` (car / bike / motorcycle / race_car / ev / trailer …), `aliases`, `identity` (VIN, frame number, registration — whichever exist), `spec` (free-form factory/as-delivered specification: engine, drivetrain, paint code, trim, options), `status` (evaluating / owned / sold / …) |
| `part` | A component with identity, fitted now or once, or on a shelf | Kept as an asset because restorations and modifications care about the displaced original |
| `tool` | Workshop equipment | |
| `location` | Where things are kept — **may be off-site** | `kind` (home garage / storage unit / shop / trailer / in transit), address. A house room is an *optional* ADR-017 reference, never required |
| **`event`** | **Something that happened to a vehicle on a date** | `kind` open: `evaluation`, `purchase`, `service`, `repair`, `modification`, `inspection`, `fuel`, `charge`, `track_day`, `rally`, `show`, `sale`, `sighting`, `recall`, `software_update`, `condition_report` …; `when`, `odometer`, `cost`, `currency`, `where` (text or a location id), free text |
| `note` | Transcribed speech, free text | The walk's transcript is a note on the vehicle |
| `photo` | base attachment | |
| `document` | This domain's attachment type (PDF/scan) | `kind`: invoice, build sheet, title, certificate, period photo, setup sheet … |

Relationships, minimal: `located_in` (interval; vehicles, parts, tools →
location), `fitted_to` (**interval**, part → vehicle — proven in the first
pass and kept), `replaced` (part → part), `happened_to` (event → vehicle),
`involved` (event → part / tool: what a service fitted, what a modification
displaced), `documented_by` (anything → note / document), base `has_photo`,
base `manages` narrowed to app → vehicle.

**Why one `event` type with an open `kind`.** The alternative is deciding now
that `service_record`, `modification`, `purchase`, `evaluation`, `sale` are
each entities with their own shape — five guesses about structure the walks
have not yet revealed. An event with a `kind` records all of them today with
no loss (the free text and the evidence are what a walk produces anyway), and
the promotion later is mechanical: a new type in the manifest and a migration
that re-types the rows of that kind, exactly as ADR-013 re-typed notes into
photos. What is *not* loose is the temporal spine: `event.when`,
`fitted_to`'s interval and `located_in`'s interval are what make "what was on
the car in March" and "where was it during the restoration" answerable, and
they are set from day one.

**Merge rules**: `vehicle.odometer` takes the higher reading (an odometer
only goes up). Nothing else until the walks show a concurrent-edit pattern.

**Tools**: the engine's 18, plus a small declared set that does not presume
structure — `get_vehicle_history` (every event, oldest first, `at`-aware),
`get_events(vehicle, kind, since, until)`, `get_parts_on_vehicle(at)`,
`get_items_in_location`, `get_vehicles_in_location`, `get_tools_for_vehicle`.
Anything more specific (`get_modifications`, `get_current_spec`,
`get_service_due`) is added when its kind is promoted.

### 3. The walk

`domains/vehicles/skills/vehicle-walk/SKILL.md`: the room walk's phases
(orient → discovery loop → review → confirm → handoff) with:

- **Lifecycle-stage packs** — *evaluating* (what is it, what did the seller
  say, what did the inspection find, photos of everything, decision);
  *owning* (the default: what is on it, what has been done, what is wrong,
  what is where); *selling* (condition, price, buyer, what went with it);
  *after* (where is it now, sightings).
- **Kind packs** — *car* (spec, options, apps and feeds, service);
  *new car / EV* (build sheet, warranty, software, charging);
  *bike* (frame, groupset, wheelsets, fit, rides that were events);
  *race car* (setup sheets, tyre sets, event log, scrutineering, damage);
  *restoration* (originality, provenance, phases, condition reports,
  displaced originals).
- Every answer becomes a `vehicle`, `part`, `location` or an `event` of some
  `kind` with photos and a note; the pack only changes which questions are
  asked and which kinds are offered.

### 4. Deriving the real vocabulary

Do at least two real walks per kind (car, bike, race car, restoration — one
of them an evaluation of a vehicle not bought, one a vehicle already sold).
The first three are named: a brand-new Mini Cooper SE (app feed), the 2010
Tesla Roadster with its OVMS connection (third-party telemetry → monthly
battery condition reports), and the E30-based Lemons race car stored off-site
with its trailer and spares and no single VIN (identity as a set of numbers
over time; hours not miles). `docs/vehicles-proposal.md` works each through.
Then,
then read the graph, not the design: which `event.kind`s recur, which carry
structure beyond text (a service always has odometer and parts; a
modification always has a displaced original and reversibility; a track day
has a venue and a setup), which questions people actually ask of it. Promote
those into typed entities, rules and tools; leave the rest as events. Rewrite
§2 with what was found, mark this ADR Implemented, and record the migration
the way ADR-013 did.

Friends with collections are asked for input on the proposal at this stage
(`docs/vehicles-proposal.md`), specifically on the questions a walk should
ask and the questions they would want the graph to answer.

### 5. Feeds and apps

An app integration is an `app` entity that `manages` the vehicle, writing
events of the kinds above at the *logbook* granularity — an odometer on a
date, a fault, a recall, a software update, a fast-charge purchase — with
`source_type: telemetry`. Raw feeds (GPS traces, per-second telemetry, every
charging session's curve) live in whatever system collects them; the graph
may hold a `document` pointing at a summary. Deciding which feeds to
integrate is deferred until a walk has recorded a vehicle that has one.

## Consequences

- The manifest gets *smaller* than the first pass (`event` replaces
  `purchase`, `service_record`, `issue`; `document` replaces `invoice`), and
  the seed becomes three worked lifecycles rather than a parts inventory.
  Existing tests are rewritten to the capture vocabulary.
- The domain is usable for real walks now, before its final shape is known,
  and the cost of being wrong is a manifest edit plus a re-typing migration —
  not a schema change and not lost data.
- Storage off-site means the vehicles domain's `location` is primary and the
  house reference (ADR-017) is optional; the two domains stay separate back
  ends (ADR-018).
- The volume boundary (§1.2) is a rule, not a mechanism: nothing stops a feed
  writing a thousand events a day. If a feed appears, its integration is
  where the summarising happens, and `get_statistics` per `event.kind` is
  how drift would show.

## Alternatives considered

- **Typed entities for service / modification / purchase from day one**
  (the first pass) — rejected: five guesses at structure before any walk;
  ADR-013 showed the house vocabulary designed from a seed was half unused
  and shaped differently from the real data.
- **Trips and telemetry as events** — rejected by the owner: this is a
  knowledge history graph; a logbook, not a data logger.
- **Per-kind entity types (`car`, `bike`, `race_car`)** — rejected: the
  lifecycle, the walk and the temporal questions are identical across kinds;
  the differences are prompt packs.
- **A separate skill per kind** — rejected: four copies of one mechanism
  drift; one skill with packs cannot.
- **Waiting to build anything until the vocabulary is known** — rejected:
  the vocabulary cannot be known without walks, and walks need a working
  domain to write into.
