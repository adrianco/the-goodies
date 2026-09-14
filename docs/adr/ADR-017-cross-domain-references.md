# ADR-017: Cross-domain references — time-stamped links by value, never by join

**Status:** Proposed · 2026-09-14 · Promotes ADR-012 §4 to a decision of its
own, with the temporal semantics and the broken-reference handling that §4
left implicit. Owner direction (2026-09-14): *separate back ends; a
time-stamped cross-domain reference mechanism; ways to handle broken
references — which, since nothing is ever deleted, should be tractable.*

## Context

Domains are separate back ends (ADR-018): the house and the vehicles graphs
live in different database files, served by different processes, each with
its own `server_seq` timeline, digest and manifest. Nothing joins them, by
design — a query never spans domains, a backup is one file, and a domain's
sync converges on its own.

But the world is not partitioned that neatly. *"The winter tyres are in the
garage on the second shelf"* is a vehicles fact whose far end is a house
room. *"The EV charger is on circuit 14"* is a vehicles tool referencing a
house device. Without references the vehicles domain reinvents places
(`location`) that the house already models, and the two descriptions of one
garage drift apart.

The append-only model changes what "broken reference" means. Nothing in
either domain is ever deleted: an entity that goes away gets a tombstone
version, an edge that stops being true gets `valid_to`, and every earlier
version stays readable (ADR-004). So a reference can never point at *nothing*
— at worst it points at something that is *no longer current*, and the graph
can say precisely when it stopped being. That is the property this ADR
builds on.

## Decision

### 1. A reference is an ordinary interval edge in the referring domain

An edge whose far endpoint is in another domain is a row in the **referring**
domain's `entity_relationships` table, exactly like any other edge: it has an
`id`, `valid_from` / `valid_to`, `server_seq`, `properties`, and it syncs on
the referring domain's timeline and counts in its digest. What is new is that
one endpoint is **qualified**:

```
to_entity_id   = "house:4f2c…"          # <domain>:<entity id>
properties     = {"ref": {"domain": "house", "label": "Garage", "type": "room",
                          "as_of": "2026-09-14T10:02:00Z"}}
```

Concretely, two nullable columns on the relationship table — `to_domain`
and `from_domain` — with the id columns holding the bare id; `NULL` means
"this domain", so every existing edge is unchanged and domains that never
reference outward pay nothing. (The `<domain>:<id>` spelling is the wire and
tool form; the columns are the storage form.) **Exactly one endpoint may be
external.** The edge always lives in the domain of its local endpoint.

The manifest declares where such edges may point:

```python
RelationshipRule(name="stored_in", allowed_endpoints=(("part", "external:house/room"), ("tool", "external:house/room")))
```

`external:<domain>/<type>` is a fourth endpoint spelling alongside a type
name and `"*"`; `external:house/*` means any house type. A domain that
declares none cannot create a reference; the engine has no default.

### 2. The reference is time-stamped twice, and the second stamp is the point

The edge interval (`valid_from` / `valid_to`) says **when the referring
domain claimed the link** — the tyres went onto that shelf on the 22nd and
came off on the 3rd. That is ordinary ADR-004.

The cached `ref.as_of` says **what version of the far entity the link was
made against** — the instant at which the referrer last saw the target and
recorded its `label` and `type`. This is what makes dereference honest:

- Resolving the reference *as of `T`* means reading the target domain's
  `snapshot(T)` — the house room as it was when the tyres were put there,
  not as it is now. `get_entity(id, at=T)` already exists (ADR-004 §3); the
  reference simply carries the `T` to ask with.
