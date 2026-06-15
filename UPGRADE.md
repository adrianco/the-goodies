# Upgrading a funkygibbon install

This guide upgrades a running **the-goodies / funkygibbon** install to a pinned
release tag. It is written for the person who owns the install, running on the
machine where the server runs. There are two installs to upgrade (this house,
then Roland's); both should use the **same release tag** so they land on
identical code.

## What this release contains

- **Authentication** is now attached to every data endpoint. After upgrading,
  unauthenticated requests are rejected; clients need a token (the upgrade mints
  one and writes it into the client configs).
- **Sync protocol correctness** — canonical version strings, a `server_time`
  delta watermark, deterministic conflict resolution, and tombstone deletes.
- **Backup/restore** with an automated scheduler.
- A **data migration** that rewrites legacy version strings and moves inline
  photos into the blobs table.

## Prerequisites

- A clean git working tree in the repo (`git status` shows nothing to commit).
- Python 3.11+ with `pip`.
- Know how your server is started/stopped (e.g. a launchd agent on macOS). You
  can pass those commands to the script, or run them yourself when prompted.

## One command

```bash
# First-time auth with a real admin password (recommended):
scripts/upgrade.sh --tag vX.Y.Z \
  --admin-password 'choose-a-strong-password' \
  --stop-cmd  "launchctl unload ~/Library/LaunchAgents/funkygibbon.plist" \
  --start-cmd "launchctl load   ~/Library/LaunchAgents/funkygibbon.plist"

# …or trusted local/dev use with explicit test mode instead:
scripts/upgrade.sh --tag vX.Y.Z --test-mode --test-password 'admin' \
  --stop-cmd "…" --start-cmd "…"
```

Add `--dry-run` first to see exactly what it will do without changing anything.
If you omit `--stop-cmd`/`--start-cmd` the script pauses and asks you to stop and
start the service yourself at the right moments.

## What the script does (in order)

1. **Pre-flight** — verifies a clean tree and that the tag exists.
2. **Stop** the server.
3. **Back up** the database file (plus `-wal`/`-shm`) to
   `…/funkygibbon.db.backup-upgrade-<timestamp>`.
4. **Checkout** the release tag.
5. **Install** dependencies from `funkygibbon/requirements.txt`.
6. **Migrate** data — `python -m funkygibbon.migrate --apply` (idempotent; safe
   to re-run; verifies counts before committing).
7. **Set up auth** — `python -m funkygibbon.setup_auth …` generates/persists a
   `JWT_SECRET`, sets the admin credential (or test mode), mints a long-lived
   client token, and writes `~/.oook/config.json` and `./.blowingoff.json`.
8. **Start** the server.
9. **Verify** — unauthenticated `/api/v1/graph/statistics` returns 401/403 and
   `/health` returns 200.

Every step is idempotent; re-running the whole script is safe.

## Doing it by hand (fallback)

```bash
# stop the service first, then:
cp funkygibbon.db funkygibbon.db.backup-upgrade-$(date -u +%Y%m%d-%H%M%S)
git fetch --tags && git checkout vX.Y.Z
python -m pip install -r funkygibbon/requirements.txt
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
