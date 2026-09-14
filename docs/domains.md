# Domains

How the engine stays ignorant of what it is storing, and what you write to teach
it a new subject.

Implements [ADR-012](adr/ADR-012-domain-abstraction.md). The worked example is
[`domains/house`](../domains/house/README.md), which also annotates which parts
of that vocabulary are actually used.

---

## 1. The split

**The engine owns mechanism.** Versioning, the temporal model, sync and conflict
resolution, per-id acknowledgement, auth, blobs, the graph index, traversal,
search, backup. None of it mentions a house, and none of it should mention a
car.

**A domain owns vocabulary.** Which entity types exist, which relationships may
connect which of them, where data can come from. That is all — a domain is data
the engine consumes, not code that extends it.

The abstraction was overdue but shallow: the engine was *already* domain-blind
everywhere that mattered. House knowledge lived in exactly two places:

- `entity_type`, `relationship_type` and `source_type` as `SQLEnum` **database
  columns**, so a new domain meant a schema migration;
- `EntityRelationship.is_valid_for_entities`, a dict literal inside a method on
  a shared model, asserting that a DEVICE may be LOCATED_IN a ROOM.

Both are now a manifest. Adding a domain is a new manifest, not an `ALTER TABLE`.

## 2. The manifest

Defined in [`inbetweenies/domain.py`](../inbetweenies/domain.py).

```python
HOUSE = build_manifest(
    name="house",
    entity_types=["home", "room", "device", ...],
    source_types=["homekit", "matter", "manual", ...],
    relationship_rules=[
        RelationshipRule(
            name="located_in",
            allowed_endpoints=(("device", "room"), ("room", "home"), ...),
        ),
        ...
    ],
    attachment_types=("manual",),   # extends the base attachment set
)
```

The engine calls `check_entity_type`, `check_source_type` and
`check_relationship` at the API and sync boundary. Storage keeps whatever the
domain declared; nothing else decides what is sayable.

### The base vocabulary every domain inherits

A domain declares what is specific to it. Two concepts are engine mechanism and
come free — declaring them per-domain would force every new domain to restate
them, and leave the engine unable to reason about them generically.

| Base | What it is | Why not domain |
|---|---|---|
| `photo` entity type, `has_photo` | An attachment carrying a blob | The blobs table, blob sync and `BlobType` are already engine. A vehicle collection, a boat and a server rack all have photos. |
| `app` entity type, `manages` | An external system that runs or controls things | Alexa, Home Assistant, a vendor scheduler. Any domain has systems acting on its entities. |

**The blob rule, engine-wide:** an entity that carries a blob is an *attachment
entity*, and top-level `content.blob_id` is the only link to the blobs table.
The entity type says what kind of document it is, so no boolean "this has a
blob" flag is needed — the type is the flag. No relationship ever points at a
blob; relationships only name the attachment's role. See
[ADR-013 §3](adr/ADR-013-house-vocabulary-cleanup.md).

A domain **extends** the attachment set with `attachment_types=(...)` — the
house adds `manual` for an appliance PDF, a vehicles domain might add `service_record`.
Anything listed there is automatically an entity type too, and
`manifest.carries_blob(entity_type)` is the single question the engine asks.

**One attachment is an entity; an ordered sequence stays inline.** Relationships
are an unordered set, so a sequence split into entities has nowhere to put its
order except a `step` integer in edge properties that every reader must know to
sort by. Keep ordered runs as `content.images[]` on the owning entity, each
element carrying its own `blob_id`. The test: if removing an item would change
what the remaining items mean, it is a sequence.

A domain **narrows** a base relationship rule by redeclaring it under the same
name. The house narrows `manages` from `app → *` to four specific pairs. Do not
widen one — that makes the base rule decorative.

### Wildcards in base rules

The base cannot enumerate a domain's entity types, so base rules use `"*"` in
one endpoint position: `("*", "photo")` means anything may have a photo;
`("app", "*")` means an app manages something. A wildcard pair is a pair like
any other and does not affect the three states below.

### Why not arbitrary strings

