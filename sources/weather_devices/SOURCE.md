# weather_devices — Ambient Weather, PurpleAir, Tempest/WeatherFlow

Read-only access patterns for three weather/air-quality device families,
contributed from a real install (Roland, #101). Stdlib-only, no house-specific
values, generic to any install using these device families.

| | |
|---|---|
| **domain** | `house` — readings resolve against a `device` entity looked up via `fg_client.py`, then feed a walk/edit's usual review-then-confirm flow. This module does not write to the graph itself. |
| **event_kinds** | `weather_reading`, `air_quality_reading` — proposed as content on a `device` entity update, or as evidence attached to a walk session; nothing here is a `writes_direct` feed event (ADR-021 §2's exemption does not apply — a reading still goes through review, since a corroboration/drift check can be wrong). |
| **credentials** | `AMBIENT_WEATHER_API_KEY` / `AMBIENT_WEATHER_APP_KEY` (from the account's ambientweather.net API-keys page); PurpleAir and the Open-Meteo reference need none — see ADR-020 §4 for the Keychain-account naming once that lands. |
| **requires** | Python stdlib only (`urllib`, `json`, `time`). A PurpleAir fetch needs LAN reachability to the device; a Tempest/WeatherFlow read needs a browser-automation tool of the caller's choosing (not included here — see the module docstring). |

## Functions

| Function | Family | Notes |
|---|---|---|
| `fetch_ambient_weather(api_key, app_key)` | Ambient Weather | Cloud REST, ~1 req/s per key, retries on 429 with backoff. |
| `fetch_purpleair_local(host)` | PurpleAir | Local LAN `/json`, no key. Retries once (cold-start latency); flags disagreement between its two PM2.5 laser channels. |
| `fetch_reference_pm25(lat, lon)` | (regional reference) | Open-Meteo air-quality API, no key, for corroborating a PurpleAir reading against a regional value. Returns `None` on any failure — never a hard dependency. |

Tempest/WeatherFlow has no fetch function here by design: the production
pattern (driving the station's public page with a browser-automation tool)
is documented in the module docstring rather than implemented, since it
depends on whichever browser-automation tool the calling skill already uses.

Each device family's non-obvious gotcha (Ambient's slot-vs-dashboard-label
mismatch, PurpleAir's dual-channel drift and Node `fetch()` `EHOSTUNREACH`
quirk, cold-start retry) is documented next to the function that hits it in
`weather_devices.py` — read the module docstring before wiring one in.

## Provenance

Contributed from a real install (Roland) in PR #101, 2026-09-27. Verified
live against a real Ambient Weather account and a real PurpleAir Flex before
submitting; Tempest/WeatherFlow's official token-based API was not validated,
only the public-station-page pattern actually running in production.

Moved here from `domains/house/skills/scripts/` by ADR-024, 2026-09-28 — no
functional change, see that ADR for why.
