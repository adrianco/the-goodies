# Sources — device and service integration tooling (ADR-024)

A **source** is a program with one output — it produces facts about a house
or a car — and a small manifest of its own: what domain it feeds, what
event kinds it can produce, what credentials it needs. Home Assistant, a
UniFi controller, a Vantage lighting probe, a HomeKit export, weather/air-
quality devices, a car's telemetry feed: each is a source, and each gets a
directory here.

This directory holds the **generic** ones — nothing house- or install-
specific. A source that only makes sense at one install (hardcoded hostnames,
a site's own sensor layout) lives in that install's fork instead, plugged in
exactly the same way. Both are contributions from the field — Roland and
Corfe post issues and PRs against this repo when they have one to share.

## The contract every source follows

1. **One directory, one `SOURCE.md`.** `sources/<name>/SOURCE.md` documents
   what the source is, which domain (`house`, `vehicles`, ...) it feeds, its
   `event_kinds`, the credentials it needs, and any gotchas — see
   `weather_devices/SOURCE.md` for the shape. This is today's manifest; a
   later ADR (ADR-021 §4, `oook doctor`) reads it programmatically via the
   `SourceManifest` shape ADR-024 declares.
2. **A source proposes, a walk commits.** Nothing a source reads is written
   to the graph directly. It produces evidence — a reading, a discovered
   device, an event — that feeds a domain's existing review-then-confirm
   flow (`room_commit.py`, `vehicle_commit.py`, ...) the same way a person's
   own walk does. The one exemption is a logbook-granularity **feed event**
   (an odometer reading, an MOT result) a source's manifest explicitly
   declares as `writes_direct` — see ADR-021 §2. No source here declares one
   yet.
3. **Stdlib-only where practical**, matching the skills-scripts convention
   (`domains/house/skills/scripts/`) these were split out from. A source
   that genuinely needs a dependency (browser automation, a vendor SDK) says
   so in its `SOURCE.md`.
4. **Credentials never in the script or the manifest.** `SOURCE.md` names
   the environment variable or Keychain account (ADR-020 §4); the value
   itself is never committed.

## What's here

| Source | Feeds | What it does |
|---|---|---|
| [`weather_devices`](weather_devices/SOURCE.md) | `house` | Read access for Ambient Weather, PurpleAir and Tempest/WeatherFlow devices. |

## Adding one

```
sources/<name>/
  SOURCE.md        — the manifest (see the contract above)
  <name>.py         — the script(s); stdlib-only unless SOURCE.md says otherwise
```

No registration step exists yet — a source is discovered by a person reading
this table, not loaded by the engine. `oook doctor` (ADR-021 §4, not yet
built) is where that changes.
