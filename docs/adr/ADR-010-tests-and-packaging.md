# ADR-010: Test architecture and packaging — real-server standard, cover the shared core, one workspace

**Status:** Proposed · 2026-08-01

## Context

508 tests pass in 36s at 70% coverage — healthy headline, uneven substance:

- **The shared core is the least-tested code:** `inbetweenies/graph/traversal.py` 12%, `inbetweenies/mcp/tools.py` 15%, `graph/search.py` 16%, `graph/operations.py` 20%. This is exactly the code every client (including a future Swift one) depends on or ports.
- **15 mock-based test files** (vs 23 on the excellent v0.3.0 real-server harness), including three overlapping auth suites (`TestAuthManager`, `TestAuthManagerSync`, `TestAuthManagerAsync`); several mostly assert mock wiring.
- **Coverage lies upward** while ADR-008's dead code ships with its own tests.
- **Packaging drift:** `python_requires` disagrees (≥3.8 / ≥3.9 / ≥3.11 across packages); legacy `setup.py` layouts already caused the 2a6284f incident (inbetweenies registering `mcp`/`models`/`sync` as top-level packages, shadowing the real MCP SDK machine-wide). Environment reconstruction for this review needed three attempts to discover the full dependency set.
- The repo carries CI, but no coverage floor per package.

## Decision

**Tests**

1. **The real-server harness is the default.** New integration tests use the root-conftest server fixture; mock-based tests are reserved for error-path unit tests where a real server can't produce the condition.
2. **Protocol conformance suite** — a named test module asserting server behavior against PROTOCOL.md (acks, idempotency, ordering, pagination, tombstones, conflict records as v3 lands). This suite is the compatibility gate for *every* client implementation and the document Swift work trusts. Under ADR-012 it is **parameterized by domain manifest** and runs against each configured domain — the byte-identical-house gate for the abstraction step, and the proof the engine is genuinely domain-blind once garage exists.
3. **Coverage floor on `inbetweenies/` of 80%**, enforced per-package in CI (`--cov=inbetweenies --cov-fail-under=80`); the overall number stops being the metric that matters.
4. **Consolidate the three auth suites into one** parameterized suite; delete tests that only assert mocks were called.
5. `graphify update .` runs in CI post-merge so the knowledge graph (and its dead-code signal) stays fresh.

**Packaging**

6. **One uv workspace** at the repo root: root `pyproject.toml` with workspace members `funkygibbon`, `inbetweenies`, `blowing-off`, `oook`, and the domain packages (`domains/house`, later `domains/garage` — ADR-012); `setup.py` files retired; **`requires-python = ">=3.11"` everywhere** (the deployed interpreter); one lockfile. `pip install -e .` from root produces the complete dev environment in one step.
7. Version pins for cross-package deps expressed as workspace references so inbetweenies can't drift from its consumers.

## Consequences

- The code a mobile port depends on gains a tested contract; protocol changes get caught by the conformance suite instead of by Corfe.
- Env setup becomes one command; the `find_packages()` class of accident is structurally gone.
- Some coverage-number pain up front (deleting dead-code tests and mock tests lowers the headline before the floor raises it honestly).

## Alternatives considered

- **Poetry / plain pip-tools** — workable; uv's workspace model maps cleanest onto the four-package monorepo and is the current ecosystem default.
- **Raise overall coverage floor to 80%** — invites padding tests in easy corners; the per-package floor on the shared core targets the actual risk.
