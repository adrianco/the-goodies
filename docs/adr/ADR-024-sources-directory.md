# ADR-024: `sources/` — a well-documented home for device integration tooling

**Status:** Accepted · 2026-09-28 · Implements [ADR-021](ADR-021-clients-and-sources.md) §2
(the sources half) only. ADR-021 §1 (client consolidation), §3 (skills →
`oook.walk`) and §4 (`oook doctor`) remain Proposed and are out of scope here.

## Context

PR #101 (Roland) landed `weather_devices.py` — three device-family read
integrations (Ambient Weather, PurpleAir, Tempest/WeatherFlow) verified
against real hardware — in `domains/house/skills/scripts/`, the only place a
script like it could go. The house skills' README had to carve out a
paragraph explaining it is "a reference, not a skill" sitting among files
that *are* skills' internals (`fg_client.py`, `room_commit.py`,
`room_session.py`). That same README already lists probes that exist and are
explicitly **not** included — a lighting controller, a network controller, a
HomeKit export — "bring your own or skip those steps," because there was no
seam to contribute them through.

ADR-021 diagnosed this precisely (§2, "One contract for sources"): a source —
Home Assistant, UniFi, Vantage, HomeKit, weather devices, the coming MINI
app/OVMS/DVLA-MOT feeds — is a program with one output and a small manifest
of its own, and belongs in `sources/<name>/` when generic, in an install's
fork when site-specific, both plugged the same way. That ADR bundles four
separate decisions (client consolidation, the sources contract, the
skills-scripts package move, one health command) under one Proposed status;
only the sources piece is ready to accept and act on today — the rest is
real but larger work, sequenced independently in ADR-021 itself.

## Decision

### 1. `sources/<name>/` is the one place device/service integration tooling lives

A new top-level directory, sibling to `domains/`, `funkygibbon/`, `oook/`:

```
sources/
  README.md              — the contract every source follows, and a table of what's here
  weather_devices/
    SOURCE.md              — what it is, what domain it feeds, credentials, gotchas
    weather_devices.py     — moved from domains/house/skills/scripts/, unchanged otherwise
```

Migrating `weather_devices.py` here is this ADR's first concrete act, done as
a follow-up commit once this shape exists to move it into.
`domains/house/skills/README.md`'s carve-out paragraph is replaced with a
one-line pointer to `sources/weather_devices/`.

### 2. Every source declares a manifest — data, not a registry the engine loads yet

```python
@dataclass(frozen=True)
class SourceManifest:
    name: str
    domain: str                                    # which domain's graph this source proposes into
    event_kinds: FrozenSet[str]                    # kinds of session-file diffs it can produce
    credentials: Tuple[str, ...] = ()               # Keychain/env accounts it needs (ADR-020 §4)
    writes_direct: FrozenSet[str] = frozenset()     # feed-event kinds exempt from review (ADR-021 §2)
```

`sources/<name>/SOURCE.md` is the manifest today — Markdown, matching every
other README-as-contract in this repo (`domains/house/skills/README.md`'s
environment-variable table is the same idea). The dataclass above is the
shape a later ADR gives `oook doctor` (ADR-021 §4) to check every source's
last successful run without hand-parsing Markdown; declaring the shape now
means the Markdown tables are already written in the fields it will
eventually read from.

### 3. What this ADR does not do

No client is touched, `fg_client.py` is not folded into `oook`, no
session-file/commit-script plumbing changes, and `oook doctor` does not
exist yet. A source in `sources/` still hands its output to a domain's
existing `*_commit.py` review flow exactly as `weather_devices.py` does
today — nothing in it writes to the graph directly. Those remain ADR-021
§1/§3/§4, tracked there, Proposed.

## Consequences

- Roland's and Corfe's next contributions (the MINI app, OVMS, DVLA MOT
  history, the UniFi heuristic from #95, a Vantage probe) have a real, named
  seam — a directory and a `SOURCE.md`, not a judgment call about which
  domain's `skills/scripts/` looks closest.
- `domains/house/skills/` goes back to holding only the room-walk family's
  actual internals; the "reference, not a skill" caveat in its README
  disappears because there is nowhere left for it to apply.
- The manifest is declared but unenforced until ADR-021 §4 lands — a
  `SOURCE.md` that drifts from what its script actually does is caught by a
  human reviewing a PR, same as today, not by a tool. Named as a known gap
  rather than hidden by the dataclass's existence.

## Alternatives considered

- **Leave `weather_devices.py` where PR #101 put it, revisit only when a
  second source arrives** — rejected: a second source is already implied by
  the house README's own "not included" list (#95's UniFi heuristic,
  Roland's Shortcuts launcher per ADR-021), and moving one file now is
  cheaper than moving several later plus updating every reference to it.
- **Accept all of ADR-021 at once** — rejected for scope: §1's client
  consolidation (folding `fg_client.py` into `oook`, KittenKong reading a
  served catalog) is a multi-release migration with its own sequencing
  already laid out in ADR-021's Consequences; bundling it with a directory
  rename would block the part that is ready today.
- **`docs/sources/` instead of a top-level `sources/`** — rejected: sources
  contain runnable scripts and, per `SOURCE.md`, credential documentation,
  not just prose; `domains/` is this repo's precedent for a top-level code
  directory organized by concept rather than by component
  (`funkygibbon`/`oook`/etc.).
