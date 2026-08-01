# ADR-001: Primary datastore — SQLite stays; explicit exit criteria for Postgres

**Status:** Proposed · 2026-08-01

## Context

Entities live in SQLite (WAL) as immutable `(id, version)` rows. Live scale: 423 entities / 510 version rows / 5.7 MB. Honest worst-case for the larger use cases: ~20k entities, ~150k edges, ~365k version rows over years — 3–5 orders of magnitude below any engine's limits. Deployment is one server process per home on a Mac mini via launchd; backup is file copy (already built and running). Two installs, both controlled; migration is cheap *whenever* a reason exists.

Measured bottlenecks are in the access layer (full-history scans reduced in Python — see ADR-002), not the engine.

## Decision

1. **SQLite remains the system of record** for structured data (entities, relationships, sync metadata).
2. **No engine-specific SQL outside the repository layer** — everything through SQLAlchemy async, so the engine remains swappable by config + data copy.
3. **Postgres is adopted if and when one of these triggers occurs**, and not before:
   - a second writer *process* per install (beyond one FastAPI app),
   - multi-tenant hosting (many homes, one database),
   - hot server-side JSON content queries needing JSONB+GIN,
   - replication requirements beyond file-level backup/mirror.
4. **Neo4j is rejected** as primary store: the graph ops in use (BFS, k-hop, type/name lookup) run in microseconds in memory at this scale; a JVM service, a second wire protocol, and loss of single-file backup buy nothing. The in-memory index is the right design (its invalidation bug is ADR-003).
5. **A dedicated vector database (ruvector or otherwise) is rejected as a store**; the similarity *feature* is ADR-006 (sqlite-vec in-file). Note: evaluated as a category — no product-specific assessment of ruvector was made.

## Consequences

- Zero migration work now; deployment/backup story unchanged.
- ADR-002 is mandatory — staying on SQLite is only viable with the access layer fixed.
- Revisit at each trigger, not on a calendar.

## Alternatives considered

- **Postgres now** — buys concurrency and JSONB nobody uses yet; costs a service to run on both installs and complicates the "database is one file you can copy" operational story that backup/mirror already exploits.
- **Neo4j** — wrong workload class; average degree 2.2, no declarative multi-hop queries anywhere in the API.
- **Vector store as primary** — a knowledge graph is not an embedding index; would still need a relational/graph store beside it.
