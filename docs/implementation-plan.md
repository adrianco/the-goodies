# The Goodies — Staged Implementation Plan

**Date:** 2026-08-01 (revised 2026-08-02 — see §1.2) · **Planned at:** `715a3e8` (v0.3.0 + ADR-001…012)
**Status: proposed — awaiting owner review. Nothing implemented in this repository.**
**Companion to:** [`design-review-2026-08.md`](design-review-2026-08.md) (findings) and [`adr/`](adr/) (decisions). This document is the third piece: *order of work*, and why that order.

---

## 1. Findings were re-verified before planning

The review's findings were spot-checked against the code rather than carried forward on trust. Two confirmed; one is materially wrong in a way that changes which work comes first.

| Finding | Verdict | Evidence |
|---|---|---|
| **F3** — access-layer full scans | Confirmed | `api/sync.py:142-150` is `select(Entity)` over every version, reduced in Python. `cursor` is never populated server-side. |
| **F4** — dead sync stack | Confirmed | 937 LOC in `funkygibbon/sync/`; no importer outside that package and its own tests. |
| **F1 / #69** — pull destroys unpushed local edits | **Real in KittenKong only** | See §1.1. |

### 1.1 F1 is a KittenKong bug, not a shared one

The review states the pull-then-push hazard exists in blowing-off and that *"KittenKong shares the pattern."* The two clients differ on precisely the line that decides it.

**blowing-off — safe.** `sync/engine.py` captures the push payload *before* the pull:

```
line 106   local_changes = await self._get_local_changes(last_sync)   # snapshot
line 109   sync_response = await self.protocol.sync_request(...)      # pull
line 120   await self._apply_single_change(change)                    # overwrite
line 127   await self._push_local_changes(local_changes)              # sends the snapshot
```

Running the exact failure sequence from #69 (offline local edit → concurrent server edit → sync) shows the push transmitting `LOCAL-EDIT`, both versions retained locally, and the pending mark cleared only because the server acknowledged the client's own edit. The write reaches the server and is adjudicated.

**KittenKong — the bug is real.** `packages/kittenkong/src/sync/engine.ts`:

```
Step 1  syncRequest()          // pull
Step 2  applySingleChange()    // storeEntity(entity) — no pending guard
Step 4  getLocalChanges()      // AFTER the overwrite
        syncPush(localChanges) // sends the server's own version back
```

`getLocalChanges()` runs after local storage has been overwritten, so the push payload is the server's version. The idempotent ack then clears the pending mark and the local edit is destroyed with the server never having seen it — exactly the mechanism #69 describes.

**Consequences for the plan.** The urgent fix belonged in the TypeScript client, which is the one in production. blowing-off is correct *by accident of statement order*, not by an expressed invariant — a future refactor could silently reintroduce the bug, so it gets a regression test that pins the ordering rather than a behavioural change. ADR-011 §1's pull-guard remains the right invariant for both clients; only its urgency differed.

**Status: fixed upstream.** KittenKong shipped the guard in `ee4eea5` (2026-08-02) with tests (`sync-pending.test.ts`), skipping pull-apply for any id carrying a pending local edit and pushing relationships alongside. The same commit's comment traces the mechanism and cites #69. The Python-side regression test remains outstanding.

**Cross-repo note.** KittenKong lives in `rolandcanyon-cmd/the-goodies-typescript` (upstream). `adrianco/the-goodies-typescript` is a *fork* of it and lags; fixing the fork would not reach production. Stage A retains a coordination dependency outside this repository.

### 1.2 The guard and the loser-ack are coupled — shipping one alone livelocks

*Added 2026-08-02, after the upstream guard landed.*

ADR-011 lists the pull-guard (§1) and loser-acknowledgement (§2) as separate numbered decisions. They are not separable in practice, and the first draft of this plan wrongly split them across Stage A and Stage E.

This server does not acknowledge a change that loses conflict resolution — deliberately, and pinned by a passing test (`funkygibbon/tests/test_sync_protocol.py::test_rejected_change_is_not_reported_as_applied`: *"A blind overwrite that LOSES resolution must stay pending on the client."*). That was correct behaviour when an unacked id simply retried. With a pull-guard in the client it is no longer sufficient:

1. Client holds a pending edit `v_local`, older than the server's `v_other`.
2. Pull returns `v_other` → the guard skips it, because the id is pending.
3. Push sends `v_local` → it loses clamped LWW → **not acked**.
4. The pending mark survives, so the guard keeps blocking `v_other`.
5. Every subsequent sync repeats steps 2–4 unchanged.

The entity never converges on that client and retries indefinitely. The trigger is precisely the scenario the guard exists for — edit offline at 14:00, another client edits at 15:00, sync at 18:00 — so this is a routine path, not an exotic one.

Severity is *stuck divergence*, not destruction: both versions survive and the outcome is strictly better than the silent loss it replaced. But it is incomplete, and it is live now that the client half has shipped.

ADR-011 §2 already contains the resolution — a loser is **"acked (it was processed — ends the ambiguity between 'lost' and 'not received')"**. That acknowledgement is what breaks the cycle: the client drops its pending mark, the guard stops firing, and the next delta delivers the winner. Only the *ack* is required now; storing losers as version rows can still wait for Stage E.

Two further consequences worth recording:

- The convergence digest (ADR-011 §4) would surface this class of divergence automatically. It is cheap and server-side, which is an argument for pulling it forward into Stage C rather than leaving it with the rest of §11.
- The guard's own comment asserts the skipped server version "is re-sent on the next delta once this id is no longer pending". That holds only while the delta filter re-selects an entity whose latest row has not changed. It should be asserted in the conformance suite (Stage B) rather than assumed.

---

## 2. Stages

Each stage lists its exit gate. A stage is not "done" until its gate is demonstrable, because later stages assume it.

### Stage A — Stop the bleeding
*No design dependency. Can start immediately and in parallel with Stage B.*

| Work | ADR | Risk |
|---|---|---|
| ~~KittenKong: pull-guard~~ — **done upstream** in `ee4eea5` | 011 §1 | Was live data loss; closed |
| **Server: acknowledge a losing change** (§1.2) — unblocks the shipped guard | 011 §2 | **Live livelock**; small, server-only |
| blowing-off: regression test pinning the pre-pull snapshot ordering | 011 §1 | Trivial |
| Delete `funkygibbon/sync/` (937 LOC) + client conflict-resolver overlap | 008 | Low — no importers |
| GraphIndex: single owner, write-through on every mutation path, drift rebuild | 003 | Low |

The loser-ack is now the *only* urgent item, and it is on this side of the fence: the client half shipped first, which is what turned a latent coupling into a live one.

**Exit gate:** a losing push is acked, its pending mark clears, and the following delta delivers the winner — asserted end-to-end against a real client, not just server-side; #69 closed; `graphify update .` shows no orphaned sync modules; a sync-applied change is visible to `find_path` without a restart.

### Stage B — Build the safety net
*Gates Stages D and E. The single highest-leverage stage.*

| Work | ADR |
|---|---|
| `inbetweenies/` coverage floor → 80%, enforced per-package in CI | 010 §3 |
| Protocol conformance suite asserting **current v2** behaviour | 010 §2 |
| One uv workspace; `requires-python = ">=3.11"` everywhere; retire `setup.py` | 010 §6 |

**Exit gate:** CI fails on `--cov=inbetweenies --cov-fail-under=80`; the conformance suite passes against today's server and is the artifact Stage D diffs against.

### Stage C — Access layer
*The scalability unlock. Server-only; no client coordination.*

ADR-002 in full (`is_latest` maintained transactionally, `server_seq` watermark, `(id, version desc)` and `(is_latest, updated_at)` indexes, per-id push resolution, paginated pull populating `cursor`). ADR-003 §3's generation tag rides on `server_seq`. Plus the cheap server-side half of ADR-011: one transaction per push batch (§3) and the convergence digest (§4).

**Exit gate:** sync cost is O(changes + page), not O(history × changes); a mid-batch crash leaves nothing applied and nothing acked; digest returned on every response.

**Risk:** medium. One schema migration; both installs controlled; 510 version rows makes backfill trivial.

### Stage D — Domain abstraction, step 1
Type columns become strings; vocabulary moves to a manifest; `domains/house` extracted. ~45 files take a mechanical import change (ADR-012 §1–2, §6.1).