Maximum flexibility, and a graph that fragments in silence: `"DEVICE"`,
`"device"` and `"Device"` become three types that nothing joins. The damage
shows up much later, as query results that are quietly incomplete. A manifest
keeps writes honest while staying data rather than schema.

### `allowed_endpoints` has three states

| Value | Meaning |
|---|---|
| `(("device", "room"),)` | Only those pairs. |
| `None` | Explicitly unconstrained — any pair. |
| `()` | Nothing is permitted. |
| `(("*", "photo"),)` | Wildcard — any *from* type, but only `photo` as *to*. |

`None` and `()` must not be conflated. The empty tuple looks like an oversight and
sometimes is one — house declares `contained_in` and `depends_on` with no pairs,
so neither can be created at all — but reading it as "unconstrained" would
silently make unusable types usable. That is a behaviour change smuggled in by
an abstraction whose entire premise is that behaviour does not change.

### Endpoints are checked only when both are known

An edge may legitimately reference an entity that has not synced yet.
`check_relationship` skips the endpoint check when either type is `None` rather
than rejecting the write: refusing data because of arrival order is not a
property of the data.

## 2a. Tools and skills

A domain's MCP tools are **declared, not coded** (ADR-012 §2). The manifest
carries a tuple of `DomainTool`s; the engine renders each into the catalog and
dispatches calls to it, on the server and on a replica alike, from
`inbetweenies/mcp/domain_tools.py`.

```python
DomainTool(
    name="get_parts_on_vehicle",
    description="Parts currently fitted to a vehicle; with `at`, the parts fitted then.",
    anchor="vehicle_id", anchor_types=("vehicle",),
    walk=(Walk("fitted_to", "incoming", ("part",)),),
    result_key="parts",
)
```

A **walk** starts at the anchor entity (whose type is checked), follows the
named relationship in the named direction, keeps results of the named types,
optionally filters on `content` (`where={"status": "open"}`), and may chain
several hops. Every walk takes `at`. The result is
`{anchor: id, "anchor": {...}, result_key: [entities], "count", "as_of"}`.
`get_devices_in_room` and `get_parts_on_vehicle` are the same engine code with
different constants.

A tool that genuinely needs logic supplies `handler=` instead — an
`async (ops, **arguments)` in the domain package. The house's
`find_device_controls` and the vehicles' `get_vehicle_history` are handlers.
Either way the engine's 18 tools cannot be redeclared, and `catalog_for(manifest)`
is what every transport serves.

**Skills** are guided workflows over the tools — the house's `room-walk`,
`room-edit`, `app-walk` and `align-rooms`, the vehicles' `vehicle-walk`. A
domain ships them as `SKILL.md` files under `domains/<name>/skills/` (shared
scripts in `skills/scripts/`) and names them in the manifest (`skills={...}`)
so a client can find them without knowing the repo layout. The house's
`fg_client.py` is domain-blind and drives a vehicles server unchanged.

## 3. Adding a domain

1. **Create the package.**

   ```
   domains/vehicles/
     __init__.py      # exports the manifest
     manifest.py      # the vocabulary
     README.md        # annotate what is used vs declared
   ```

2. **Declare the vocabulary** — and only the parts that are yours. `photo`,
   `has_photo`, `app` and `manages` come from the base; a domain that restates
   them is describing engine mechanism as its own knowledge. Add attachment
   types you genuinely own with `attachment_types=(...)`, and narrow a base rule
   only if the domain really is more restrictive.

   `house` was originally *derived* from the enums it replaced, so ADR-012's
   move could be proved byte-identical across all 2016 endpoint triples. That is
   finished: ADR-013 changed what the vocabulary says, so house is now declared
   like any other domain and the enums are legacy.

