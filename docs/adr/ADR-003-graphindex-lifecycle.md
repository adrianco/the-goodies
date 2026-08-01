# ADR-003: GraphIndex gets an owner, an invalidation rule, and a concurrency posture

**Status:** Proposed · 2026-08-01 · **Correctness fix — highest-priority code change in this review.**

## Context

`routers/graph.py` holds `_graph_index` as a module global, built lazily on first request, never rebuilt. Three defects:

- **Sync writes never touch it.** Once a second client syncs changes in, every graph/MCP read on the server serves pre-sync state until process restart. This defeats the system's core promise.
- **REST writes patch it partially.** `create_entity` calls `_add_entity()` but not `_build_nodes()`: the entity is findable by name yet invisible to `find_path`/`get_connected_entities`. Relationship creation has the mirror problem.
- **Multi-worker divergence.** Under `uvicorn --workers N`, N independent copies drift apart. (Today's deployment is 1 worker — by luck, not by contract.)

## Decision

1. **Single owner.** The index becomes an app-lifecycle object (FastAPI `lifespan` state), not a router-module global. Routers receive it via dependency; nothing else may construct one.
2. **Write-through, fully.** Every mutation path — REST create/update/delete, **sync apply**, blob attach — goes through repository methods that update storage and index in the same code path. `_add_entity`/`_add_relationship` maintain `nodes` incrementally (the incremental update is O(1); `_build_nodes()`'s full rebuild becomes load-time-only).
3. **Generation-tagged rebuild as the safety net.** The index carries the `server_seq` (ADR-002) it was built at; a cheap `max(server_seq)` check on read detects missed writes and triggers rebuild-on-drift (log loudly — drift means a write path bypassed rule 2).
4. **Concurrency posture made explicit: one worker process.** Documented and asserted at startup (refuse `workers > 1` unless the index is disabled). This is honest about the design rather than pretending the global is safe. If multi-worker ever matters, the options are a shared cache or per-worker indexes keyed on generation — a new ADR then.
5. **Deleted entities excluded** at load and on write-through (ties into ADR-004 tombstones).

## Consequences

- Graph reads become correct under sync — the prerequisite for trusting a second client or a mobile app.
- Load cost drops with ADR-002 (latest-rows-only scan).
- The 1-worker constraint is now a stated invariant instead of an accident.

## Alternatives considered

- **Rebuild per request** — correct but wasteful; at 20k entities a rebuild is tens of ms, too slow for every MCP call.
- **TTL cache** — bounded staleness is still staleness; invalidation is cheap here because all writes already funnel through repositories.
- **Drop the index, query SQL each time** — recursive CTEs for BFS in SQLite are possible but slower and far less readable than 150k edges in RAM; wrong trade.
