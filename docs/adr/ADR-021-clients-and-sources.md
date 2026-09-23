# ADR-021: Clients and sources — which clients survive, and one contract for everything that feeds the graph

**Status:** Proposed · 2026-09-23 · The architecture clean-up that ADR-019
makes necessary and that the last two months of field use have been asking
for.

## Context

There are, counting honestly, **five clients** of FunkyGibbon and **six
sources** of data, and they do not share a shape.

Clients: blowing-off (Python reference replica + stdio MCP server), KittenKong
(TypeScript replica + stdio MCP server, the one the walks use), `oook` (local
admin CLI over the tools), `fg_client.py` (the skills' thin HTTP client, in
`domains/house/skills/scripts/`), and `c11s-house-ios` (the phone app, on a
much older protocol). An abandoned Swift port (*WildThing*) exists as a repo.
ADR-019 proposes a sixth, the macOS helper.

Sources — things that produce facts about the house or the cars: the walks
(a person), Home Assistant's REST API, a UniFi controller, a Vantage lighting
probe, a HomeKit export, and the coming feeds (the MINI app, OVMS, DVLA MOT
history). Each is a script of its own shape living wherever it was first
written: some in the skills' `scripts/`, some "site-specific, not included",
some imagined. None of them shares a way of saying "here is what I found;
here is what you should do about it".

The consequences show up in the issues: a room-walk session lost to a stale
build of one client (typescript#4); a sync silently broken for three months
because only one client could have noticed (#100); capabilities living in
one install's fork because there was no seam to contribute them through
(#95); `fg_client.py` re-implementing what oook and blowing-off already do.

## Decision

### 1. Three clients, each with one job

| Client | Job | Keep? |
|---|---|---|
| **KittenKong** (TS) | The replica: local store, sync, offline, stdio MCP for agents and skills | **Yes — the client.** Gains ADR-018 §3 (reads its domain's catalog from the server, so it serves vehicles too). |
| **`oook`** (Python) | Local administration on the server host: stats, verify, token minting, backups, one-off tool calls | **Yes — the operator's CLI.** Absorbs `fg_client.py`'s Python API so the skills import `oook.client` instead of carrying their own. |
| **Ecky-Thump** (Swift, ADR-019) | Apple-framework capabilities on a Mac; a thin tool client, not a replica | **Yes — the system-integration daemon.** |
| blowing-off (Python) | Reference replica; proves PROTOCOL.md is implementable from the text | **Kept as the reference and the conformance harness only** — no new features, no MCP server of its own once KittenKong serves every domain. It stays in the repo because the protocol tests are built on it. |
| `fg_client.py` | Thin HTTP tool client for the skills | **Folded into `oook`** (§1 above). One Python tool client, tested once. |
| `c11s-house-ios` | Phone front end | Out of scope here; it re-targets KittenKong's protocol or the tool API when it is next worked on. |
| WildThing (Swift port) | — | Archived; ADR-019 is the Swift component, and it is deliberately not a replica. |

The rule that falls out: **a replica is TypeScript, a tool client is Python
or Swift, and there is one of each.** A new client is a bug report.

### 2. One contract for sources: a source proposes, a walk commits

Every source — human, network service, Apple framework, feed — produces the
same thing: a **session file** in the skills' existing format (`room_session.py`
/ the vehicle walk's diffs), containing proposed diffs with evidence, and
nothing is written to the graph until a walk reviews it and the user says
`confirm`. This is the room-walk's "local until saved" rule (Corfe, #92)
promoted from one skill to the system's boundary.

```
source (HA / UniFi / Vantage / HomeKit / MINI app / OVMS / MOT / a person)
   └─ proposes ─▶ session file (diffs + evidence)
                      └─ reviewed ─▶ confirm ─▶ *_commit.py ─▶ MCP tools ─▶ graph
```

A source is a program with one output and a small manifest of its own —
what domain it feeds, what event kinds it produces, which credential
(ADR-020 §4) it needs — living in `sources/<name>/` in this repo when it is
generic and in an install's fork when it is site-specific, and **both
plugged in the same way**. Roland's Shortcuts launcher and UniFi heuristic
(#95) are the first two contributed this way instead of as skill edits.

The one exemption is the logbook-granularity **feed event** (ADR-016 §5,
ADR-019 §3): a fact about what happened — an odometer on a date, an
accessory paired, an MOT result — may be written directly as an `event` with
`source_type: imported` or `telemetry`, because a person would not want to
confirm each one. The source's manifest declares which kinds it writes
directly; everything else is a proposal.

### 3. Skills are scripts plus prompt packs, in one place

The skills' shared scripts (`fg_client.py`, `room_session.py`,
`render_review.py`, `image_compress.py`, `room_commit.py`, `vehicle_commit.py`)
move to one package, `oook.walk`, installed with the engine; the `SKILL.md`
files stay with their domains and import from it. The `cp … .claude/scripts/`
install step becomes `oook skills install <domain>` (ADR-018 §4's missing
command), which symlinks the domain's skills into a project and checks the
package is on the path. A skill is then a prompt pack over a tested library,
not a copy of a library.

### 4. One process per domain stands; one health surface

ADR-018's one-process-per-domain topology is unchanged. What is added is a
single place that says whether the whole installation is healthy:
`oook doctor` checks each domain's endpoint, its `--verify`, the replica's
`sync.degraded`, the helper's capability grants, and each source's last
successful run, and prints one table. #100 was three months of a failure
that any one of those checks would have named on day one.

## Consequences

- Fewer things: one replica, one Python tool client, one Swift daemon, one
  session format, one install command, one health command. Each issue in the
  context above had a "there was nothing to catch this" component; this is
  what would have caught them.
- Contributions from the installs (Corfe, Roland) have a seam: a source is a
  directory with a manifest, not a diff to a skill.
- `blowing-off` loses its future but not its present; it remains the
  executable specification of the protocol.
- `c11s-house-ios` is explicitly deferred rather than silently rotting: it is
  named as out of scope with the two options it has.
- Sequencing, so nothing is broken on the way: (1) `oook.walk` absorbs
  `fg_client.py` and the session scripts, skills import from it, `oook
  skills install`; (2) KittenKong reads its catalog (ADR-018 §3); (3) the
  source contract and the first two contributed sources (#95); (4) ADR-019's
  helper as the first Apple source; (5) `oook doctor`. Each step is a
  release; none needs the next.

## Alternatives considered

- **Keep every client and add the helper** — the status quo plus one; rejected
  because five is already the reason things go unnoticed.
- **Make the helper the replica and retire KittenKong** — rejected: KittenKong
  is the tested, field-used client and the phone will want a non-Apple path;
  the helper's value is Apple frameworks, not sync.
- **Sources write directly to the graph** — rejected: it is the pre-#92 world
  (writes invented on the fly, six blob conventions, a rollback bug nobody
  saw). The review step is where the vocabulary stays honest.
- **A plugin API in the server for sources** — rejected: sources run where
  their data is (a Mac for HomeKit, a LAN for UniFi, the cloud for MOT), and
  the tools are already the interface. The server does not need to know a
  source exists.
