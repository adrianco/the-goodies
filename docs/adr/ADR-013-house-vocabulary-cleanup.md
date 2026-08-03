# ADR-013: House vocabulary cleanup — one word, one meaning

**Status:** Accepted · 2026-08-03 · Supersedes the byte-identical constraint of
[ADR-012](ADR-012-domain-abstraction.md) §6.1, deliberately and only for the
house vocabulary.

## Context

ADR-012 moved the vocabulary out of `SQLEnum` columns and out of
`EntityRelationship.is_valid_for_entities` into a manifest, byte-identically —
the point being to change *where* the rules live without changing *what* they
say. That landed. Making the rules data then made three things visible that
were not visible as a dict literal inside a method.

Measured against the live instance (423 entities, 461 relationships):

**1. `part_of` means two different things, split by source system.**

| Shape | Count | `source_type` |
|---|---:|---|
| `part_of` device → device | 104 | `imported` |
| `part_of` room → home | 48 | `homekit` |
| `located_in` device → room | 252 | mixed |

HomeKit uses `part_of` for spatial containment. The import uses it for
composition — a device that is a component of another device. One word, two
meanings, and the reason `located_in` and `part_of` looked like redundant
hierarchies: they are not redundant, they are *conflated*.

**2. 107 live edges violate the vocabulary's own declared rules.**
`part_of device → device` (104) is not in `part_of`'s declared endpoints at all,
plus `has_blob door → note` (2) and `note → note` (1).

They exist because the endpoint check runs in exactly one write path —
`inbetweenies/mcp/tools.py:243`. The REST path has it commented out
(`funkygibbon/api/routers/graph.py:256`) and sync never checks. A rule enforced
on one of three doors is not a rule.

**3. Two relationship types cannot be created at all.** `contained_in` and
`depends_on` declare no permitted endpoint pairs, so every attempt is rejected
for every combination.

Two further facts shape the decisions:

- **The Roland instance is incomplete, not minimal.** Its automation (a Vantage
  system) physically exists and has not been described in the graph. An earlier
  reading of the zero counts as "a feature modelled and never built" was wrong.
- **There are two deployments with different provenance.** Roland: rooms from
  Apple HomeKit, automation from Vantage. Corfe: Home Assistant plus HomeKit,
  with no Vantage equivalent. The vocabulary has to describe both.

## Decision

### 1. `located_in` is spatial; `part_of` is composition

| | Meaning | Endpoints |
|---|---|---|
| `located_in` | Physical containment — where a thing *is* | device→room, device→zone, room→zone, room→home, zone→home |
| `part_of` | Composition — a thing is a component of another | device→device |

This is what the data already does in 356 of 404 cases. The 48 HomeKit
`part_of room → home` edges are migrated to `located_in`, which is the only data
change either meaning requires.

`contained_in` is deleted: it duplicates `located_in` and has never been
creatable.

### 2. `depends_on` becomes explicitly unconstrained

It has no obvious endpoint constraint and a real use once automation is
described (an automation depending on a device, a schedule on an automation).
Declared `allowed_endpoints=None` rather than `()`, so it is usable rather than
silently rejected.

### 3. `has_blob` is explicitly unconstrained

Anything may have a blob attached; `door → note` and `note → note` are
legitimate. Recording that as `None` is the accurate statement, where the
current empty tuple happens to be permissive only because nothing enforces it.

**Not resolved here:** blobs are linked both by `has_blob` edges (26) and by
`content.blob_id`. Both are live. Choosing one is a data-model question beyond
vocabulary and is left open.

### 4. Automation provenance is an `app` entity, not a source type

`automation`, `schedule`, `procedure` and the relationship types serving them
are retained. They are undescribed, not absent.

An earlier draft of this ADR added `home_assistant` and `vantage` to
`source_type`. That was wrong twice over. It does not scale — Alexa, Google
Home, SmartThings and every IoT app with its own scheduler would each need a
value, and the list never stops growing. And it conflates two different facts:

| | Question it answers |
|---|---|
| `source_type` | How did this *record* reach the graph? |
| the running system | Which system *executes* this automation? |

The second stays true however the record arrived. An automation imported from a
Home Assistant backup but actually run by Alexa is `imported` and Alexa-run;
one field cannot say both.

The vocabulary already had the mechanism: an **`app` entity per system** —
Alexa, Google Home, HomeKit, Vantage, Home Assistant, a vendor's own scheduler
— with `manages` edges to what it runs. Unbounded without schema change, and it
makes *"what breaks if this system goes away"* a graph traversal rather than a
text search.

This also explains why `app` looked like a half-built feature: one entity
exists and nothing links to it. It is the right mechanism, declared before the
automations it was meant to describe.

`source_type` therefore stays at five and keeps its original meaning.

**`controlled_by_app` is deleted.** It was the exact inverse of `manages` —
`device → app` against `app → device` — which is the same one-thing-two-ways
defect as the `located_in`/`part_of` conflation this ADR exists to fix. Both
were unused, so there was no cost to choosing; `manages` wins because the app is
the actor and reads as the subject.

### 5. Endpoint validation is enforced on every write path

REST, sync and MCP, after the data migration. A manifest that only one path
consults documents an intention; one that every path consults is a rule.

Ordering matters and is not negotiable: **migrate first, then enforce.**
Enforcing first would reject 107 existing edges and break both servers.

## Consequences

- One data migration, on top of the ADR-002 backfill: re-type 48 edges. Small,
  reversible, and both installs are controlled.
- The house manifest stops being *derived* from `EntityType` and
  `is_valid_for_entities` and starts being *declared*, because it now says
  something they do not. The 2016-triple equivalence check retires with it.
- `contained_in` disappears from the vocabulary. No data uses it and none could.
- Enforcement will reject writes that previously succeeded. That is the point,
  and it is why the migration precedes it.
- ADR-012's conformance gate still holds for the *engine*: this changes the
  house vocabulary, not the protocol. The conformance suite must still pass.

## Alternatives considered

- **Merge `located_in` and `part_of` into one containment type.** Simplest
  vocabulary, but it would re-type the 104 device→device composition edges into
  spatial containment and assert that a component is *located in* its parent.
  That is false, and unrecoverable once merged.
- **Widen `part_of` to permit both shapes.** Zero migration, and preserves the
  conflation permanently — the two source systems would keep meaning different
  things by the same word, with nothing to distinguish them.
- **Enforce first, migrate after.** Rejected: it breaks both live servers for
  the duration.
- **Drop the automation vocabulary as unused.** Rejected on the owner's
  correction: the automation exists physically and is simply undescribed.
  Deleting it would mean rebuilding it to describe the Vantage and Home
  Assistant systems.