- Resolving it *now* means reading the target's current version and
  comparing with the cache: same label and type → fine; different → the
  reference is **stale**, which is information, not an error ("the room you
  called Garage is now Workshop").

A reference therefore never asks "does the target exist?"; it asks "what
was the target at `as_of`, and what is it now?" — two questions the append-
only stores can always answer, because nothing has been removed.

### 3. Broken references: a taxonomy, and none of them is a hole

Because neither domain deletes, there are exactly four states, all
detectable, none of which loses the referring domain any data:

| State | How it is known | What the reader gets |
|---|---|---|
| **Live** | target's current version is not a tombstone; label/type match the cache | the target, resolved |
| **Stale** | target current, but label or type differ from `ref` | the target, plus `stale: true` and both labels |
| **Retracted** | target's current version is a tombstone (ADR-004 §2) | the target *as of `ref.as_of`* (still readable), plus `retracted_at` — the tombstone's version timestamp |
| **Unreachable** | the target domain is not mounted / not held locally / not answering | the cached `label` and `type`, plus `unresolved: true` |

There is no fifth state "gone", and that is the whole reason the
append-only model was worth its cost here. A referring domain's edge stays
exactly as true as it was — the tyres *were* on that shelf; the shelf being
retracted later does not unmake it. **No cascades, by construction**:
tombstoning a house room cannot reach into `vehicles.db`. What a retraction
*does* do is show up in the next integrity sweep (§5) so a human can decide
whether the vehicles edge should be ended too.

The only genuinely lossy case is a target domain whose database has been
**restored to before the target existed** — a backup-restore, not a delete.
Then `as_of` resolution fails for real. The sweep reports it as `missing`
and the cached label still renders; the edge is not touched.

### 4. Dereference is an MCP-layer act, best-effort, on both sides

Server side (ADR-018: both domains mounted on one host, separate processes),
dereference is an HTTP call to the target domain's `get_entity_details`
tool with `at=ref.as_of`, using the shared token. Client side, a replica
holding both domains resolves locally the same way; a replica holding only
one shows the cached label and the qualified id. Unreachable ≠ broken.

Engine tools, in every domain's catalog:

- `create_relationship` accepts a qualified endpoint (`to_entity_id="house:…"`)
  for a relationship the manifest declares `external:`; the engine resolves
  the target once at write time to fill `ref.label` / `ref.type` / `ref.as_of`,
  **validates softly** (warns on a type mismatch, never rejects — cross-domain
  write ordering is not guaranteed and must not deadlock a sync), and refuses
  only when the manifest has no `external:` rule for that pair.
- `resolve_reference(relationship_id [, at])` — the four-state answer above.
- `find_references_to(domain, entity_id [, at])` — the reverse lookup ("what
  vehicle things are in this room?"), which is inherently cross-domain and
  is therefore offered **above** the isolation boundary: it scans the
  reference edges of every domain the caller holds, and never crosses the
  network to one it does not.
- `list_relationships` / `get_connected` / the declared walks return
  references with the `ref` block attached and do **not** follow them:
  a walk stops at a domain boundary. Following is `resolve_reference`.

### 5. Integrity is a sweep that reports, never a constraint that rejects

A periodic job (with the backup scheduler, once a day) walks every reference
edge in every mounted domain and classifies it per §3. It writes a report —
counts per state and the stale / retracted / missing edges by id — that the
`get_statistics` tool exposes under `references`. It changes nothing. This is
distinct from the intra-domain integrity that ADR-004 §3.4 makes
impossible-by-construction; across domains, "impossible" is not available,
so "always visible" is the substitute.

### 6. Sync carries references unchanged

A reference is a row in one domain, so it syncs with that domain: the wire
shape gains the two nullable domain fields, and a replica that holds only
the referring domain stores it verbatim without resolving it. Protocol
version is unchanged (additive, nullable). The target domain's timeline is
never consulted by the referring domain's sync.

## Consequences

- The vehicles domain can say where things are in the house without
  duplicating the house; its `location` type becomes the *fallback* for
  places the house does not model (a storage unit across town), not the
  primary one. The manifest gains `stored_in` (part/tool → external:house/room)
  as the first reference rule, and the walk skill records "kept in the
  garage" as a reference.
- Two nullable columns and a migration that adds them; no existing row
  changes. Domains that never reference pay nothing.
- Reads across the boundary are best-effort and say so; a reader must handle
  the four states. That is the honest cost of separate back ends and is
  cheaper than the alternatives below.
- Tombstoning something that is referenced from another domain is no longer
  silent: the sweep surfaces it. This is a feature: it is the first time the
  house has any way of knowing that the vehicles domain depends on one of
  its rooms.
- The house domain gains nothing it must do; it may, later, declare references
  outward (a `device` `powers` an `external:vehicles/tool`).

## Alternatives considered

- **One database, a `domain` column on every row** — rejected in ADR-012:
  couples backup, sequence and digest across domains for the convenience of
  a join, and the owner's topology decision was separate files.
- **Hard foreign keys via a shared entity table** — impossible across files
  and undesirable anyway: it makes "delete" cascade, which the append-only
  model exists to forbid.
- **Copy the referenced entity into the referring domain** — rejected: two
  copies of one room, neither authoritative, drifting; the cached `label` is
  the deliberately minimal version of this (a display hint, not a copy).
- **References resolved at write time only, never re-checked** — rejected:
  it is §3's *stale* state with no way to know; the sweep is the cost of
  knowing.
- **Reject the tombstone of a referenced target** — rejected: it makes the
  house depend on the vehicles domain's data to do its own housekeeping,
  which inverts the isolation the whole design is built on.
