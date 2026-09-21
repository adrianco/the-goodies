# Upgrading a funkygibbon install

This guide upgrades a running **the-goodies / funkygibbon** install to a pinned
release tag. It is written for the person who owns the install, running on the
machine where the server runs. There are two installs to upgrade (this house,
then Roland's); both should use the **same release tag** so they land on
identical code.

## ⚠ This release is the `inbetweenies-v3` cutover — read this first

**v0.4.0 was the last `inbetweenies-v2` release.** This one changes the wire
protocol and the edge table, and both changes are hard:

- **A v2 client is rejected with HTTP 400** on `/api/v1/sync/`. There is no
  compatibility window. Stop every client before upgrading the server and do
  not start one again until it is a v3 build. This is the same "do not let an
  old one back in" rule as ADR-013 below, one level stricter: a v2 client does
  not silently damage the graph, it simply cannot sync at all.
- **Edges become immutable interval rows** (ADR-004). The migration rebuilds
  `entity_relationships` with a `(id, valid_from)` primary key, drops the
  `from_entity_version` / `to_entity_version` pins and their foreign keys, and
  backfills `valid_from` from `created_at`. Every existing edge survives as an
  open interval. This step is what was **missing from the v0.4.0 migration**
  (issue #87): on that release the server upgraded cleanly, `--verify` passed,
  and every data endpoint then returned 500 because the model read columns
  the table did not have. `--verify` now compares the live schema against the
  models and fails on that state instead of passing it.
- **Clients:** the Python client (blowing-off, in this repo) is v3. The
  TypeScript client (KittenKong) must be on its matching release before it
  reconnects: **`adrianco/the-goodies-typescript` tag `v0.5.0`** pairs with
  this server's `v0.5.0`.

Upgrading **from v0.4.0** and **from v0.2.2** both work with the one command
below; the migration detects which shape it is starting from.

## v0.8.1 — tombstones end their edges; `--verify` counts what the server counts

**This is the tag both installs should be on.** Additive on v0.8.0; the one
command upgrades, and there is no data migration.

- **Tombstoning an entity ends its open edges** at the same moment (#96), in
  both directions, returned as `ended_relationships`. An edge to something
  that no longer exists was skipped by traversal but still counted as current
  by `get_statistics` and `list_relationships`, so every retraction leaked a
  row into the relationship count. Ended, not deleted: the intervals stay as
  history and `at` still answers. Edges already left open by earlier
  retractions are not touched — end them with `end_relationship` if your
  count has crept.
- **`migrate --verify` prints current counts** (#97) — the same numbers
  `get_statistics` reports — with tombstoned, version-row and ended-interval
  counts beside them.
- **`fg_client_selftest.py` has 24 gates** (#98): it ends its own edges in
  both directions and asserts it left the relationship count where it found it.
- **The vehicles domain is a walk-first capture vocabulary** (ADR-016): one
  open-kind `event` type, US and UK vehicles, `where_is` and
  `get_part_history`. House installs are unaffected.
- ADR-016/017/018 added; ADR-001/009/011 closed out. A server-authored merge
  version carries the winning writer's user id and `content.merged: true`.
- **Matching clients:** KittenKong `adrianco/the-goodies-typescript` **`v0.8.1`**.

## v0.8.0 — domains are pluggable; the vehicles domain; #90/#91 fixed

v0.7.0 refuses two edges the
house vocabulary declares — `device part_of device` (#90, 104 live edges at
Roland) and `device documented_by note` (#91) — and both are fixed here, so
an install whose room walk writes keypad buttons must not stop at v0.7.0
(#94). Additive for a house install otherwise; the one command upgrades from
v0.2.2, v0.4.0, v0.5.0 or v0.7.0. Things a script author may notice:

- **The tool catalog comes from the domain.** `GET /api/v1/mcp/tools` is the
  18 engine tools plus the served domain's own (the house's five, so still 23).
  The `enum` lists on `create_entity` / `create_relationship` /
  `search_entities` / `list_entities` are now generated from the manifest, so
  `contained_in` (deleted in ADR-013) is no longer advertised and `photo` /
  `app` are.
- **Vocabulary is enforced on every write path** (ADR-013 §5 closed): an
  undeclared `entity_type` in a tool call *or a sync push* is a 400 naming the
  declared types; an edge between endpoints the manifest does not permit is
  refused with the rule that refused it.
- **`domains/` is installed with the engine.** The server imports the manifest
  `DOMAIN_MANIFEST` names at runtime; v0.7.0 relied on the checkout being on
  the path. The one command handles it.
- **A second domain: `vehicles`.** `DOMAIN_MANIFEST=domains.vehicles.manifest:VEHICLES`
  with its own `DATABASE_URL` and `API_PORT` runs a vehicles server alongside
  the house; see `domains/vehicles/README.md`. blowing-off honours the same
  variable.
- **Package versions say what is installed.** `pip show funkygibbon` and
  `funkygibbon.__version__` report `0.8.0`; at v0.7.0 they still said 0.4.0
  (#89). `git describe --tags` remains the authority.
- **The verify step probes a live route** (#89): unauthenticated
  `/api/v1/mcp/tools` must be 401/403, and `/api/v1/graph/statistics` must be
  404 — a server still serving graph REST is older than v0.7.0.
- **Matching clients:** KittenKong `adrianco/the-goodies-typescript`
  **`v0.8.1`** — v0.8.0's build output could not be started by `node`
  (typescript#3; `tsx` worked); v0.8.1 fixes the packaging and documents the
  MCP client config shape. It does not yet read the catalog for another
  domain.

## v0.7.0 — the graph REST API is removed; concurrent edits merge

Additive on v0.6.0 for clients; **`oook` must be upgraded with the server**
(it ships in this repo, so the one command does both).

- **`/api/v1/graph/*` is gone.** Every client, including `oook`, uses the MCP
  tools. Nothing else changes for blowing-off or KittenKong — neither ever
  called those routes. If you have a script of your own that did, see
  `docs/mcp.md` for the tool that replaces each route.
- **Concurrent edits are merged** (ADR-005 §2 rungs 2–3): two edits that
  share an ancestor produce a server-authored merge version with both as
  parents — keys changed on one side take that side, `device.capabilities`
  union, `automation.enabled` prefers enabled, and only keys both sides
  changed differently fall to last-write-wins. A blind overwrite (no
  `parent_versions`) is decided whole, as before. Set `DOMAIN_MANIFEST` if the
  server runs a domain other than `domains.house.manifest:HOUSE`.
- `list_entities` tool. Twenty-three tools.
- **Matching clients:** KittenKong `adrianco/the-goodies-typescript` **`v0.7.0`**.

## v0.6.0 — MCP is the client interface (ADR-015)

Additive on top of v0.5.0; the same one command upgrades from v0.2.2, v0.4.0
or v0.5.0.

- **Clients use MCP tools only.** The graph REST routes (`/api/v1/graph/*`)
  are the local maintenance surface for `oook` and nothing else. Both
  replicas already complied; the tool surface now covers everything REST did:
  `list_relationships`, `get_connected`, `end_relationship` (the delete — an
  ended interval, kept as history), `get_graph_diff`, and `at` on every graph
  read (ADR-004 §3 delivered). Twenty-two tools; see `docs/mcp.md`.
- **Edges carry `server_seq`.** The migration adds and backfills it, so a
  cursor delta is one order over entities and edges together. No client
  change is required.
- **Matching clients:** blowing-off is in this repo; KittenKong
  `adrianco/the-goodies-typescript` **`v0.6.0`**.

## What this release contains

- **Authentication** is now attached to every data endpoint. After upgrading,
  unauthenticated requests are rejected; clients need a token (the upgrade mints
  one and writes it into the client configs).
- **Sync protocol correctness** — canonical version strings, a `server_time`
  delta watermark, deterministic conflict resolution, and tombstone deletes.
- **Backup/restore** with an automated scheduler.
- A **data migration** that rewrites legacy version strings, moves inline
  photos into the blobs table, and normalises the type columns (`entity_type`,
  `source_type`, `relationship_type`, `blob_type` stored the enum's *name*,
  `DEVICE`; they now store its value, `device`, matching the wire format).

  That last one is **not optional**. Those columns stopped being database enums
  (ADR-012 §1) and nothing translates on read any more, so a server started
  against an un-migrated database will find no entities of any known type — the
  graph looks empty while the rows sit there intact. Migrate before starting the
  new server.

## This release also cleans up the vocabulary (ADR-013)

On top of the migration above, this release changes what the vocabulary *says*
and fixes two bugs that made writes unreliable.

**Stop the clients before you migrate, and do not let an old one back in.**
This is the one ordering rule that matters. The pre-0.4 TypeScript client
upper-cases every type it sends (`DEVICE`, `LOCATED_IN`). That was harmless
while the database also held uppercase. After the migration the database holds
lowercase, so **one push from an old client writes `DEVICE` alongside `device`**
and splits the graph into two types that nothing joins. The damage is silent and
shows up later as queries that quietly return less than they should.

Upgrade the clients to the matching release before restarting them. **Client
releases live at `adrianco/the-goodies-typescript`** (KittenKong); that is the
canonical repository, and the one an install should track. Use the client
release whose tag matches this server tag. (An earlier revision of this
document pointed at a pull request on a fork, `rolandcanyon-cmd/...`, which
is where that change was first developed; it is not where releases are cut.)

What the migration does, beyond the earlier steps. **The counts are from one
install and are illustrative** -- a different house has a different shape (one
reported zero `part_of` edges). Run `--dry-run` to see your own numbers; do
not read these as expected values.

| Step | Why |
|---|---|
| 48 `part_of room→home` → `located_in` | One word carried two meanings — spatial containment and composition. Now split. |
| 27 blob-carrying notes → `photo` (or `manual` for a PDF) | A JPEG and a walk transcript were the same entity type. |
| `has_blob` → `has_photo` / `documented_by` | The edge never pointed at a blob; it pointed at a note carrying one. |
| Reversed documentation edges flipped | An attachment is not documented *by* the thing it documents. |
| `controlled_by_app` → `manages` (reversed) | They were exact inverses; the app is the actor. |
| Redundant content flags dropped | `is_blob` / `has_blob` restated what the entity type now says. |

### Verify before letting clients back in

```bash
python -m funkygibbon.migrate --db ./funkygibbon.db --verify --domain domains.house.manifest:HOUSE
```

Read-only. It checks every current edge against the vocabulary, confirms no
undeclared entity types, checks blob references for dangling or orphaned rows,
and confirms none of the retired conventions remain. Expect `PASS`.

Run it again after the clients have been reconnected for a while: it is also the
check that catches an old client writing the pre-ADR-013 vocabulary.

### Two write-path bugs fixed at the same time

- **MCP writes were never committed.** Every write through
  `/api/v1/mcp/tools/{name}` was rolled back when the request ended —
  `create_entity` and `create_relationship` reported success and persisted
  nothing. If anything of yours used that endpoint, it has never worked, and
  will start working now.
- **Attachments wrote a null author**, which broke *reads* for any client that
  later pulled the entity.

## Before you start — the checklist from a real upgrade

Distilled from Corfe's v0.2.2 → v0.7.0 field notes (#93) and Roland's v0.8.0
upgrade (#94, #96, #97). Read it before running the script.

1. **Baseline first.** Record what the *server* reports (`get_statistics`:
   current entities and relationships) and the blob count and byte total.
   Every later step is "unchanged from this", never a number from a document.
2. **Stop every client, not just the server** — KittenKong included. A client
   on the old protocol is refused with a 400 after the cutover, which is the
   good outcome.
3. **Back up with the server stopped**, then open the backup read-only and
   re-count. A plain `cp` while the server runs can miss committed WAL data.
4. Check out the tag, install **into the venv the server actually runs**,
   `migrate --apply`, then `migrate --verify --domain domains.house.manifest:HOUSE`.
   `--verify` prints *current* entities and relationships — the same numbers
   `get_statistics` reports — with tombstones, version rows and ended
   intervals beside them, so a difference from your baseline is explained on
   the line that shows it.
5. Start the server; check auth on a live route (`/api/v1/mcp/tools` → 401
   unauthenticated) and that the graph is **served**: call `get_statistics`
   with the minted token. "Healthy + verify PASS" is not "serves data" (#87).
6. Reconnect clients one at a time, then run
   `python3 domains/house/skills/scripts/fg_client_selftest.py` — 24 live
   gates, the last of which asserts it left the relationship count where it
   found it — and re-run `--verify`.

Things that surprise people afterwards: every write is a version and every
delete a tombstone, so the table holds more rows than `get_statistics` counts;
tombstoning an entity **ends its open edges** at the same moment (from
v0.8.1 — before that, end them yourself or the relationship
count creeps); blobs are content-addressed and outlive their photo entity, so
blob bytes only ever grow.

## Prerequisites

- A clean git working tree in the repo (`git status` shows nothing to commit).
- Python 3.11+ with `pip`.
- Know how your server is started/stopped (e.g. a launchd agent on macOS). You
  can pass those commands to the script, or run them yourself when prompted.

## One command

The server runs as the standard macOS launchd LaunchAgent (`com.funkygibbon`),
so the script stops/starts it for you, and `--tag` defaults to the latest
release — so usually you just run:

```bash
scripts/upgrade.sh --dry-run     # preview the latest release, change nothing
scripts/upgrade.sh               # upgrade to the latest release
```

Pin a specific release with `--tag vX.Y.Z` (e.g. to put both installs on the
exact same code).

If this install configures auth for the first time (rather than via the launchd
start script), add one of:

```bash
  --admin-password 'choose-a-strong-password'   # a real admin password
  --test-mode --test-password 'admin'           # explicit local/dev test mode
```

Override the service control only for a non-standard setup:

```bash
  --launchd-label com.something          # different LaunchAgent label
  --launchd-plist /path/to/agent.plist   # explicit plist path
  --stop-cmd "…" --start-cmd "…"         # non-launchd
```

The standard agent is loaded from `~/Library/LaunchAgents/com.funkygibbon.plist`
(created by the house-agent bootstrap, `RunAtLoad`+`KeepAlive`). The script
**unloads** it before migrating so KeepAlive doesn't respawn the old server
mid-upgrade, then **loads** it to bring the new one back.

## What the script does (in order)

1. **Pre-flight** — verifies a clean tree and that the tag exists.
2. **Stop** the server — `launchctl unload` the LaunchAgent (so KeepAlive won't
   respawn the old server while the database is migrated).
3. **Back up** the database file (plus `-wal`/`-shm`) to
   `…/funkygibbon.db.backup-upgrade-<timestamp>`.
4. **Checkout** the release tag.
5. **Install** dependencies — `pip install -e .` from the repo root
   (one uv workspace since v0.3.0; the per-component requirements.txt
   files are gone).
6. **Migrate** data — `python -m funkygibbon.migrate --apply` (idempotent; safe
   to re-run; verifies counts before committing).
7. **Set up auth** — only if you passed `--admin-password`/`--test-mode`:
   `python -m funkygibbon.setup_auth …` generates/persists a `JWT_SECRET`, sets
   the admin credential (or test mode), mints a long-lived client token, and
   writes `~/.oook/config.json` and `./.blowingoff.json`. Skipped by default.
8. **Start** the server — `launchctl load` the LaunchAgent.
9. **Verify** — unauthenticated `/api/v1/mcp/tools` returns 401/403,
   `/api/v1/graph/statistics` returns 404 (the graph REST API is gone since
   v0.7.0), and `/health` returns 200. Then read data through a tool with the
   minted token — `POST /api/v1/mcp/tools/get_statistics` — because "healthy +
   verify PASS" is not the same as "serves data" (#87, #93).

Every step is idempotent; re-running the whole script is safe.

> **Note for installs configured by the house-agent bootstrap:** auth is set in
> the launchd start script's environment (`start_funkygibbon.sh` exports
> `JWT_SECRET` and `ADMIN_PASSWORD_HASH`), not in `.env`. Leave the auth flags
> off — the server keeps its existing credentials. Local clients then need a
> bearer token signed with **that** `JWT_SECRET`. Pass `--mint-client-token` to
> the upgrade (it reads the secret from `start_funkygibbon.sh` and writes the
> client configs), or do it directly:
>
> ```bash
> JWT=$(grep -m1 JWT_SECRET= start_funkygibbon.sh | cut -d'"' -f2)
> python -m funkygibbon.setup_auth --client-token-only --jwt-secret "$JWT"
> ```
>
> This mints a token against the existing secret and writes `~/.oook/config.json`
> + `./.blowingoff.json` without changing any server auth config.

## Doing it by hand (fallback)

```bash
# stop the service first, then:
cp funkygibbon.db funkygibbon.db.backup-upgrade-$(date -u +%Y%m%d-%H%M%S)
git fetch --tags && git checkout vX.Y.Z
python -m pip install -e .
python -m funkygibbon.migrate --apply
python -m funkygibbon.setup_auth --admin-password 'strong-password'
# start the service, then verify:
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/v1/mcp/tools          # 401/403
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/v1/graph/statistics   # 404 since v0.7.0
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/health                     # 200
```

## Reconfiguring clients

`setup_auth` writes the minted token into:
- **oook**: `~/.oook/config.json` (server URL + bearer token)
- **blowing-off**: `./.blowingoff.json`

A mobile app or other client that opens a remote port must send
`Authorization: Bearer <token>` from the same `JWT_SECRET`. Run
`python -m funkygibbon.setup_auth --print-token` to read the token back.

## Rollback

The migration runs in a single transaction and is verified before commit, so a
failed migration leaves the database unchanged. If you need to revert after a
successful upgrade:

1. Stop the server.
2. Restore the backup: `cp funkygibbon.db.backup-upgrade-<timestamp> funkygibbon.db`
   (and the `-wal`/`-shm` copies if present).
3. `git checkout <previous-tag-or-commit>` and reinstall dependencies.
4. Start the server.

To temporarily disable auth for diagnosis, clear `ADMIN_PASSWORD_HASH` and set
`FUNKYGIBBON_TEST_MODE=true` in `.env`, then restart.

## Notes for the second (larger) install

The migration and auth setup are size-independent and idempotent, so the same
command works for Roland's larger database. The pre-commit count check scales
with the data; allow a little more time for the backup copy of a bigger file.
