# ADR-006: Text search via SQLite FTS5; similarity via sqlite-vec (optional, deferred-friendly)

**Status:** Proposed · 2026-08-01

## Context

`search_entities` walks all entities in Python computing substring/word-overlap scores; `find_similar_entities` ranks by shared-word counts. Fine at 423 entities; linear and quality-poor at 20k with document-like content (manuals, notes). This is also where "should it be a vector database?" actually lands: the *feature* is similarity, the *store* doesn't need to change (ADR-001).

## Decision

1. **FTS5 virtual table** over `name` + flattened `content` text fields, maintained by triggers (or in the repository write path alongside ADR-003's write-through). BM25 ranking replaces the hand-rolled scorer for `search_entities`. Zero new dependencies — FTS5 ships in SQLite.
2. **Similarity, when wanted, is `sqlite-vec` in the same database file:** an embeddings table keyed by entity id, refreshed on write for the entity types where semantic similarity matters (notes, manuals, procedures). Exact k-NN at ≤20k vectors is milliseconds; no ANN index tuning, no second service, single-file backup preserved.
3. **Embedding generation is the only open dependency** (a local model or an API call). Until that's chosen, `find_similar_entities` falls back to FTS5 more-like-this (query by top terms of the source doc) — a real quality improvement over word overlap with no ML dependency at all. sqlite-vec lands only when embeddings have an owner.
4. Search stays server-side (clients query via API/MCP as today); client-local search on mobile can reuse the same FTS5 design in its local store (ADR-009) later.

## Consequences

- Search quality and cost both improve; the Python scorer and its 16%-covered module retire.
- No new deployment artifacts; ADR-001's single-file story holds.
- A dedicated vector DB (ruvector et al.) remains unjustified at this corpus size; revisit only if embeddings outgrow memory-mapped exact search (≫10⁶ vectors — not a smart-home number).

## Alternatives considered

- **Dedicated vector database** — third artifact to run/back up/keep consistent on two Mac minis, for ≤60 MB of vectors. Category mismatch.
- **Postgres + pgvector** — the right shape *if* ADR-001's exit ever triggers; not a reason to exit by itself.
- **Embed in the API process with FAISS/numpy** — workable, but loses persistence-with-the-data and adds Python-only state a Swift server-less future would re-solve.
