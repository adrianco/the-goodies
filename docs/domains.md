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

3. **Mount it.** One engine process serves N domains at `/{domain}/api/v1/...`,
   one database file each (ADR-012 §3). Adding one is config plus manifest — no
   engine code.

4. **Run the conformance suite against it.** `test_protocol_conformance.py`
   asserts the protocol clause by clause and is written to be parameterized by
   manifest: its vocabulary sits in three module constants. The same invariants
   passing for house and vehicles is what proves the engine is domain-blind rather
   than merely arranged to look that way.

5. **Check isolation.** See below.

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

**Cross-domain references** are supported, by value (ADR-012 §4): an interval
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
| Boundary validation wired to the manifest | in progress (Stage D.2) |
| Declarative MCP tools | not started — ADR-012 §2 expects the 5 house-specific tools to collapse into manifest definitions |
| Per-domain mounting and database files | not started — ADR-012 §3 |
| `domains/vehicles` | not started — the proof |

The second domain is **`vehicles`**, not `garage`: `garage` is a room name in
the house domain and in the live graph, so it would collide with an entity name
on the first cross-domain reference.

The five house-specific MCP tools (`get_devices_in_room`, `find_device_controls`,
`get_room_connections`, `get_procedures_for_device`, `get_automations_in_room`)
are still Python, and still the largest remaining piece of house vocabulary
inside the engine. ADR-012 §2 expects most to become declarative — a type filter
plus a relationship walk — at which point `get_devices_in_room` and a future
`get_cars_in_bay` are the same engine query with different constants.
