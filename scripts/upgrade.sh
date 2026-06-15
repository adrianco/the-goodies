#!/usr/bin/env bash
#
# the-goodies / funkygibbon — install upgrade orchestrator
#
# Upgrades a running install to a pinned release tag in the correct order:
#   stop service -> back up DB -> pull code to the tag -> install deps ->
#   data-migrate -> set up auth -> restart service -> verify.
#
# Designed to be run by the (separate) user that owns the install, on the
# machine where it runs. Idempotent and backup-first. See UPGRADE.md.
#
# Usage:
#   scripts/upgrade.sh --tag vX.Y.Z [options]
#
# Required:
#   --tag TAG              Release tag to upgrade to (both installs use the SAME
#                          tag so they land on identical code).
#
# Auth (choose one; only needed the first time auth is set up):
#   --admin-password PASS  Configure a real admin password.
#   --test-mode            Enable explicit test mode (optionally --test-password).
#   --test-password PASS   Test-mode password (default: admin).
#   (omit both to leave existing auth config untouched)
#
# Service control (how to stop/start the server; omit to be prompted):
#   --stop-cmd  "CMD"      e.g. "launchctl unload ~/Library/LaunchAgents/funkygibbon.plist"
#   --start-cmd "CMD"      e.g. "launchctl load   ~/Library/LaunchAgents/funkygibbon.plist"
#
# Other:
#   --db PATH              Database file (default: from settings / ./funkygibbon.db).
#   --server-url URL       For post-upgrade verification (default http://localhost:8000).
#   --skip-backup          Do not back up the DB (not recommended).
#   --dry-run              Show what would happen; make no changes.
#   --yes                  Don't prompt for confirmation.
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG=""
DB_PATH=""
AUTH_MODE=""            # "" | admin | test
ADMIN_PASSWORD=""
TEST_PASSWORD="admin"
STOP_CMD=""
START_CMD=""
SERVER_URL="http://localhost:8000"
SKIP_BACKUP=0
DRY_RUN=0
ASSUME_YES=0
PYTHON="${PYTHON:-python3}"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY_RUN" = 1 ]; then printf '   [dry-run] %s\n' "$*"; else eval "$*"; fi; }

while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift 2;;
    --db) DB_PATH="$2"; shift 2;;
    --admin-password) AUTH_MODE="admin"; ADMIN_PASSWORD="$2"; shift 2;;
    --test-mode) AUTH_MODE="test"; shift 1;;
    --test-password) TEST_PASSWORD="$2"; shift 2;;
    --stop-cmd) STOP_CMD="$2"; shift 2;;
    --start-cmd) START_CMD="$2"; shift 2;;
    --server-url) SERVER_URL="$2"; shift 2;;
    --skip-backup) SKIP_BACKUP=1; shift 1;;
    --dry-run) DRY_RUN=1; shift 1;;
    --yes) ASSUME_YES=1; shift 1;;
    -h|--help) sed -n '2,40p' "$0"; exit 0;;
    *) die "unknown option: $1";;
  esac
done

[ -n "$TAG" ] || die "--tag is required (the release tag to upgrade to)"
cd "$REPO_DIR"
git rev-parse --git-dir >/dev/null 2>&1 || die "not a git repository: $REPO_DIR"

log "Upgrade plan for $REPO_DIR"
echo "   release tag:   $TAG"
echo "   auth setup:    ${AUTH_MODE:-(leave existing untouched)}"
echo "   service stop:  ${STOP_CMD:-(manual / prompt)}"
echo "   service start: ${START_CMD:-(manual / prompt)}"
echo "   backup DB:     $([ "$SKIP_BACKUP" = 1 ] && echo no || echo yes)"
echo "   dry-run:       $([ "$DRY_RUN" = 1 ] && echo yes || echo no)"

if [ "$ASSUME_YES" != 1 ] && [ "$DRY_RUN" != 1 ]; then
  printf 'Proceed? [y/N] '; read -r reply
  case "$reply" in y|Y|yes) ;; *) die "aborted";; esac
fi

# 0. Pre-flight: clean tree, tag exists ------------------------------------- #
if [ -n "$(git status --porcelain)" ]; then
  die "working tree is not clean — commit/stash local changes first"
fi
run "git fetch --tags --quiet"
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null \
  || die "tag not found after fetch: $TAG"

