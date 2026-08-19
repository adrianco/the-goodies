# The Goodies — Design & Implementation Review

**Date:** 2026-08-01 (updated same day after design discussion) · **Reviewed at:** `d00749b` (v0.3.0)
**Status: review only — no implementation yet.** All ADRs are *Proposed*; further review time is planned before any code changes.
**Inputs:** Graphify knowledge graph (4,205 nodes · 6,782 edges · 211 communities over 221 files), full test run (508 passed, 70% coverage, 36s), live production instance (423 entities · 461 relationships · 510 version rows · 5.7 MB), and code reading guided by the graph's community hubs.

This document has two parts: **findings** (what was measured — unchanged by opinion) and **decisions** (where the design discussion landed, recorded in ADR-001…012). Where a decision overturned the reviewer's first recommendation, that is said plainly.

---

## 1. Executive summary

The architecture is fundamentally sound and recent work (v0.3.0 sync acks, the ephemeral-port test harness, auth-at-router-registration) moved it in the right direction. The four-package split — server / client / shared protocol / CLI — is the correct shape for multiple client implementations sharing one sync contract.

**The database engine is not the problem.** The measured scalability ceiling is the *access layer* — full-history table scans reduced in Python, per sync request and per pushed change — not SQLite. Decision: **SQLite stays** (ADR-001), the access layer moves into SQL (ADR-002), and blobs **stay in-row** for single-file consistent backup (ADR-007 withdrawn, owner decision, with a 500 MB tripwire).

The system is being extended around three owner-set premises that emerged in review:

1. **Time is a first-class query dimension** — pick a point in the past and reason about the state of the house (ADR-004: interval edges, as-of snapshots). Every query takes `at`; omitted means now (ADR-009).
2. **Clients are primary** — editing and querying happen mostly client-side; clients hold a full replica of each domain database; the client's edit time is preserved by the server and is the query axis (ADR-004/009).
3. **The engine is domain-generic** — house today, a vehicles domain next, as isolated databases sharing auth/sync/query code, with cross-domain *references* by value but no cross-domain queries (ADR-012).

