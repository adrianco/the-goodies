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
  TypeScript client (KittenKong, `adrianco/the-goodies-typescript`) must be on
  its matching v3 release before it reconnects.

Upgrading **from v0.4.0** and **from v0.2.2** both work with the one command
below; the migration detects which shape it is starting from.

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
9. **Verify** — unauthenticated `/api/v1/graph/statistics` returns 401/403 and
   `/health` returns 200.

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
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/v1/graph/statistics   # 401/403
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
