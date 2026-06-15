# Archive

Historical and superseded documentation, kept for reference only. **None of this
describes the current system** — for that, start at the top-level
[`README.md`](../README.md), the protocol spec
[`inbetweenies/PROTOCOL.md`](../inbetweenies/PROTOCOL.md), and
[`UPGRADE.md`](../UPGRADE.md).

These were moved here during the 2026-06 hardening because they predate the
codebase's pivot (from a HomeKit-style Home/Room/Accessory model to the generic
Entity/Relationship knowledge graph) and the security/sync/MCP work, and so
contradicted the code.

## What's here and why

- **`architecture/`** — the original, pre-pivot design docs. They describe an
  ambitious multi-house distributed system (PostgreSQL/Redis, vector clocks,
  WebSockets), a HomeKit Home/Room/Accessory data model, aspirational security
  (MFA, E2EE, device certs, ABAC) and the abandoned Swift *WildThing* port — most
  of which was never built or was simplified away. The authoritative protocol
  spec now lives in `inbetweenies/PROTOCOL.md`; the implemented security/sync are
  described in the top-level README and PROTOCOL.md.
- **`chat/`** — an experimental local-LLM (TinyLlama / llama-cpp-python) chat
  prototype over the knowledge graph. Not wired into the system, not in the
  default dependencies, and only ever referenced by its own files.
- **`planning-docs/`** — analysis/planning notes for that chat experiment.
- **`funkygibbon-README-homekit-api.md`** — the old funkygibbon README, which
  documented a HomeKit REST API (`/homes`, `/accessories`, …) that no longer
  exists. Replaced by a current `funkygibbon/README.md`.
- **`funkygibbon-PHASE1_IMPLEMENTATION_SUMMARY.md`** — an early phase-1 status
  doc (superseded by `funkygibbon/PHASE2_IMPLEMENTATION_SUMMARY.md` and the code).
- **`funkygibbon-TEST_SUMMARY-stale.md`** — a point-in-time test report with
  counts that no longer match.
- **`blowing-off-IMPLEMENTATION_SUMMARY.md`** — predates the MCP-server addition
  and references the abandoned Swift port.
- **`blowing-off-HUMAN_TESTING-tinyllama.md`** — TinyLlama testing notes for the
  archived chat experiment.
