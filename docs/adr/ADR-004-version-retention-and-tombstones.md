# ADR-004: Temporal model — as-of queries, interval edges, bitemporal-lite

**Status:** Proposed (v2 — rewritten 2026-08-01 after the as-of-query requirement landed; supersedes the "graph is current" draft)

## Context

New first-class use case: *pick a point in the past and query/reason about the state of the house at that point.* This overturns two calls from the v1 draft of this ADR:

- v1 proposed dropping edge/version pinning because "nothing exposes time-travel traversal" — as-of queries are exactly that consumer.
- v1 proposed pruning old version rows — pruning destroys as-of fidelity inside the pruned window.

What exists today, measured against the requirement:

- **Entities are already time-travelable.** Immutable `(id, version)` rows; the version string's timestamp prefix is lexically ordered = chronological. "Version of E at time T" is a max-version-≤-T lookup that works *now*.
- **Edges are not — the data is being destroyed.** `entity_relationships` rows have no end and no history: when a device moves rooms, the old `located_in` edge is replaced and the prior topology is unrecoverable. The composite version-pin (`from_entity_version`/`to_entity_version`) does not help: it freezes where an edge pointed *at creation*, and says nothing about when it stopped being true. It is the half-measure the review flagged (C4) — temporal-looking, temporally useless.
- **Two timelines already exist implicitly** and must not be conflated: the version-string timestamp is *valid time* (when the edit happened, per the editing client — an offline phone edit at 14:00 synced at 18:00 carries 14:00), while server apply order (`server_seq`, ADR-002) is *transaction time* (when the server learned it). Any as-of design that picks only one silently mis-answers one class of question.

## Decision

### 1. Edges become immutable interval rows

Replace in-place edge mutation/deletion with the same discipline entities already have:

- Each relationship row gains `valid_from` (set at creation) and `valid_to` (nullable; null = still true).
- Changing an edge (re-point, property change) = **end the old row** (`valid_to = now`) **and insert a new row**. Deleting = end the row. Rows are never updated in content and never deleted.
- Edge "current at T" ⇔ `valid_from ≤ T < coalesce(valid_to, ∞)`. Current graph = `valid_to IS NULL` (indexed; the GraphIndex loads exactly this set — ADR-003 unchanged).
- **The composite version-pin columns are dropped** (with their FKs). Edges reference entity *ids*; the *time axis*, not a frozen pin, resolves versions — see §3. (`from/to_entity_version` may be retained as provenance metadata during migration, but nothing joins on them.)

### 2. Two timelines, one job each: client time is the query axis; server time is the replication axis

- Every entity version row and edge row carries **valid time** (client edit time — already in the version string; **materialized as an indexed column and preserved verbatim by the server**) and **transaction time** (`server_seq` / server apply timestamp — arriving with ADR-002).
- **The as-of axis is valid time.** Editing and querying are primarily client-side (ADR-009 v2); "state at T" therefore means *when edits were made*, which is the question the house-history use case asks. The server stores client time untouched — clamped for LWW ordering (ADR-005) but never rewritten.
- **Transaction time is used only for replication**: the sync cursor, pagination, and audit. Queries never consult `server_seq`; sync never consults client time.
- **Retroactivity, stated honestly:** an as-of answer may *improve* when a late-syncing client's edits arrive — the record of 14:00 gets better at 18:00 when the offline phone syncs. This is the correct behavior for history, and it is documented rather than hidden. Once all clients have synced, every replica computes identical snapshots (verified by the ADR-011 digest).
- **Clock-sanity guard:** the ADR-005 clamp stops future-stamped edits; a symmetric guard flags (never silently rewrites) suspiciously *old* valid times — an edit claiming to be older than its client's last sync watermark minus a grace window is applied but reported, so a device with a broken clock can't quietly rewrite deep history.

### 3. As-of resolution rule (the "resolve cleanly" contract)

`snapshot(T)` is defined over the **accepted lineage** on the valid-time axis:

