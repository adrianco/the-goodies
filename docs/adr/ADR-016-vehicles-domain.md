# ADR-016: The vehicles domain

**Status:** Proposed · 2026-09-14 · A first pass shipped 2026-09-13 in `1225b32`
(v0.8.0): manifest, seed, eight tools, `vehicle-walk`, `tests/test_vehicles_domain.py`.
**The vocabulary (§1) is under owner review against the real use cases** and
will be revised before this ADR is accepted; the *shape* of a domain (§2) is
the durable part and is not in question.

## Context

ADR-012 abstracted the engine from the house and named vehicles as the
second domain: a car collection — what vehicles exist, each one's history,
issues and service records — chosen because "history of the cars" is exactly
the temporal model (ADR-004) read as a story. The owner's sequencing was
abstract → prove on house → instantiate vehicles. This ADR records the
instantiation: what the vehicles domain says, why it says it that way, and
what proving the abstraction cost the engine.

What building it exposed (recorded because it is why v0.8.0 exists):
the abstraction was *declared* but not *real* at v0.7.0. Every write path still
coerced through the legacy house enums (`EntityType("vehicle")` raised), the
five house tools were methods on the engine's `MCPTools`, the tool catalog
hard-coded house `enum`s, and `domains/` was not even packaged. None of that
was visible while the only domain was the house. The second domain is the
test that a domain abstraction is real; this one failed it until the engine
was fixed.

## Decision

### 1. Vocabulary

One `vehicle` type, not `car` / `bicycle` / `motorcycle`. `content.kind` says
which. Everything the domain asks — parts, tools, purchase, service, issues,
location — applies to all of them alike, and a walk skill that must choose
between five types before it can record anything is a worse walk. The cost is
that a rule cannot say "only cars have registrations"; that is a content
convention, not a vocabulary one, and acceptable at this scale.

| Type | Role |
|---|---|
| `vehicle` | The machine. `kind`, `make`, `model`, `year`, `registration`, `odometer` + `odometer_unit`. |
| `part` | A component fitted now or once. Tyres, chain, battery, pads. |
| `tool` | Workshop equipment that serves vehicles without being fitted. |
| `location` | Bay, shelf, shed — the domain's own notion of place (not a house room; see ADR-017). |
| `purchase` | What was paid, to whom, when. One purchase may cover several items, so it is an entity, not a field. |
| `service_record` | One dated maintenance event with odometer and notes. |
| `issue` | A known problem; `content.status` open / resolved, `opened_at` / `resolved_at`. |
| `invoice` | **Attachment** (PDF) — this domain's counterpart of the house's `manual`. |
| `note` | Free text. |

`photo` / `has_photo` and `app` / `manages` are inherited from the base and
not restated (ADR-013 §3/§4).

**`fitted_to` is the interval edge of this domain.** A part on a vehicle is
`part -fitted_to-> vehicle` with `valid_from`; taking it off *ends* that
interval; its replacement opens a new one the same instant, and `replaced`
(new → old) records the succession. `get_parts_on_vehicle(at=…)` is therefore
the same query as "what is on it now" — no history table, no status field,
the ADR-004 model doing what it was built for. The seed's tyre swap is the
worked example and the e2e test pins it: Michelins before 2025-08-22,
Continentals after, nothing before 2023-09-10.

Other edges: `located_in` (same word and meaning as the house), `compatible_with`
(serves without being fitted), `purchased_via`, `service_for`, `used`
(a job fitted a part or used a tool), `issue_for`, `resolved_by`,
`documented_by` (notes; invoices onto purchases / services / vehicles), and
`manages` narrowed to `app → vehicle`.

Source types: `manual`, `imported`, `telemetry` (the vehicle or its app said
so — the one source the house does not have), `generated`.

### 2. What a domain package is (the durable part)

```
domains/vehicles/
  manifest.py        vocabulary · merge rules · TOOLS · skills   (the contract)
  tools.py           handlers, for the tools that are more than a walk
  seed.py            a dated fixture on the same primitives as the house seed
  skills/<name>/SKILL.md
  README.md
```

plus one line in the root `pyproject.toml` package list. The engine is not
touched; `tests/test_domain_isolation.py` fails if it is.

**Tools are declared, not coded.** Seven of the eight vehicles tools are
`DomainTool(anchor, walk=(Walk(relationship, direction, target_types, where),), result_key)`;
the engine renders the schema into the catalog and runs the walk against any
store — server, replica, test double — `at`-aware. `get_parts_on_vehicle` and
the house's `get_devices_in_room` are the same engine code with different
constants, which is what ADR-012 §2 predicted. `get_vehicle_history` is the
one handler: several walks stitched into one dated timeline is logic.

**Merge rule** (ADR-005 §2 rung 2): a vehicle's `odometer` only goes up; two
concurrent readings merge to the higher. That is the whole list for now — the
domain does not yet know enough about its own concurrent-edit patterns to
declare more, and a rule that is wrong is worse than the generic merge.

**Skill:** `vehicle-walk` has the room walk's shape (session file → diffs →
review → `confirm` → read-back before archive) and reuses the house's
`fg_client.py` unchanged, because the client is domain-blind and auth is
shared. It has not been used on a real garage yet.

### 3. What proving it changed in the engine

Recorded so the next domain knows what to expect: nothing.

The v0.8.0 engine changes — manifest-driven vocabulary on every write path
including sync, `catalog_for(manifest)`, `DomainTool` / `Walk` and their
executor, the five house tools leaving `MCPTools`, `domains/` packaged — were
all fixes to ADR-012's abstraction, not accommodations of vehicles. The third
domain should need a manifest and nothing else; if it needs an engine line,
that line is a bug in the abstraction and gets an issue, as these did (#90,
#91 were both the same class: a house rule table the manifest had not
replaced).

## Consequences

- Vehicles runs today as its own server process and database file, alongside
  the house, on a shared token (ADR-018). Both servers advertise only their
  own catalog; house vocabulary at the vehicles endpoint is a 400.
- The vocabulary is a first pass and *will* change. Because it is data, a
  change is a manifest edit plus, if a type is renamed, a data migration of
  the same kind ADR-013 did for the house — not a schema change. Candidates
  already visible: VIN / frame number as the identity field rather than
  `registration`; whether consumables (oil, brake fluid) are parts or service
  content; whether `location` should be able to *be* a house room by reference
  (ADR-017) rather than a parallel notion.
- The seed carries no `invoice` blobs and the skill has no `vehicle_commit.py`
  yet; both are gaps to fill on first real use.
- Cross-domain references — the parts box kept in the house's garage — are the
  next thing the vehicles domain actually needs and are ADR-017.

## Alternatives considered

- **Per-kind entity types (`car`, `bicycle`, …)** — rejected above: every
  tool and edge rule would be declared N times for the same idea.
- **Service history as an inline list on the vehicle** — rejected: a service
  fits parts and uses tools, so it has edges of its own; and the house learned
  (ADR-013 §3, ordered `images[]` aside) that an inline list is where things
  go to be invisible to traversal.
- **Parts as content on the vehicle (`content.tyres = …`)** — rejected: the
  point of the domain is that a part's life across vehicles is history, and
  history lives on interval edges, not in a field that gets overwritten.
- **A separate `garage` domain for tools and locations** — rejected before
  writing (ADR-012's renaming note): `garage` is a house room name, and the
  tools serve the vehicles; splitting them puts the domain's most common
  question (`get_tools_for_vehicle`) across a boundary.