# 1. Stop the service ------------------------------------------------------- #
log "Stopping the server"
if [ -n "$STOP_CMD" ]; then
  run "$STOP_CMD"
elif [ "$DRY_RUN" != 1 ] && [ "$ASSUME_YES" != 1 ]; then
  printf '   Stop the funkygibbon service now, then press enter... '; read -r _
else
  warn "no --stop-cmd given; ensure the server is stopped"
fi

# 2. Back up the database --------------------------------------------------- #
RESOLVED_DB="$DB_PATH"
if [ -z "$RESOLVED_DB" ]; then
  RESOLVED_DB="$($PYTHON -c "import sys; sys.path.insert(0,'.'); from funkygibbon.migrate import resolve_db_path; print(resolve_db_path(None))" 2>/dev/null || echo "./funkygibbon.db")"
fi
if [ "$SKIP_BACKUP" != 1 ]; then
  if [ -f "$RESOLVED_DB" ]; then
    STAMP="$(date -u +%Y%m%d-%H%M%S)"
    BACKUP="${RESOLVED_DB}.backup-upgrade-${STAMP}"
    log "Backing up database -> $BACKUP"
    run "cp -p '$RESOLVED_DB' '$BACKUP'"
    for sfx in -wal -shm; do
      [ -f "${RESOLVED_DB}${sfx}" ] && run "cp -p '${RESOLVED_DB}${sfx}' '${BACKUP}${sfx}'" || true
    done
  else
    warn "database not found at $RESOLVED_DB — skipping backup (new install?)"
  fi
fi

# 3. Pull code to the pinned tag (fast-forward only) ------------------------ #
log "Checking out release tag $TAG"
run "git checkout --quiet '$TAG'"

# 4. Install/refresh dependencies ------------------------------------------- #
log "Installing dependencies"
run "$PYTHON -m pip install --quiet --upgrade pip"
[ -f funkygibbon/requirements.txt ] && run "$PYTHON -m pip install --quiet -r funkygibbon/requirements.txt"

# 5. Data migration (idempotent; safe to re-run) ---------------------------- #
log "Running data migration"
MIG_ARGS=""
[ -n "$DB_PATH" ] && MIG_ARGS="--db '$DB_PATH'"
if [ "$DRY_RUN" = 1 ]; then
  run "$PYTHON -m funkygibbon.migrate $MIG_ARGS"            # dry-run mode of the tool
else
  run "$PYTHON -m funkygibbon.migrate $MIG_ARGS --apply"
fi

# 6. Auth setup (only if a mode was chosen) --------------------------------- #
if [ -n "$AUTH_MODE" ]; then
  log "Configuring authentication ($AUTH_MODE)"
  if [ "$AUTH_MODE" = "admin" ]; then
    run "$PYTHON -m funkygibbon.setup_auth --admin-password '$ADMIN_PASSWORD' --server-url '$SERVER_URL'"
  else
    run "$PYTHON -m funkygibbon.setup_auth --test-mode --test-password '$TEST_PASSWORD' --server-url '$SERVER_URL'"
  fi
else
  warn "no auth mode chosen; leaving existing auth config untouched"
fi

# 7. Restart the service ---------------------------------------------------- #
log "Starting the server"
if [ -n "$START_CMD" ]; then
  run "$START_CMD"
elif [ "$DRY_RUN" != 1 ] && [ "$ASSUME_YES" != 1 ]; then
  printf '   Start the funkygibbon service now, then press enter... '; read -r _
else
  warn "no --start-cmd given; start the server manually"
fi

# 8. Verify ----------------------------------------------------------------- #
if [ "$DRY_RUN" != 1 ]; then
  log "Verifying"
  sleep 2
  code_unauth="$(curl -s -o /dev/null -w '%{http_code}' "$SERVER_URL/api/v1/graph/statistics" || echo 000)"
  echo "   unauthenticated /graph/statistics -> $code_unauth (expect 401/403)"
  case "$code_unauth" in 401|403) ;; 000) warn "server not reachable at $SERVER_URL";; *) warn "expected 401/403, got $code_unauth";; esac
  health="$(curl -s -o /dev/null -w '%{http_code}' "$SERVER_URL/health" || echo 000)"
  echo "   /health -> $health (expect 200)"
fi

log "Upgrade complete."
echo "If clients (oook / blowing-off) were reconfigured, their tokens are in"
echo "  ~/.oook/config.json and ./.blowingoff.json. Verify a client sync."