The most serious code findings are unchanged and still ahead of any of that work: a client-side silent-data-loss bug (filed as **the-goodies#69**), a stale-forever graph cache, ~1,000 lines of dead sync machinery, and the shared core being the least-tested code in the repo.

---

## 2. Findings (measured)

| Dimension | Value |
|---|---|
| Packages | funkygibbon 14.8k LOC · blowing-off 10.2k · inbetweenies 4.4k · oook 0.9k |
| HTTP endpoints | 42 · MCP tools: 12 (7 generic, 5 house-specific) |
| Tests | 508 passing, 36s wall, 70% line coverage |
| Real-server integration tests | 23 files on the v0.3.0 ephemeral-port harness; 15 mock-based |
| Live instance | 423 entities · 461 relationships · 510 version rows · 5.7 MB |
| Graphify | 4,205 nodes · 6,782 edges · 211 communities; 96% deterministically extracted |
| Installs | 2, both controlled — migration freedom is real |

**F1 — Client pull destroys unpushed local edits (worst finding; live bug; filed as adrianco/the-goodies#69).** The sync cycle pulls before it pushes, and `_apply_single_change` (blowing-off `sync/engine.py:268`) overwrites local storage with no pending-edit guard. An offline edit can be replaced by a concurrent server change *before the push phase runs*; the push then sends the server's own version back, which is idempotently acked, clearing the pending mark. The edit is destroyed without the server ever seeing it and no conflict recorded. KittenKong shares the pattern.

**F2 — `GraphIndex` staleness.** Module-global, built on first request, never invalidated. Sync-applied changes never touch it; REST `create_entity` patches it only partially (visible to name search, invisible to `find_path` until restart). Divergent copies under multi-worker.

**F3 — Access-layer scans.** `_latest_entities()` = `select(Entity)` (every version of every entity) reduced in Python, called once per sync **plus once per pushed change**. Delta filtering also in Python. The `cursor` wire field exists but is never populated — responses unbounded. Only secondary index: `entity_type`.

**F4 — Dead sync stack (937 LOC).** `funkygibbon/sync/{binary,conflict_resolution,delta,transfer,versioning}.py` — Merkle trees, `VersionTree`, `DeltaSyncEngine` — has zero production importers; only its own tests exercise it (inflating coverage). Graphify ranks its classes as community hubs of a system that never calls them.

**F5 — Edges have no history, and version-pins don't help.** Relationships carry composite FKs to entity *versions* but no lifecycle (no end, no history): when a device moves rooms the prior topology is destroyed. The pin freezes where an edge pointed at creation — temporal-looking, temporally useless (and it can dangle against post-conflict-resolution latest versions).

**F6 — Wall-clock conflict resolution; losers vanish.** LWW by version-string timestamp (clamp-free), with the losing version *not stored* — reported once in a transient `ConflictInfo`, then gone. A dead `vector_clock` field rides every message (`RESERVED — echoed, never read`). Push application commits per change (partial batch on crash).

**F7 — Client dual store.** blowing-off keeps a SQLAlchemy SQLite DB *and* JSON graph files, with pending marks in a separate file from the writes they mark — no transactional truth.

**F8 — The shared core is the least-tested code.** `inbetweenies/graph/traversal.py` 12%, `mcp/tools.py` 15%, `graph/search.py` 16%, `graph/operations.py` 20% — against 70% overall. Exactly the code every client depends on. Packaging drift alongside (`python_requires` ≥3.8/≥3.9/≥3.11; the 2a6284f `find_packages()` incident).

**F9 — Domain coupling is shallow but schema-deep.** House vocabulary (`EntityType`, `RelationshipType`, `SourceType`) is baked in as `SQLEnum` **database columns** (45 importing files); 5 of 12 MCP tools are house-specific thin queries. The engine itself (sync, versioning, auth, graph, blobs) is already domain-blind.

**What's right (keep):** protocol-as-package (inbetweenies); per-id acks (v0.3.0) — the correct durability contract; causality-aware fast-forward via `parent_versions` (better than the review initially credited); immutable lexically-ordered version strings; the ephemeral-port test harness with server-ownership proof; auth at router registration; Graphify in the loop (its hub list flagged F4 instantly).

---

## 3. Decisions (where the discussion landed)

**D1 — SQLite stays; the access layer is the fix (ADR-001/002).** Honest worst-case sizing (~20k entities, ~150k edges, ~365k version rows) is orders of magnitude below engine limits. Latest-version semantics and delta move into SQL (`is_latest`, `(id, version)` index, `server_seq` watermark, pagination); repository discipline keeps a later Postgres exit a config change. Neo4j rejected (BFS over ≤150k in-memory edges; avg degree 2.2). Vector DB rejected as a store; similarity is a *feature* via FTS5 now and sqlite-vec if/when embeddings get an owner (ADR-006).

**D2 — Blobs stay in-row (ADR-007 WITHDRAWN — owner decision, reversing the review's proposal).** Single-file consistent backup is valued above externalization; current volume is trivial. Residue: a 500 MB size tripwire so the question reopens on evidence.

**D3 — Temporal model (ADR-004 v2).** Edges become immutable **interval rows** (`valid_from`/`valid_to`; change = end + insert); version-pin columns dropped. `snapshot(T)`: accepted-lineage versions by time, edges by interval cover, endpoints resolved **by id + T**. Retention: **keep everything** (the review's pruning proposal withdrawn — pruned history is a hole in as-of fidelity; volume makes forever affordable). Tombstones become structural (`deleted_at`).

**D4 — Two timelines, one job each (ADR-004/005, owner-set).** **Client edit time is the query axis** — preserved verbatim by the server, clamped only inside conflict-resolution comparison. **Server time (`server_seq`) is the replication axis** — cursors, pagination, audit; queries never touch it. Consequence stated honestly: as-of answers can improve when late-syncing edits arrive; once synced, all replicas answer identically. Clock-sanity guards flag (never rewrite) suspicious timestamps.

**D5 — No HLC (ADR-005 v2, reversing the review's first draft).** One authority (the server) means the ordering rule needs to be deterministic and intuitive, not distributed-systems-complete. Resolution ladder: **fast-forward → per-type rule (from the domain manifest) → 3-way merge via DAG common ancestor → clamped LWW → loser preserved**; optional per-type manual-review queue. HLC deferred with an explicit trigger (a second authority).

**D6 — No silent loss (ADR-011).** The pull-guard (F1 fix — first change to make, independent of everything else); losers stored as version rows and acked; one transaction per push batch; a convergence digest over synced rows; a persisted conflict/review table. Salvage from the dead stack: per-type rules, manual queue, common-ancestor merge, state digest — as *ideas*; the code (with its deletion-resurrecting 2-way merge) is deleted per ADR-008.

**D7 — Clients are full temporal replicas with a uniform query interface (ADR-009 v2, owner-set).** Every read takes `at` (omitted = now); client and server run the same `snapshot(at)` rule over the same schema; read-your-writes holds at every point in time (pending edits sit on the timeline at their own timestamps, provisionally accepted). Single SQLite store per domain per client; JSON dual-store deleted; pinned-snapshot (`t0`) reasoning documented as the pattern for multi-query consistency.

**D8 — Domain abstraction (ADR-012, owner-set).** Type columns become strings validated against a per-domain **manifest** (types, relationship endpoint constraints, declarative MCP tools, optional conflict rules, seeds). One engine process mounts N domains: `/{domain}/api/v1/...`, MCP endpoint per domain, **database file per domain**, shared auth, domain-blind sync (`domain` field; per-domain `server_seq` + digest). House first (byte-identical, gated by the conformance suite), then `domains/vehicles` (cars, bays, issues, service records — the as-of machinery applied to new nouns). **Cross-domain queries: out of scope. Cross-domain references: supported by value** — an interval edge in the owning domain with a `(domain, entity_id)` remote endpoint; best-effort dereference; soft validation; dangling reported, never cascaded; `find_references_to` as the explicit above-the-boundary reverse lookup.

**D9 — Tests and packaging (ADR-010).** Real-server harness as the default; a protocol conformance suite parameterized by domain manifest (the compatibility gate for every client, and the byte-identical gate for the abstraction step); 80% floor on `inbetweenies/`; one uv workspace (incl. domain packages), `>=3.11` everywhere.

---

## 4. Sequencing (proposal — nothing starts until review completes)

| Phase | Work | ADRs | Risk |
|---|---|---|---|
| 0 | **Pull-guard fix in both clients** (#69) — independent of all design work | 011 | Low; live data-loss bug |
| 1 | Delete dead stack; GraphIndex ownership + invalidation | 008, 003 | Low |
| 2 | Access layer in SQL (`is_latest`, `server_seq`, pagination); strings-for-enums + domain manifest extraction (house, byte-identical) | 002, 012 | Medium — schema migrations, both installs controlled |
| 3 | Temporal model (interval edges, tombstones, snapshot/diff); protocol v3 (ladder, atomic batches, digest, history-carrying delta); client temporal replicas | 004, 005, 011, 009 | Medium-high — coordinated server+client, the core of the redesign |
| 4 | FTS5 search; vehicles domain instantiation | 006, 012 | Low — additive |
| ongoing | Conformance suite, coverage floor, workspace | 010 | — |

## 5. ADR index

| ADR | Title | Status |
|---|---|---|
| 001 | Primary datastore — SQLite stays; Postgres exit criteria | Proposed |
| 002 | Latest-version and delta queries move into SQL | Proposed |
| 003 | GraphIndex ownership, invalidation, concurrency posture | Proposed |
| 004 | Temporal model — as-of queries, interval edges, bitemporal-lite | Proposed (v2) |
| 005 | Inbetweenies v3 — resolution ladder, clamped LWW, no HLC | Proposed (v2) |
| 006 | Search — FTS5 now, sqlite-vec when embeddings have an owner | Proposed |
| 007 | Blob externalization | **Withdrawn** (blobs stay in-row; 500 MB tripwire) |
| 008 | Delete the dead sync stack | Proposed |
| 009 | Client as temporal replica — time is always a parameter | Proposed (v2) |
| 010 | Tests and packaging | Proposed |
| 011 | Sync robustness — no write is ever silently lost | Proposed |
| 012 | Domain abstraction — engine + house/vehicles; cross-domain references by value | Proposed |

*Related issues: adrianco/the-goodies#69 (pull-guard, F1) · rolandcanyon-cmd/the-goodies-typescript#3 (KittenKong sync acks).*