**Exit gate:** the Stage B conformance suite passes **unchanged** against the manifest-driven house domain. That is the whole point of building it first — "byte-identical" is otherwise an unfalsifiable claim.

**Risk:** low intrinsic, large diff. Mitigated entirely by Stage B; attempted before it, this is the riskiest work in the plan rather than the safest.

### Stage E — Temporal core
*The redesign. Highest risk, and the only stage requiring lockstep server + client work.*

ADR-004 (interval edges, structural tombstones, `snapshot(at)`, drop version pins) · ADR-005 (v3 resolution ladder, clamped LWW, wire changes, PROTOCOL.md §7 rewrite) · ADR-009 (client as temporal replica, single store per domain, `at` on every read) · ADR-011 remainder (losers stored as version rows, persisted review queue).

**Exit gate:** conformance suite extended with the ADR-004 snapshot invariants — `snapshot(T)` internally consistent, stable under replay, `diff(T1,T2) ∘ snapshot(T1) = snapshot(T2)` — passing against server, blowing-off and KittenKong.

**Risk:** medium-high, and mostly *coordination* rather than technical. Two client implementations under separate ownership must land compatible changes; the conformance suite is what makes that tractable.

### Stage F — Additive
FTS5 search (ADR-006 §1) and `domains/vehicles` instantiation (ADR-012 §6.3). Low risk, no migration, genuinely optional in ordering.

---

## 3. Deviations from the review's §4 sequencing

Three changes, with reasons.

**3.1 — Phase 0 is redirected, not deleted.** The review's Phase 0 is "pull-guard fix in *both* clients." Per §1.1 the Python client does not have the bug. Doing that work as specified would spend effort where there is no defect while the real one stays live in production.

**3.2 — The conformance suite is a prerequisite, not "ongoing."** ADR-012 §6.1 names it as the gate for byte-identical house behaviour, while ADR-010 lists it under ongoing work. These contradict. It is promoted into Stage B, ahead of the abstraction it is supposed to gate.

**3.3 — Coverage precedes the 45-file refactor.** The review runs the coverage floor in parallel with everything. But the modules the abstraction rewrites are the least-tested in the repo — `graph/traversal.py` 12%, `mcp/tools.py` 15%, `graph/search.py` 16%, `graph/operations.py` 20% (F8). A large mechanical change through untested code is the one avoidable risk here.

**3.4 — ADR-011 §2 (loser-ack) moves from Stage E into Stage A.** Per §1.2 the pull-guard and the loser-ack are one mechanism described in two numbered decisions; separating them across stages produces a livelock in the interval. Only the acknowledgement moves — storing losers as version rows stays in Stage E, where it belongs with the rest of the temporal work. The ADR-011 §4 digest is also a candidate to pull forward into Stage C, since it detects exactly this class of divergence and is cheap and server-side.

*This is a correction to this document's own first draft, not to the review — the review did not make the split.*

Unchanged from the review: the dead-code deletion and GraphIndex fix stay early and cheap; the access layer precedes the temporal model; the temporal model is the core; vehicles comes last.

---

## 4. Open questions for the owner

1. ~~**KittenKong ownership.**~~ Resolved — the guard shipped upstream in `ee4eea5`. Stage A's remaining urgent item (the loser-ack, §1.2) is server-side and in this repository. Ongoing coordination still matters for Stage E, which needs lockstep changes in both clients.
2. **v3 cutover.** Both installs are controlled — hard cutover, or is a v2 compatibility window required? ADR-005 §3 assumes the window can be short; confirming it removes negotiation work.
3. **Is vehicles driving the schedule?** If it is, Stage D moves ahead of Stage C and Stage E stages behind it. If opportunistic, the order above stands.
4. **ADR-006 embeddings have no owner.** Is FTS5-only acceptable indefinitely, or should sqlite-vec be scheduled?
5. **Stage boundaries as releases?** Stages A, C and E each end at a coherent, shippable point. Tagging them keeps the two installs upgradable in steps rather than one large jump.

---

*Related: adrianco/the-goodies#69 (pull-guard) · rolandcanyon-cmd/the-goodies-typescript#2 (updateEntity push) · #3 (sync acks).*
