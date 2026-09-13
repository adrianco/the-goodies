# ADR-015: MCP is the client interface; the graph REST API is for maintenance

**Status:** Implemented · 2026-09-13 · Owner decision. Records a rule the code
already mostly obeyed, closes the gaps that let it be broken, and — as of
v0.7.0 — removes the graph REST routes entirely; `oook` moved to the tools.

## Context

Two surfaces can read and write the graph: the MCP tools
(`/api/v1/mcp/tools/<name>` over HTTP, and the same catalog over stdio from
either client's MCP server) and the graph REST routes (`/api/v1/graph/*`).
[docs/mcp.md](../mcp.md) has said "MCP is the interface — not one of two
options" since ADR-013, and the reason was concrete: every gap in the tool
surface was filled by invention, and each invention became a de-facto schema
that took a migration to undo.

Measured on 2026-09-13, the rule was already true of the clients:

- **blowing-off** calls only `/api/v1/sync/`.
- **KittenKong** calls `/api/v1/auth/*`, `/api/v1/mcp/tools/*`, `/api/v1/sync/`.
- **oook** is the only caller of `/api/v1/graph/*`.

But the tool surface could not do everything the REST surface could (issue
#85), which is the condition under which someone routes around it, and the
documentation still listed a `DELETE /api/v1/graph/relationships/{id}` that has
never existed — the phantom route #85's report was built on.

## Decision

1. **MCP is the client interface.** A client — human, agent, skill, script,
   or the two replicas — reads and writes the graph through the tool catalog
   in `inbetweenies/mcp/catalog.py` and nothing else. The sync protocol
   (`/api/v1/sync/`) and authentication (`/api/v1/auth/*`) are protocol
   endpoints, not graph access, and are unaffected.
2. **`/api/v1/graph/*` is a maintenance surface for the local server.** Its
   one client is `oook`, run on the host by an operator. It is not
   advertised, not documented for clients, and not extended for them. It may
   shrink.
3. **Parity is a rule, not an aspiration.** Anything a client needs to do to
   the graph is a tool first. A capability that exists only as a REST route
   is a bug against this ADR. Closed with this decision: `list_relationships`,
   `get_connected`, `end_relationship` (the delete — an ended interval, kept
   as history, per ADR-004), and `get_graph_diff`; and every graph read takes
   `at` (ADR-004 §3, SQL:2011 `AS OF`).
4. **The catalog is the contract.** One definition renders both transports;
   a client's dispatch map that lags the catalog advertises tools it cannot
   run (blowing-off's did — twelve entries against eighteen — and is fixed).
5. **Tests drive tools, not routes.** End-to-end coverage of graph behaviour
   goes through `/api/v1/mcp/tools/<name>`; REST route tests exist only to
   keep `oook` working.

## Consequences

- `docs/mcp.md` is the reference for clients, and no longer lists REST routes
  as an alternative. The phantom `DELETE` is gone from it.
- Twenty-three tools (`list_entities` closed the last REST-only read). `README.md` and `CLAUDE.md` said twelve.
- A future REST removal is a non-event for every client; only `oook` would
  need to move, and it can move to the tools it already uses for half its
  commands.
- ADR-004 §3 is delivered through this surface: `at` on every read,
  `get_graph_diff` for the window form. The persistent GraphIndex still
  caches `at = now`; an as-of read is a query, as §3 specified.

## Alternatives considered

- **Keep both surfaces at parity forever.** Twice the code, twice the tests,
  and the history of this project says the two drift the moment one is not
  exercised. Rejected.
- **Keep the REST routes for `oook`.** Deferred in the first draft of this
  ADR to avoid coupling the removal to the protocol cutover; done one release
  later (v0.7.0) once `oook`'s four commands were moved to tools.
