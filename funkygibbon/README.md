# FunkyGibbon

The Python backend server for The Goodies — a single-house smart-home **knowledge
graph**. FastAPI + async SQLAlchemy over SQLite, serving a generic
**Entity / Relationship** graph (not a HomeKit Home/Room/Accessory model) with
immutable versioning, the inbetweenies-v2 sync protocol, 12 MCP tools, and
backup/restore.

> The old HomeKit-style REST API documentation has been retired to
> [`../archive/funkygibbon-README-homekit-api.md`](../archive/funkygibbon-README-homekit-api.md).

## Run

```bash
pip install -r funkygibbon/requirements.txt
python -m funkygibbon                 # serves on http://localhost:8000
```

API docs at `/docs`. Health at `/health`.

## Authentication

All data endpoints require a bearer token — only `/health` and `/api/v1/auth/*`
are public. Configure auth (and mint a client token) with:

```bash
python -m funkygibbon.setup_auth --admin-password 'strong-pw'   # or --test-mode
```

- `--admin-password` stores an argon2 hash; `--test-mode` enables an explicit,
  opt-in test password (`FUNKYGIBBON_TEST_MODE`). There is **no** silent default
  password, and the server fails closed if no JWT secret is configured.
- See [`../UPGRADE.md`](../UPGRADE.md) for the full auth/migration story.

## Endpoints (all under `/api/v1`, bearer token required except auth/health)

- **`/graph/*`** — entities & relationships: create/get/list/update, versions,
  search, path-finding, connected/similar, statistics.
- **`/mcp/*`** — list and execute the 12 MCP tools.
- **`/sync/`** — the inbetweenies-v2 sync endpoint (see
  [`../inbetweenies/PROTOCOL.md`](../inbetweenies/PROTOCOL.md)).
- **`/sync-metadata/*`** — per-client sync metadata.
- **`/backup/*`** — create/list/restore/delete backups; scheduler status/trigger.
- **`/auth/*`** — admin login, guest QR, token refresh (public where appropriate).

## Tooling

- `python -m funkygibbon.migrate` — one-time data migration to the canonical
  protocol shape (version strings, inline photos → blobs). Dry-run by default.
- `python -m funkygibbon.setup_auth` — configure auth / mint client tokens.
- `scripts/upgrade.sh` + [`../UPGRADE.md`](../UPGRADE.md) — orchestrated install upgrade.

## Data model

Generic `Entity` (composite key `(id, version)`, immutable, `parent_versions`
DAG) and `EntityRelationship`. Entity types: home, room, device, zone, door,
window, procedure, manual, note, schedule, automation, app. Deletes are
**tombstones** (a new version with `content.deleted = true`).

## Tests

```bash
PYTHONPATH=inbetweenies:funkygibbon python -m pytest funkygibbon/tests
```
