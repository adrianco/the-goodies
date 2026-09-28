#!/usr/bin/env python3
"""
weather_devices.py — generic read access patterns for three weather/air-quality
device families, contributed from a real install (see SOURCE.md next to this
file, and sources/README.md for the contract every source in this directory
follows — ADR-024).

None of this talks to FunkyGibbon directly except to resolve a device's
station/host identity — look that up via fg_client.py's search_entities /
get_entity the way any skill does (this source feeds the house domain), then
pass the resolved value in here. Credentials and hosts are read from
environment variables; nothing here is house-specific.

Three families, three access patterns, three gotchas worth knowing before you
build against them:

AMBIENT WEATHER (cloud REST API)
---------------------------------
`rt.ambientweather.net/v1/devices?applicationKey=...&apiKey=...` — both keys
come from the user's ambientweather.net account (Account -> API Keys), not
from the device itself. Rate limit is ~1 request/second PER API KEY; the API
answers `429 {"error":"above-user-rate-limit"}` the moment another caller
(another skill, a browser tab open on the dashboard) touches the same key in
the same second. Retry with backoff rather than failing outright — a single
shared key across several tools/skills makes this collision routine, not rare.

GOTCHA — sensor labels: the API returns NUMBERED slots (`temp1f`, `temp2f`,
`humidity1`, ...), never the custom names the dashboard shows ("Pool",
"Garage", ...). There is no endpoint that returns the label mapping. Record
your own slot -> name mapping once per install (ask the operator, or read it
off the dashboard) and keep it next to your config — do not guess from
context, and do not assume slot 1 is always "outdoor": ONE real install had
slot 1 as outdoor air and slot 2 as a pool probe, but that is a per-account
custom-sensor assignment, not a protocol guarantee.

TEMPEST / WEATHERFLOW (public station page, browser-driven)
-------------------------------------------------------------
WeatherFlow's official REST API (swd.weatherflow.com) requires a personal
access token tied to a WeatherFlow account and was NOT what we validated here
— if you have that token, prefer it; it is a cleaner integration than what
follows.

What we actually run in production: the station's PUBLIC page at
`https://tempestwx.com/station/<station_id>/` requires no login and renders
current conditions + a multi-day forecast client-side (JavaScript). We drive
it with a browser-automation tool (Playwright in our case) and read the
rendered DOM — there is no stable JSON endpoint behind the page we found.
Resolve `station_id` from your own graph (a `device` entity's content, e.g.
`{"integration": "tempestwx.com", "station_id": "..."}`) rather than
hardcoding it, since a station can be replaced.

PURPLEAIR (local LAN JSON — no cloud dependency)
--------------------------------------------------
A PurpleAir Flex (and most PurpleAir sensors) serve current readings directly
at `http://<device-ip>/json` — no API key, no internet round-trip. Discover
the IP via your network controller (UniFi, pfSense, ...); it is normally
DHCP-assigned, so re-resolve it if the host stops answering rather than
assuming it is static.

GOTCHA — cross-check the two laser channels: the response carries BOTH
`pm2_5_atm` (channel A) and `pm2_5_atm_b` (channel B) from independent laser
counters reading the same air. Treat a wide disagreement between them (this
script flags >2x) as a failing channel, not a real reading — a drifted PM2.5
sensor keeps answering confidently, it just answers wrong, and nothing on the
device tells you that. Corroborating a "trusted" single-channel value against
a regional reference (e.g. Open-Meteo's air-quality API, keyed off the
device's own lat/lon) catches the case where BOTH channels drift together.

GOTCHA — cold-start latency: the device is slow to answer after being idle
(observed 8-25s on a first request). Retry once on failure/timeout before
concluding it is unreachable rather than reporting a false outage.

GOTCHA — do not assume a Node.js `fetch()` (or any JS HTTP client) reaches
this endpoint just because `curl` does. We hit a 100%-reproducible
`EHOSTUNREACH` from Node's fetch/http/net to one specific PurpleAir host,
at every layer, while `curl` to the exact same host:port from the same shell
worked every time (root cause unconfirmed; shelling out to `curl` was the
practical fix). Python's `urllib`/`requests` did not exhibit this — noting it
here in case a JS-based consumer of this same pattern hits the identical
symptom.

Usage (each function is independent and stdlib-only):

    from weather_devices import fetch_ambient_weather, fetch_purpleair_local

    devices = fetch_ambient_weather(api_key, app_key)
    pa = fetch_purpleair_local("10.0.0.140")
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

# --- Ambient Weather ---------------------------------------------------------

AMBIENT_RETRY_DELAYS_S = (1.2, 2.5, 5.0)


def fetch_ambient_weather(api_key: str, app_key: str, timeout_s: int = 20) -> Any:
    """Fetch this account's devices + latest readings. Retries on the API's
    per-key rate limit (429) with backoff; raises on any other failure."""
    url = (
        "https://rt.ambientweather.net/v1/devices"
        f"?applicationKey={urllib.request.quote(app_key)}"
        f"&apiKey={urllib.request.quote(api_key)}"
    )
    for attempt, delay in enumerate((*AMBIENT_RETRY_DELAYS_S, None)):
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and delay is not None:
                time.sleep(delay)
                continue
            body = e.read().decode("utf-8", "replace")[:200]
            hint = " (rate limited — ~1 req/sec per key)" if e.code == 429 else ""
            raise RuntimeError(f"Ambient Weather HTTP {e.code}{hint}: {body}") from e
    raise RuntimeError("unreachable")  # loop always returns or raises above


# --- PurpleAir (local) --------------------------------------------------------

CHANNEL_DISAGREEMENT_RATIO = 2  # A vs B beyond this => one laser channel is failing


def fetch_purpleair_local(host: str, timeout_s: int = 20, retry_once: bool = True) -> Dict[str, Any]:
    """Read a PurpleAir device's local JSON endpoint. Retries once on any
    failure (the device is slow to answer cold) before raising. Returns the
    raw JSON plus a derived `pm25_channels_agree` bool and averaged `pm25`."""

    def _once() -> Dict[str, Any]:
        with urllib.request.urlopen(f"http://{host}/json", timeout=timeout_s) as resp:
            return json.loads(resp.read())

    try:
        j = _once()
    except Exception:
        if not retry_once:
            raise
        j = _once()

    a, b = j.get("pm2_5_atm"), j.get("pm2_5_atm_b")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        lo, hi = min(a, b), max(a, b)
        agree = (hi / lo <= CHANNEL_DISAGREEMENT_RATIO) if lo > 0 else (hi <= 5)
        j["pm25"] = round((a + b) / 2, 1)
        j["pm25_channels_agree"] = agree
    return j


def fetch_reference_pm25(lat: float, lon: float, timeout_s: int = 15) -> Optional[Dict[str, Any]]:
    """Regional PM2.5 reference (Open-Meteo, no key required) for the
    drift/corroboration check described above. Returns None on any failure —
    this is a corroboration signal, never a hard dependency."""
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}&current=pm2_5,us_aqi&timezone=UTC"
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            j = json.loads(resp.read())
        current = j.get("current", {})
        if isinstance(current.get("pm2_5"), (int, float)):
            return {"pm25": current["pm2_5"], "us_aqi": current.get("us_aqi")}
    except Exception:
        pass
    return None


# Tempest/WeatherFlow has no local/no-auth fetch function here on purpose —
# see the module docstring. Drive the public station page with whatever
# browser-automation tool your skill already uses, or use the official
# swd.weatherflow.com API if you hold a personal access token.
