# ADR-002: Latest-version and delta queries move into SQL

**Status:** Proposed · 2026-08-01 · **This is the scalability unlock; ADR-001 depends on it.**

## Context

`funkygibbon/api/sync.py::_latest_entities()` executes `select(Entity)` — every version of every entity — and reduces to latest-per-id in Python. It is called once per sync request for the outgoing pull **and once per pushed change** inside `_apply_incoming()`. A 50-change push over 365k version rows materializes ~18M ORM rows. Delta filtering (`updated_at > since`) and entity-type filters also run in Python after the full scan. The only secondary index on `entities` is `entity_type`. The wire protocol has a `cursor` field; the server never populates it — responses are unbounded.

## Decision

1. **Latest-version semantics in SQL.** Either a window-function view (`row_number() over (partition by id order by version desc) = 1`) or — simpler and index-friendly — an `is_latest` boolean maintained transactionally on version insert (set false on the previous latest in the same transaction). Index `(is_latest, updated_at)` and `(id, version desc)`.
2. **A server-assigned monotonic watermark.** Add `server_seq` (integer, autoincrement per row insert) and use it — not wall-clock `updated_at` — as the delta-sync cursor. Clock-independent, gap-free ordering; `since` becomes "seq > N", immune to same-timestamp edge cases the current exclusive-bound comparison has.
3. **Batch the push path.** `_apply_incoming` resolves the latest row for the *specific* id being applied (`where id = :id and is_latest`), not the whole table; the per-batch set of ids is fetched once.
4. **Paginate pull.** Populate `cursor` (last `server_seq` sent) with a page cap (e.g. 500 changes); clients loop until drained. The field already exists on the wire — KittenKong and blowing-off need only handle a non-null value.
5. **Repository discipline:** these queries live in `GraphRepository`/sync repository only; no raw SQL leaks into routers (keeps ADR-001's engine exit clean).

## Consequences

- Sync cost becomes O(changes + page) instead of O(total history × changes).
- One schema migration (new column + backfill + indexes) — trivial at 510 rows, and both installs are controlled.
- `server_seq` becomes the natural foundation for ADR-005's protocol v3 cursor.
- The GraphIndex load (ADR-003) also stops scanning dead versions: it loads `is_latest` rows only.

## Alternatives considered

- **Keep Python-side reduction, add caching** — caches inherit the invalidation problem ADR-003 exists to fix; the database is the right place for "latest".
- **Move to Postgres for the optimizer** — the same view/index work is required there too; engine change doesn't remove the need.