3. **Declare its tools and skills** (see [§2a](#2a-tools-and-skills)). A
   walk is data; a handler is a function in `domains/<name>/tools.py` that
   takes the `ops` it runs against.

4. **Run it.** A domain is served by its own process with its own database
   file and port, told which manifest to load:

   ```bash
   DATABASE_URL=sqlite+aiosqlite:///./vehicles.db python domains/vehicles/seed.py
   DOMAIN_MANIFEST=domains.vehicles.manifest:VEHICLES DATABASE_URL=sqlite+aiosqlite:///./vehicles.db API_PORT=8001 python -m funkygibbon
   ```

   That is ADR-012 §3's topology — separate endpoint, separate database,
   separate MCP client per domain, shared auth and protocol — as two processes.
   One process mounting N domains is the later iteration; nothing a client
   sees changes when it lands. Adding a domain is a manifest plus a line in
   `pyproject.toml`'s `packages` so it is installed with the engine — no engine
   code.

5. **Run the conformance suite against it.** `test_protocol_conformance.py`
   asserts the protocol clause by clause and is written to be parameterized by
   manifest: its vocabulary sits in three module constants. The same invariants
   passing for house and vehicles is what proves the engine is domain-blind rather
   than merely arranged to look that way.

6. **Check isolation.** See below.

## 4. No domain leakage

**No module under `funkygibbon/`, `inbetweenies/` or `blowing-off/` may import
`domains.*`.** Enforced by `tests/test_domain_isolation.py`, not left to review.

This is the property a second domain exists to prove. If `domains/vehicles` can be
added without touching the engine, the abstraction is real. If the engine needs
one line, it is not — and the test says so at the moment the line is added,
rather than three domains later when it is expensive.

Direction matters: a domain may import the engine. That is the dependency the
design intends.

## 5. What is deliberately out of scope

**Cross-domain queries.** Domains are isolated databases with their own sync
timelines and digests. A query never spans them.

**Cross-domain references** are designed, not built — [ADR-017](adr/ADR-017-cross-domain-references.md) (promoted from ADR-012 §4, with temporal semantics and the four broken-reference states): an interval
edge living entirely in the referring domain, whose remote endpoint is a
qualified `(domain, entity_id)` plus a cached label. The vehicles domain's "parts box stored
in house room X" is a *vehicles* row — it syncs on vehicles' timeline and counts in
vehicles' digest. Dereference is best-effort; a dangling reference is reported,
never cascaded.

**Shared auth.** One JWT secret, one admin system, tokens valid across domains
on the instance. The owner premise is one operator.

**Houses with wheels.** A motorhome is a house *and* a vehicle: it has rooms and
devices, and it also has mileage, service records and a registration. The domain
model has no answer for one entity living in two domains — references are by
value and point *between* domains, never merge them. Deliberately out of scope
for now. Whichever domain such a thing lands in first, the other view of it will
be a reference, not a second home for the same entity.

## 6. Status

| | |
|---|---|
| Manifest contract | done — `inbetweenies/domain.py` |
| Base vocabulary (attachments, apps) | done — `inbetweenies/domain.py`, ADR-013 §3/§4 |
| `domains/house` | done, declared (was derived; ADR-013 changed what it says) |
| Isolation test | done |
| Boundary validation wired to the manifest | done — tool calls and sync pushes; the legacy enums are no longer consulted on any write path |
| Declarative MCP tools | done — `DomainTool` / `Walk`; the house's `get_devices_in_room` is a walk, its other four are handlers in `domains/house/tools.py`; nothing house-specific remains in the engine |
| Skills named by the manifest | done — `manifest.skills`; house ships four (`domains/house/skills/`, from Corfe's #92), vehicles one |
| Per-domain database files and endpoints | done as **one process per domain** (`DOMAIN_MANIFEST`, `DATABASE_URL`, `API_PORT`) — ADR-018; one process mounting N domains is deferred |
| `domains/vehicles` | **first pass done** — manifest, seed, 8 tools, `vehicle-walk` skill, tests (`tests/test_vehicles_domain.py`) |
| Cross-domain references (§4) | proposed — ADR-017 |
| KittenKong reads its domain from the catalog | not started — the TypeScript client still hard-codes the house tools |

The second domain is **`vehicles`**, not `garage`: `garage` is a room name in
the house domain and in the live graph, so it would collide with an entity name
on the first cross-domain reference.

The five house tools left the engine: `get_devices_in_room` is a declared walk
and the other four are handlers in `domains/house/tools.py`. The vehicles
domain's `get_parts_on_vehicle` is the same walk with different constants,
which is what §2 predicted.
