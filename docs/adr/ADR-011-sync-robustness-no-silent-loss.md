# ADR-011: Sync robustness — no write is ever silently lost

**Status:** Proposed · 2026-08-01 · Companion to ADR-005 (the ladder decides *who wins*; this ADR guarantees *nobody vanishes*). Carries the salvage from the deleted sync stack (ADR-008) and one live bug.

## Context

The design requirement is blunt: concurrent writes must not corrupt or silently destroy data. Three gaps in the live code violate it today, one of them client-side and actively dangerous:

- **C6 (live bug, client): pull overwrites unpushed local edits.** The sync cycle pulls before it pushes, and `blowing-off/blowingoff/sync/engine.py::_apply_single_change` (line ~268) stores the server's entity over local storage with **no check for a pending local edit on the same id**. Sequence: edit entity X offline; another client edits X meanwhile; sync → pull applies the server's version over the local edit *before the push phase runs* → push reads storage (now the server's own version) and sends it back → idempotent ack clears the pending mark. The local edit is destroyed **without the server ever seeing it**; no conflict is recorded anywhere. KittenKong shares the pattern. Filed upstream (see issue link in PR/issue tracker).
- **Losing writes are not stored.** `api/sync.py::_resolve_conflict` reports the loser once in a transient `ConflictInfo` and discards the data. The immutable version table makes preservation nearly free.
- **Push batches are not atomic.** `_insert_version` commits per change; a crash mid-batch leaves a half-applied push — server-side partial state, the textbook corruption case.

## Decision

1. **Client pull-guard (fix first, independently of v3).** An entity with a pending local change is never overwritten by pull-apply. The pull records the incoming server version aside; the pending edit is pushed and the *server* adjudicates via the ADR-005 ladder; the client's state updates from the ack/conflict outcome. Applies to blowing-off and KittenKong; the rule joins ADR-009's reference client design ("a pending mark is a lock against pull-apply").
2. **Losers become version rows.** A version that loses resolution is stored as a non-latest row (it is already parented into the DAG), **acked** (it was processed — ends the ambiguity between "lost" and "not received"), and reported in `conflicts` with winner/loser version ids. Any human can recover the losing content from history. Retention follows ADR-004.
3. **Atomic push application.** One database transaction per push request: apply all changes, commit once, then compute acks. A crash yields "nothing applied, nothing acked, client retries" — never a partial batch.
4. **Convergence digest** (salvaged, simplified, from the deleted Merkle code's `compute_sync_checksum`): server computes `sha256` over the sorted `(id, latest_version)` set — cheap at this scale, incrementally maintainable later — and returns it in every sync response; client computes the same over its cache and compares. Mismatch → client performs a full resync and reports loudly. Divergence becomes detectable instead of theoretical.
5. **Persisted manual-review queue** (salvaged from the dead code's in-memory list): a `sync_conflicts` table holding queued conflicts for entity types flagged `manual` in the ADR-005 ladder, plus the resolution audit trail for automatic resolutions. Surfaced via an API endpoint; at this conflict rate the queue will almost always be empty, which is exactly why it's affordable.

**Anti-decisions, recorded deliberately:** no 2-way content merge anywhere (it resurrects deletions — the deleted stack's cautionary defect); no merge versions authored as synthetic users (`"sync-merge"`) — merge versions carry the *winning writer's* user id plus a `merged: true` marker; no Merkle tree (single-server topology; the digest is the 20-line degenerate form that delivers the verification value).

## Consequences

- The five robustness properties become: single serialization point (exists) · causal fast-forward (exists) · idempotent acked application (exists) · **no silent loss** (2+1) · **verified convergence** (4). Together with the pull-guard (1), a concurrent write can lose *prominence* but never *existence*.
- Client complexity rises by one rule (the pull-guard); everything else is server-side.
- The digest adds one hash per sync — noise at this scale.

## Alternatives considered

- **Push-before-pull ordering** as the C6 fix — narrows the window but doesn't close it (a pull between edit and next sync still overwrites); the guard is the invariant, ordering is just hygiene.
- **Rebase local edits onto pulled versions client-side** — re-parents the pending change for a cleaner fast-forward, but puts merge intelligence in every client; rejected for the same reason ADR-005 keeps resolution server-side.
- **Trust the suite instead of a digest** — tests prove the algorithm; the digest proves *this pair of databases*. Different failure classes (bit-rot, missed invalidation, operator surgery).
