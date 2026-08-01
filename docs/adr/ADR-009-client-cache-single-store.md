# ADR-009: The client is a temporal replica — one query interface, time is always a parameter

**Status:** Proposed (v2 — rewritten 2026-08-01; supersedes the latest-only cache draft after the client-side as-of requirement landed)

## Context

Owner-set design premises (2026-08-01 discussion): **editing and querying are primarily client-side, with sync to the server; clients hold their own copy of the entire database; the client's edit time is preserved by the server.** Plus the design rule that motivated v2: *every query carries a time, and supplying the current time yields the latest state.* v1's "client caches are latest-only; as-of is a server capability" contradicts all of it.

The design point makes full replication the *simple* answer, not the heavy one: infrequent updates and blob-free versioning mean full history is small — 510 version rows today; years of edits are tens of thousands of rows, single-digit MB. A phone holds the whole timeline comfortably.

The v1 problems all still stand and their fixes carry over: blowing-off's dual store (SQLAlchemy DB **plus** JSON files), pending marks in a separate file from the writes they mark, KittenKong's shared shape, and the pull-overwrite bug (ADR-011 C6, filed as the-goodies#69).

## Decision

### 1. One SQLite store, same shape as the server

The client cache is a **replica of the server's temporal schema**: `entity_versions` (immutable rows, all versions), `relationships` (immutable interval rows per ADR-004), `pending_changes`, `sync_state` (cursor per server). The JSON `LocalGraphStorage` and the parallel SQLAlchemy store are deleted; `client_sync_tracking` merges into `sync_state`. Latest-only projection disappears — "latest" is a query, not a table. Under multi-domain (ADR-012), this design instantiates **once per domain**: one local database file per domain a client holds, synced against that domain's endpoint, with its own cursor and digest.

### 2. The uniform query interface

Every read — client and server, REST, MCP tool, and library call — takes `at: Timestamp` with **omitted/`null` meaning now**:

- `snapshot(at)` resolves exactly as ADR-004 §3: entity versions by max-axis ≤ `at`, edges by interval cover, endpoints resolved by id + `at`.
- Because the schemas match, **the resolution rule is implemented once per client platform against the same table shapes** — the Python, TS, and future Swift implementations are ports of one small algorithm (a two-predicate SQL query plus endpoint resolution), not three designs. It joins PROTOCOL.md as part of the reference client design.
- `omitted = now` rather than the caller stamping wall-clock, so the common case has one canonical meaning and no client/server clock comparison. Passing an explicit time is choosing the time-travel path, deliberately.
- **Pinned-snapshot reasoning:** a caller may take `t0 = current cursor position` and pass it to every query in a session, getting a *mutually consistent* view immune to syncs landing mid-session — the primitive an LLM agent reasoning over the house wants. This falls out of the design for free and gets documented as the recommended pattern for multi-query reasoning.

### 3. The client's time axis, honestly defined

The as-of axis is **valid time — client edit time** (ADR-004 §2), which the server preserves verbatim. A pending (unsynced) local edit therefore already has its place on the timeline: its own timestamp. The rule:

- Every query — `at = now` or `at = past T` — resolves over **synced accepted rows plus this client's pending rows**, all by valid time. Read-your-writes holds at every point in time: your 14:00 edit is visible in a 14:30 as-of query whether or not it has synced yet.
- A pending edit is *provisionally accepted*: if conflict resolution later demotes it (ADR-005 ladder), the local answer for that window changes — the same retroactivity that late-arriving remote edits already cause (ADR-004 §2), symmetric and documented.
- **The convergence digest (ADR-011) is computed over synced state only** — pending rows are excluded, so two mid-sync replicas don't false-alarm; after sync, identical row sets ⇒ identical digests ⇒ identical snapshots.

### 4. Sync carries history, not a latest-projection

The v3 delta stream (ADR-005) ships **every immutable row** — all entity versions and edge interval rows/end-events since the cursor — not the server's latest-per-id reduction. Clients stop discarding superseded versions. Idempotent row-id application and per-id acks are unchanged; a fresh client's full sync is delta-from-zero (paginated) and equals the server's history minus blobs (blob `data` stays lazy per ADR-007's surviving fields).

### 5. History horizon as the escape hatch, not the default

If some future client genuinely can't hold full history, it may sync from a cursor floor (`server_seq ≥ X`). Its as-of answers before the horizon are refused offline ("history unavailable before ⟨date⟩") or proxied to the server when online — never silently wrong. No current client needs this; it exists so the protocol doesn't have to change when one does.

### 6. Durability rules (carried from v1, unchanged)

Pending marks are written in the **same transaction** as the local edit; ack processing clears them transactionally; **pull-apply never overwrites an entity with a pending local change** (the ADR-011 C6 guard — with the temporal schema this becomes natural: pulled rows *insert alongside* history rather than replacing state, and only the "what is latest" question ever contends).

## Consequences

- Client-side time travel works offline, and "current" is nowhere a special case — one code path, tested once per platform against the shared conformance suite (ADR-010), which gains the §3 axis rules as cases.
- Client storage grows from "latest" to "everything" — single-digit MB at this design point, same 500 MB tripwire philosophy as the server, with §5 as the pressure valve.
- The pull-overwrite bug class disappears *structurally*: immutable-row insertion has no overwrite to get wrong. (The C6 fix in the current latest-only clients is still needed now — ADR-011 sequencing unchanged.)
- Migration per client: create the temporal schema, full-sync from zero, delete JSON files. Both Python clients trivial; KittenKong follows its issue #3 work.

## Alternatives considered

- **Latest-only cache + server-proxied as-of (v1)** — dies on the offline requirement; also leaves client and server running *different* query logic, which the uniform-interface rule exists to prevent.
- **Materialized `latest` table beside history** — a denormalization to maintain under sync; at this row count, `max(version) ≤ at` with an index *is* fast enough, and one source of truth beats two.
- **Sync latest + fetch history on demand** — reintroduces online-only as-of through the back door and a second wire shape; rejected.
