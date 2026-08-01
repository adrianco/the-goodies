# ADR-012: Domain abstraction — a generic temporal-graph engine, house and garage as domain packages

**Status:** Proposed · 2026-08-01

## Context

Owner direction: the sync/auth/query engine should serve **unrelated domains**. First: the existing smart-home graph. Second: a **car collection** — what's in the garage, the history of each car, issues and service records. Topology decided up front: **shared auth/sync/query code · separate endpoint · separate database file · separate MCP client per domain.** Sequencing decided too: abstract first, get the new code working for house, then instantiate garage.

How deep the house assumptions go today, measured:

- **Schema-level:** `entity_type`, `relationship_type`, and `source_type` are `SQLEnum` columns — HOME/ROOM/DEVICE and located_in/controls are baked into the *database*, so a new domain is currently a schema migration. `EntityType` is imported by 45 files.
- **Tool-level:** of the 12 MCP tools, **7 are already generic** (search/create/update entity, create relationship, find_path, entity details, find_similar) and **5 are house vocabulary** (`get_devices_in_room`, `find_device_controls`, `get_room_connections`, `get_procedures_for_device`, `get_automations_in_room`) — thin graph queries with 18 hardcoded type references.
- **Engine-level: nothing.** Versioning, the temporal model (ADR-004), sync + resolution ladder (ADR-005/011), auth, blobs, graph index/traversal/search, backup — none of it mentions a house. The abstraction is overdue but shallow.

The garage domain is also a validation case: "history of the cars and issues" is *exactly* the as-of machinery — a car's bay changes are interval edges, an issue's lifecycle is version history, `snapshot(T)` answers "what was in the garage in March".

## Decision

### 1. Type columns become strings; vocabulary moves to a domain manifest

`entity_type`, `relationship_type`, `source_type` (and `blob_type`) become plain `String` columns. Validation moves to the API/sync boundary, checked against the **domain manifest** — the engine stores what the domain declares. This simultaneously removes the schema-per-domain problem and the enum-vs-string fragility that e2e4fe5 / PR #62 papered over (`getattr(x, "value", x)` dances disappear: the wire, the store, and the code all speak strings).

### 2. A domain is a small package with a declared shape

```
domains/
  house/    — the current vocabulary + 5 house tools + seed/import scripts
  garage/   — CAR, BAY, SERVICE_RECORD, ISSUE, DOCUMENT, ... (phase 2)
```

A domain declares, via a typed manifest the engine consumes:

- `entity_types`, `relationship_types` (each with allowed endpoint types — e.g. `located_in: CAR→BAY`), `source_types` — validated at write time.
- `mcp_tools`: the domain's query tools. Most are **declarative**: name, description, params, and a generic graph query (type filter + relationship walk + `at` parameter) executed by the engine — `get_devices_in_room` and a future `get_cars_in_bay` are the *same* engine query with different constants. A tool may drop to a Python handler when it genuinely needs logic; the declarative form is preferred because it ports to every client for free.
- `conflict_rules` (optional): the ADR-005 rung-2 registry, now explicitly *supplied by the domain* (union-capabilities and prefer-enabled move into `domains/house`).
- Seed/import scripts (`populate_graph_db.py` becomes `domains/house/seed.py`).

The engine's 7 generic tools ship with the engine and appear in every domain's MCP surface, `at`-parameterized per ADR-009.

### 3. Deployment: one engine process, N mounted domains

One FastAPI process (one launchd service, as today) hosts each configured domain as a sub-application:

- **Routing:** `/{domain}/api/v1/...` and an MCP endpoint per domain (`/{domain}/mcp`) — *separate endpoint, separate MCP client* per the topology decision. Existing house paths stay canonical during transition via a redirect/alias.
- **Storage:** one database file per domain (`house.db`, `garage.db`) — each keeps the single-file backup story (ADR-001/007); the backup/mirror jobs enumerate configured domains.
- **Auth: shared.** One JWT secret, one admin/token system, tokens valid across domains on the instance (owner premise: same operator). A per-domain claim can be added later without a protocol change if a domain ever needs distinct audiences.
- **Sync: the protocol is domain-blind.** Inbetweenies v3 messages gain exactly one field: `domain`. A client syncs each domain it holds against that domain's endpoint into that domain's local database file (ADR-009 replica per domain). Server-side, each domain has its own `server_seq` sequence and digest — domains never share a timeline.
- Config lists the mounted domains; adding one is config + manifest, not engine code.

