# ADR-005: Inbetweenies v3 — server-arbitrated resolution ladder; clamped LWW; no HLC

**Status:** Proposed (v2 — rewritten 2026-08-01 after design discussion; supersedes the earlier HLC draft) 

## Context

Design point, agreed: a handful of clients, infrequent updates, server-authoritative sync — and the hard requirement is that concurrent writes can never corrupt or silently destroy data. The earlier draft of this ADR recommended hybrid logical clocks. That recommendation is **withdrawn**: HLC earns its complexity when multiple authorities order events, and this system has exactly one — every write serializes through the server's apply path. Given a single arbiter, the ordering rule only needs to be *deterministic* and *intuitive*; the robustness comes from what happens around the rule (ADR-011), not from the clock.

What v2 already gets right and v3 preserves: server-authoritative apply; causality-aware fast-forward via the `parent_versions` DAG (`api/sync.py` correctly distinguishes fast-forward from concurrent edit, and treats a parentless overwrite as a conflict); idempotent `(id, version)` inserts; per-id acks.

## Decision

1. **Ordering rule: last-write-wins by client edit time, clamped by the server for ordering only.** The client's timestamp is **preserved verbatim in storage** (it is the valid-time query axis, ADR-004 §2 — the owner-set premise is that client time is the truth about when edits happened); the clamp to `server_now + ε` (ε ≈ 5 min) applies only inside the *resolution comparison*, so a skewed or lying clock can never win "from the future" — the only real LWW failure mode this topology has. A clamped-for-ordering edit keeps its claimed time in history but is flagged (ADR-004 §2 clock-sanity guard). Ties break on the version string (already unique via counter + writer id). "The later edit wins" matches human expectation for a smart-home knowledge graph.

2. **Resolution ladder** (server-side, in order; deterministic at every rung):
   1. **Fast-forward** — client edited from our latest → apply, no conflict (exists today).
   2. **Per-entity-type rule** — deterministic rules **supplied by the domain manifest** (ADR-012; salvaged in spirit from the deleted `funkygibbon/sync/conflict_resolution.py`: union device capabilities, prefer-enabled automations — both now live in `domains/house`). Rules produce a merge version with both parents in the DAG.
   3. **Three-way field merge** — find the common ancestor via `parent_versions` (the DAG is already stored; the deleted `VersionTree.find_common_ancestor` proved it's cheap). Keys changed on one side take that side; keys changed on both fall through to rung 4 *for that key set*. Three-way is deletion-safe: the base distinguishes "deleted" from "never existed" — the exact defect that made the dead 2-way merge resurrect deletions.
   4. **Clamped LWW** on whatever remains.
   5. **Loser preserved** — the losing version is stored as a non-latest version row, acked as processed, and reported (ADR-011). Optionally, entity types may be flagged `manual`: instead of rung 4, the conflict lands in a persisted review queue (salvaged from the dead code's in-memory `pending_manual_resolutions`; viable precisely because conflicts are rare at this design point).

3. **Wire changes for v3** (modest; no clock migration): delta pagination via the `server_seq` cursor (ADR-002); **the delta stream carries every immutable row** — all entity versions and edge interval rows since the cursor, not a latest-per-id projection, so clients can replicate history (ADR-009 v2 §4); structural tombstones on the wire (ADR-004 §4); **edge interval rows** — relationship changes carry `valid_from`/`valid_to`, an edge end-event is an ordinary idempotent change, and the pinned `from/to_entity_version` fields leave the wire (ADR-004 §1/§6); a state-digest field for convergence verification (ADR-011 — computed over the full row set, which the replica model makes directly comparable); the dead `vector_clock` field **removed**. Version negotiation covers the transition; both installs are controlled, so the v2 window can be short.

4. **PROTOCOL.md §7 is rewritten to specify the ladder** precisely enough that a client implementation needs no access to server code — it remains the contract a Swift/mobile client is built from. The conformance suite (ADR-010) asserts each rung.

5. **HLC is explicitly deferred**, with its trigger written down: adopt it only if a second authority ever appears (multi-server, peer-to-peer, or client-to-client sync). None is on the roadmap.

## Consequences

- Concurrent edits to *different fields* of the same entity — the common real case — merge cleanly instead of one side losing wholesale.
- Every client implements only: version strings, parent tracking, push-until-acked, and pull-apply. All resolution intelligence stays server-side — the cheapest possible contract for the mobile client.
- Clock skew is defanged rather than solved; acceptable because the server is the only judge and losers are never destroyed (ADR-011).
- Rung 2 and the manual queue are *optional strictness* — the ladder degrades gracefully to fast-forward + LWW if nobody writes type rules.

## Alternatives considered

- **HLC / vector clocks** — solve a multi-authority problem this topology doesn't have; cost lands on every future client implementation.
- **CRDTs** — per-field JSON merge semantics would dominate client complexity for a domain where concurrent same-entity edits are rare and a human review queue is affordable.
- **First-arrival-wins (pure `server_seq`)** — maximally simple and clock-free, but "whoever syncs first wins" surprises humans; clamped LWW is one clamp away and matches intuition.
