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
)
```

The engine calls `check_entity_type`, `check_source_type` and
`check_relationship` at the API and sync boundary. Storage keeps whatever the
domain declared; nothing else decides what is sayable.

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

The last two must not be conflated. The empty tuple looks like an oversight and
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
   domains/garage/
     __init__.py      # exports the manifest
     manifest.py      # the vocabulary
     README.md        # annotate what is used vs declared
   ```

2. **Declare the vocabulary.** A new domain writes its types out directly. Only
   `house` derives them, because it is a migration of definitions that already
   existed and "byte-identical" had to be true by construction rather than by
   careful retyping.

3. **Mount it.** One engine process serves N domains at `/{domain}/api/v1/...`,
   one database file each (ADR-012 §3). Adding one is config plus manifest — no
   engine code.

4. **Run the conformance suite against it.** `test_protocol_conformance.py`
   asserts the protocol clause by clause and is written to be parameterized by
   manifest: its vocabulary sits in three module constants. The same invariants
   passing for house and garage is what proves the engine is domain-blind rather
   than merely arranged to look that way.

5. **Check isolation.** See below.

## 4. No domain leakage

**No module under `funkygibbon/`, `inbetweenies/` or `blowing-off/` may import
`domains.*`.** Enforced by `tests/test_domain_isolation.py`, not left to review.

This is the property a second domain exists to prove. If `domains/garage` can be
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
qualified `(domain, entity_id)` plus a cached label. Garage's "parts box stored
in house room X" is a *garage* row — it syncs on garage's timeline and counts in
garage's digest. Dereference is best-effort; a dangling reference is reported,
never cascaded.

**Shared auth.** One JWT secret, one admin system, tokens valid across domains
on the instance. The owner premise is one operator.

## 6. Status

| | |
|---|---|
| Manifest contract | done — `inbetweenies/domain.py` |
| `domains/house` | done, derived from the definitions it replaces |
| Isolation test | done |
| Boundary validation wired to the manifest | in progress (Stage D.2) |
| Declarative MCP tools | not started — ADR-012 §2 expects the 5 house-specific tools to collapse into manifest definitions |
| Per-domain mounting and database files | not started — ADR-012 §3 |
| `domains/garage` | not started — the proof |

The five house-specific MCP tools (`get_devices_in_room`, `find_device_controls`,
`get_room_connections`, `get_procedures_for_device`, `get_automations_in_room`)
are still Python, and still the largest remaining piece of house vocabulary
inside the engine. ADR-012 §2 expects most to become declarative — a type filter
plus a relationship walk — at which point `get_devices_in_room` and a future
`get_cars_in_bay` are the same engine query with different constants.