1. **Accepted lineage:** conflict-resolution losers (stored per ADR-011 but recorded as losers in the resolution audit) are *excluded from every snapshot* — they are recoverable archive, not state. This keeps as-of well-defined even though losers sit in history with their own timestamps, and it keeps every replica's answer identical after sync: the rule depends only on synced state plus the shared resolution outcome, never on local perspective.
2. **Entities:** for each id, the accepted version row with the greatest valid time ≤ T; excluded if a tombstone (`deleted_at ≤ T`, structural per §4) is current at T.
3. **Edges:** accepted rows with `valid_from ≤ T < coalesce(valid_to, ∞)` (valid-time axis).
4. **Resolution:** each surviving edge's endpoints resolve to the entity versions chosen in step 2 — *by id + T*, never by pin. An edge whose endpoint has no surviving version at T (entity not yet created / already deleted) is excluded and counted as an integrity warning — with interval edges and structural tombstones this should be impossible; surfacing it beats hiding it.

Exposure: an `at` parameter on **every** graph read — REST, MCP tools, and client-local queries alike — with omitted meaning now (the uniform query interface, ADR-009 v2 §2). Server implementation: SQL snapshot + a transient in-memory index built at T (milliseconds at this scale — the persistent GraphIndex remains now-only, as the cache of the `at = now` case). A `diff(T1, T2)` endpoint falls out nearly free and is the tool an agent wants for "what changed since yesterday?".

### 4. Tombstones (unchanged from v1)

`deleted_at` becomes a structural column on the terminating version row; sync carries `change_type: "delete"` as today. Tombstones are what make step 1's exclusion and step 3's integrity guarantee work.

### 5. Retention: keep everything (v1's pruning is withdrawn)

As-of fidelity is now a feature; pruned history is a hole in it. Version volume at this design point (infrequent updates, blobs excluded from versioning) is small — the original immutable-forever posture is affordable and now earns its keep. The ADR-007 tripwire (warn at 500 MB) is the review trigger; if it ever fires, pruning returns as an *explicit horizon* ("as-of supported back to date X"), never a silent default.

### 6. Sync protocol impact (rides ADR-005/011 machinery)

Edge interval rows sync as immutable rows exactly like entity versions: idempotent on row id, end-events (`valid_to` set) travel as ordinary changes, per-id acks apply. Concurrent edge edits (two clients re-point the same edge) resolve through the ADR-005 ladder — both end the same predecessor row; the ladder picks which successor is "current", and the loser's row stays in history, satisfying ADR-011's no-silent-loss invariant for topology as well as content.

## Consequences

- "State of the house at T" becomes a defined, tested query — on the *transaction* axis, reproducible forever.
- Storage grows with edit history, deliberately; measured against the tripwire rather than pruned on faith.
- One real migration: add interval columns (backfill `valid_from` from `created_at`, `valid_to` null), drop the pinned-version FKs, and change the edge write path from update-in-place to end+insert. Both installs controlled; the edge count is 461.
- Clients replicate the temporal schema and answer as-of locally with the same resolution rule (ADR-009 v2) — every query takes `at`, omitted = now, so "current" is nowhere a special case.
- The conformance suite (ADR-010) gains snapshot invariants: `snapshot(T)` is internally consistent (no dangling edges), stable under replay, and `diff(T1,T2) ∘ snapshot(T1) = snapshot(T2)`.

## Alternatives considered

- **Keep version-pinned edges as the temporal mechanism** — pins say where an edge pointed at creation, not when it ceased; they cannot answer as-of without interval ends anyway, and they force relationship rewrites on every entity version bump. Worst of both worlds; this is the C4 defect, not a design.
- **Full bitemporal (valid-time intervals editable retroactively, audit of the audit)** — the textbook machinery (Snodgrass) is built for correcting recorded history; nothing in the use case edits the past, it only *queries* it. Bitemporal-lite records both instants and skips the four-column interval algebra.
- **Event sourcing / rebuild-from-log** — the version rows *are* the event log in materialized form; a separate log adds a second source of truth to keep consistent for no added query power at this scale.
- **Snapshot tables (periodic full copies)** — simple but lossy between snapshots and redundant beside immutable versions; rejected.
