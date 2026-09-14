# ADR-018: Hosting several domains — separate back ends, shared auth, one catalog per endpoint

**Status:** Accepted · 2026-09-14 · Records how ADR-012 §3 was actually
delivered (one server process per domain) and what remains. Owner direction
2026-09-14: *separate back ends.*

## Context

ADR-012 §3 decided the topology up front — *shared auth/sync/query code ·
separate endpoint · separate database file · separate MCP client per
domain* — and sketched one FastAPI process mounting N domains as
sub-applications at `/{domain}/api/v1/...`. When the vehicles domain was
built (ADR-016) the mount was not needed to satisfy any of the four
properties, so it was not built. This ADR makes that a decision rather than
an omission, and records the pieces of ADR-012 §3 that are still open.

## Decision

### 1. One process per domain, one database file per domain

A domain is served by its own `funkygibbon` process, told which manifest to
load and which file to open:

```bash
DOMAIN_MANIFEST=domains.vehicles.manifest:VEHICLES DATABASE_URL=sqlite+aiosqlite:///./vehicles.db API_PORT=8001 python -m funkygibbon
```

The house is the default (`domains.house.manifest:HOUSE`, `funkygibbon.db`,
8000). Each process advertises exactly its own catalog — the 18 engine tools
plus the domain's declared ones, with `create_entity` / `create_relationship`
listing that domain's vocabulary — and refuses the other's vocabulary with a
400 at both the tool and the sync boundary. Each has its own `server_seq`
timeline, digest, backup file and launchd service. The `/{domain}/` path
prefix of ADR-012 §3 is replaced by the port; nothing a client sees depends
on which.

**Why not the mount.** It saves a process and a port, and costs: one crash
takes both domains down, one backup job must enumerate domains, the app has
to construct N engines / N index services / N settings, and every
`Depends(get_db)` needs to know which domain the request is for. None of that
is hard, but none of it buys a property the two-process form lacks — and the
two-process form is what the upgrade script, the backup scheduler and the
launchd bootstrap already know how to run, once per domain. Revisit if
domains multiply past what a person will configure by hand (say, five), or
if cross-domain dereference (ADR-017 §4) turns out to want an in-process
path rather than an HTTP hop.

### 2. Auth is shared

One JWT secret per host, one admin, one client-token minting
(`setup_auth --client-token-only`); a token minted against the house server
is accepted by the vehicles server, verified. The owner premise is one
operator per host. A per-domain audience claim can be added later without a
protocol change if a domain ever needs distinct access; nothing needs it now.

### 3. A replica picks its domain the same way

blowing-off honours `DOMAIN_MANIFEST` and exposes that domain's catalog
over stdio; its local store validates against the same manifest. A client
that holds both domains runs two replicas (two local databases, two sync
loops against two endpoints, two MCP servers), which is exactly the
*separate MCP client per domain* of the original decision.

KittenKong does not yet do this: it hard-codes the house catalog. The fix is
for it to read `GET /api/v1/mcp/tools` from the server it is pointed at and
serve that, with its local implementations keyed by tool name and the
declared walks executed generically as blowing-off does. Until then KittenKong
is a house client only. Tracked as the last open item of ADR-012 §3.

### 4. Skills travel with the domain

A domain's skills live under `domains/<name>/skills/` and are named in its
manifest (`skills=`), so a client holding a domain can find them without
knowing the repo layout. Installation is still manual (`cp` into a project's
`.claude/skills/`); a `funkygibbon skills install <domain>` command is the
obvious next step and is not built.

### 5. What one host looks like

```
launchd: funkygibbon-house      DOMAIN_MANIFEST=…HOUSE     funkygibbon.db  :8000
launchd: funkygibbon-vehicles   DOMAIN_MANIFEST=…VEHICLES  vehicles.db     :8001
backup scheduler: one per process, one file each
JWT_SECRET: shared; one client token works on both
clients: one replica per domain held
references (ADR-017): an HTTP hop between the two, with the shared token
```

## Consequences

- Adding a domain to a host is: seed its database, add a launchd entry with
  three environment variables, mint nothing (the token is shared). No engine
  change, no config schema.
- Upgrades are per process; both must be on the same release tag, which is
  the rule UPGRADE.md already states for the two installs.
- Cross-domain dereference (ADR-017) is an HTTP call between local processes
  with the shared token, not an in-process read. Slower by a millisecond,
  and the isolation is real rather than by convention.
- The single-process mount remains available as a later optimisation; the
  API shape does not change if it lands.

## Alternatives considered

- **One process mounting N domains** — deferred, not rejected; reasons in §1.
- **One database with a domain column** — rejected in ADR-012 and ADR-017.
- **Per-domain JWT secrets** — rejected for now: one operator per host, and
  the shared token is what makes ADR-017's dereference a one-line HTTP call.
