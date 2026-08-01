# ADR-008: Delete the dead sync stack (funkygibbon/sync/) — one sync implementation

**Status:** Proposed · 2026-08-01 · **Lowest risk, highest clarity-per-line in the review.**

## Context

`funkygibbon/sync/` — `binary.py`, `conflict_resolution.py`, `delta.py`, `transfer.py`, `versioning.py`, 937 LOC of Merkle trees, `VersionTree`, and `DeltaSyncEngine` — has **zero production importers**. Only `funkygibbon/tests/test_sync.py` exercises it (and thereby inflates coverage). The real, live sync is `inbetweenies/sync/` (wire types + protocol) + `funkygibbon/api/sync.py` (server apply/ack logic, rewritten in v0.3.0).

The cost is not the bytes. Graphify ranks `DeltaSyncEngine`, `MerkleNode`, `VersionTree`, and `ConflictResolver` among the repo's community hubs — a newcomer (or an LLM assistant) reading the graph or grepping "how does sync work" finds an elaborate machine that never runs, beside the modest one that does. During this review it cost real time to establish which stack was live; it will cost every future contributor the same.

## Decision

1. **Delete `funkygibbon/sync/` and its test file.** Git history preserves it; if a Merkle-based delta optimization is ever wanted, it will be redesigned against protocol v3 anyway, not resurrected.
2. **Sweep the same class of debt in the same pass:** `blowing-off/blowingoff/sync/conflict_resolver.py`'s overlap with `inbetweenies/sync/conflict.py` (client should use the shared one), and any `archive/`-candidate modules Graphify shows with no inbound edges (a `graphify update .` after the deletion gives the verification for free).
3. **The invariant, stated in CLAUDE.md:** sync logic lives in exactly two places — `inbetweenies/sync/` (shared contract) and `funkygibbon/api/sync.py` (server application). A third location is a review-blocking smell.

## Consequences

- ~1,000 LOC and several misleading graph hubs disappear; the honest coverage number drops slightly (the deleted tests tested deleted code — the number was lying upward).
- "How does sync work" has one answer.
- No runtime change whatsoever — verified by the zero-importer analysis; the full suite must pass unchanged after deletion as the merge gate.

## Alternatives considered

- **Move to `archive/`** — the repo already has an `archive/` for docs; code that doesn't compile against the living tree rots misleadingly there too. Git history *is* the archive for code.
- **Finish the Merkle design instead** — delta-by-watermark (ADR-002/005) is O(changes) already; Merkle anti-entropy pays off for peer-to-peer or many-replica topologies, which contradicts the server-authoritative model the protocol just doubled down on.