### 4. Cross-domain references — links by value, never by join

Owner refinement (2026-08-01): query isolation stands, but an entity in one domain may **reference** an entity in another — *"car parts for car X stored in house at location Y."* The mechanism keeps every isolation property:

- **A reference is an ordinary interval edge that lives entirely in the referring domain**, whose remote endpoint is a qualified value: `(domain, entity_id)` plus an optional cached display label. The garage `stored_at` edge from the parts box to `house:⟨room-id⟩` is a garage row in `garage.db` — it syncs on garage's timeline, counts in garage's digest, and obeys garage's snapshot rule for its interval and its *local* endpoint. Nothing about it touches house's database, sequence, or digest.
- **Exactly one endpoint may be external**, and the manifest declares where such edges may point: `stored_at: PART_BOX → external(house: ROOM | note)`. The edge always lives in the domain of its local endpoint.
- **Dereference is an API/MCP-layer act, best-effort by design.** Server-side, both domains are mounted in one process, so resolving `house:⟨id⟩` at time T is a local read of the *other* database's `snapshot(T)`. Client-side, a client holding both replicas (the phone will) resolves locally the same way; a client holding only garage shows the cached label and the qualified id. Unreachable ≠ broken.
- **No cascades, by construction.** Deleting the house room cannot reach into garage. The reference dangles — detected by a periodic integrity sweep that *reports* dangling or type-mismatched external refs (distinct from the intra-domain integrity warning in ADR-004 §3.4, which remains impossible-by-construction). Validation at write time is likewise **soft**: when the target domain is reachable the server checks existence and declared type and warns on mismatch, but never rejects — cross-domain write ordering is not guaranteed and must not deadlock a sync.
- **Reverse lookup** ("what garage items are stored in this room?") is inherently a cross-domain question; it is offered — clearly above the isolation boundary — as an engine MCP tool, `find_references_to(domain, entity_id [, at])`, that scans the *locally mounted/held* domains' reference edges. It reads N local databases; it never crosses the network to a domain the caller doesn't hold.

### 5. What explicitly does NOT change

The temporal model, resolution ladder, ack contract, replica design, auth mechanics, blob handling, and the conformance suite are engine-level and untouched. The conformance suite (ADR-010) runs **per domain manifest** — the same invariants asserted against house and garage prove the abstraction is real rather than aspirational.

### 6. Sequencing (owner-set)

1. **Abstract:** strings-for-enums migration + manifest extraction + `domains/house` package; house behavior byte-identical (the conformance suite is the gate).
2. **Prove:** land the v3/temporal work against house as planned (ADR sequence unchanged).
3. **Instantiate:** `domains/garage` — manifest + seed + a handful of declarative tools (`get_cars_in_bay`, `get_car_history`, `get_open_issues`, `get_service_records`); second database file; second MCP client config.

## Consequences

- New domains become cheap and honest: vocabulary + tools + seeds, no engine changes, no schema migration.
- The 5 house tools likely collapse into declarative definitions, deleting ~300 lines of `tools.py` and its 12–20%-covered hand-rolled query code (helps the ADR-010 coverage goal from the deletion side).
- One process serving N domains concentrates blast radius (a crash takes both down) — accepted at this scale; the mount design leaves per-domain processes available by config if that ever changes.
- Cross-domain **queries** remain out of scope — domains are isolated databases. Cross-domain **references** are supported per §4: links by value in the owning domain, best-effort dereference, soft validation, reported (never cascaded) dangling. The schema cost is two nullable columns on the relationship table (`external_domain`, cached label); domains that never reference outward pay nothing.
- 45 files touching `EntityType` get a mechanical import change in step 1 — large diff, low risk, gated by the suite.

## Alternatives considered

- **Multi-tenant single database (domain column on every row)** — one file again couples backup/restore across domains, complicates per-domain sync sequences and digests, and buys nothing the mount design lacks; rejected against the owner topology (separate files was explicit).
- **Fork the codebase per domain** — two copies of the engine to fix bugs in; the entire review's dead-code section is the cautionary tale.
- **Fully generic vocabulary (no manifest, arbitrary strings)** — maximum flexibility, but typo-tolerant writes silently fragment the graph (`"DEVICE"` vs `"device"` vs `"Device"`); the manifest keeps writes honest while staying data, not schema.
- **Keep enums, add garage members to them** — one shared vocabulary pollutes both domains and makes the *third* domain worse; rejected on arrival.
