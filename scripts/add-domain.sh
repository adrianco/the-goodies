#!/usr/bin/env bash
# add-domain.sh -- stand up a second FunkyGibbon domain beside the house (ADR-018).
#
# One process, one database file, one port per domain; auth is shared, so the
# house's client token works on the new endpoint. This writes a start script
# and a launchd agent for the new domain, starts it, and verifies it serves
# the right catalog. It never touches the house service or its database.
#
#   scripts/add-domain.sh --domain vehicles --port 8001
#
# Everything the new process writes -- its database, ./backups, audit.log --
# lives in its own data directory, because the backup scheduler names and
# prunes files relative to the working directory: two domains sharing one
# would prune each other's backups.
#
# Options:
#   --domain NAME          Domain package under domains/ (required), e.g. vehicles.
#   --manifest SPEC        package.module:ATTR (default domains.NAME.manifest:<NAME upper>).
#   --port N               API port for the new domain (default 8001).
#   --host H               Bind address (default: copied from the house start script, else 127.0.0.1).
#   --data-dir DIR         Working directory (default ~/.funkygibbon/NAME).
#   --start-script PATH    House start script to copy JWT_SECRET / ADMIN_PASSWORD_HASH from
#                          (default <repo>/start_funkygibbon.sh).
#   --label LABEL          launchd label (default com.funkygibbon.NAME).
#   --seed-examples        Seed the domain's example data (domains/NAME/seed.py). Default: empty database.
#   --no-launchd           Write the files but do not install or load a launchd agent.
#   --dry-run              Print what would be done and stop.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="" MANIFEST="" PORT=8001 HOST="" DATA_DIR="" START_SCRIPT="" LABEL=""
SEED=0 NO_LAUNCHD=0 DRY_RUN=0

log()  { printf '\n==> %s\n' "$*"; }
warn() { printf '   WARN %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2;;
    --manifest) MANIFEST="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --host) HOST="$2"; shift 2;;
    --data-dir) DATA_DIR="$2"; shift 2;;
    --start-script) START_SCRIPT="$2"; shift 2;;
    --label) LABEL="$2"; shift 2;;
    --seed-examples) SEED=1; shift;;
    --no-launchd) NO_LAUNCHD=1; shift;;
    --dry-run) DRY_RUN=1; shift;;
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    *) die "unknown option: $1";;
  esac
done

[ -n "$DOMAIN" ] || die "--domain is required (e.g. --domain vehicles)"
[ -d "$REPO_DIR/domains/$DOMAIN" ] || die "no such domain package: domains/$DOMAIN"
[ "$PORT" != 8000 ] || die "port 8000 is the house; pick another (default 8001)"
UPPER="$(printf '%s' "$DOMAIN" | tr '[:lower:]' '[:upper:]')"
[ -n "$MANIFEST" ]     || MANIFEST="domains.$DOMAIN.manifest:$UPPER"
[ -n "$DATA_DIR" ]     || DATA_DIR="$HOME/.funkygibbon/$DOMAIN"
[ -n "$START_SCRIPT" ] || START_SCRIPT="$REPO_DIR/start_funkygibbon.sh"
[ -n "$LABEL" ]        || LABEL="com.funkygibbon.$DOMAIN"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DB="$DATA_DIR/$DOMAIN.db"
NEW_START="$DATA_DIR/start_funkygibbon_$DOMAIN.sh"
URL="http://127.0.0.1:$PORT"

if [ -x "$REPO_DIR/venv/bin/python" ]; then PYTHON="$REPO_DIR/venv/bin/python"
elif [ -x "$REPO_DIR/.venv/bin/python" ]; then PYTHON="$REPO_DIR/.venv/bin/python"
else die "no venv in $REPO_DIR -- run this from the server checkout"; fi

[ -f "$START_SCRIPT" ] || die "house start script not found: $START_SCRIPT (pass --start-script)"
grab() { grep -m1 "$1=" "$START_SCRIPT" | sed -E "s/.*$1=[\"']?([^\"']+)[\"']?.*/\1/" || true; }
JWT="$(grab JWT_SECRET)"; HASH="$(grab ADMIN_PASSWORD_HASH)"
[ -n "$JWT" ]  || die "no JWT_SECRET in $START_SCRIPT -- the new domain must share the house's secret"
[ -n "$HASH" ] || warn "no ADMIN_PASSWORD_HASH in $START_SCRIPT; admin login will not work on the new domain (client tokens will)"
[ -n "$HOST" ] || HOST="$(grab API_HOST)"; [ -n "$HOST" ] || HOST="127.0.0.1"

"$PYTHON" -c "import importlib,sys; m,_,a='$MANIFEST'.partition(':'); sys.path.insert(0,'$REPO_DIR'); mf=getattr(importlib.import_module(m),a); print('   manifest:', mf.name, '--', len(mf.entity_types), 'entity types,', len(mf.tools), 'domain tools')" \
  || die "could not load manifest $MANIFEST"

log "Plan"
echo "   domain:        $DOMAIN  ($MANIFEST)"
echo "   endpoint:      $URL  (bind $HOST)"
echo "   data dir:      $DATA_DIR   (database, ./backups, audit.log)"
echo "   database:      $DB  ($([ -f "$DB" ] && echo 'EXISTS -- kept as is' || echo 'new, empty'))"
echo "   start script:  $NEW_START"
echo "   launchd agent: $([ "$NO_LAUNCHD" = 1 ] && echo 'not installed (--no-launchd)' || echo "$PLIST")"
echo "   auth:          JWT_SECRET shared with the house -- existing client tokens work"
[ "$DRY_RUN" = 1 ] && { echo; echo "(dry run; nothing written)"; exit 0; }

log "Writing $NEW_START"
mkdir -p "$DATA_DIR"; chmod 700 "$DATA_DIR"
umask 077
cat > "$NEW_START" <<EOF
#!/usr/bin/env bash
# Generated by scripts/add-domain.sh -- the $DOMAIN domain of FunkyGibbon (ADR-018).
# Holds the JWT secret: mode 700, never commit.
export JWT_SECRET="$JWT"
export ADMIN_PASSWORD_HASH='$HASH'
export DOMAIN_MANIFEST="$MANIFEST"
export DATABASE_URL="sqlite+aiosqlite:///$DB"
export API_HOST="$HOST"
export API_PORT="$PORT"
export PYTHONPATH="$REPO_DIR"
cd "$DATA_DIR"
exec "$PYTHON" -m funkygibbon
EOF
chmod 700 "$NEW_START"

if [ "$SEED" = 1 ] && [ ! -f "$DB" ]; then
  log "Seeding example data"
  [ -f "$REPO_DIR/domains/$DOMAIN/seed.py" ] || die "domains/$DOMAIN/seed.py not found"
  ( cd "$DATA_DIR" && PYTHONPATH="$REPO_DIR" DATABASE_URL="sqlite+aiosqlite:///$DB" "$PYTHON" "$REPO_DIR/domains/$DOMAIN/seed.py" )
fi

if [ "$NO_LAUNCHD" != 1 ]; then
  log "Installing launchd agent $LABEL"
  mkdir -p "$(dirname "$PLIST")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$NEW_START</string></array>
  <key>WorkingDirectory</key><string>$DATA_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DATA_DIR/server.log</string>
  <key>StandardErrorPath</key><string>$DATA_DIR/server.log</string>
</dict></plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
else
  log "Starting in the background (no launchd)"
  nohup /bin/bash "$NEW_START" > "$DATA_DIR/server.log" 2>&1 &
  echo $! > "$DATA_DIR/server.pid"
fi

log "Verifying"
ok=0
for _ in $(seq 1 40); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/health" || true)" = 200 ] && { ok=1; break; }
  sleep 0.5
done
[ "$ok" = 1 ] || die "the $DOMAIN server did not come up on $URL -- see $DATA_DIR/server.log"
echo "   /health -> 200"
code="$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/v1/mcp/tools")"
echo "   unauthenticated /api/v1/mcp/tools -> $code (expect 401/403)"
TOKEN="${FUNKYGIBBON_TOKEN:-$("$PYTHON" -c "import json,os; print(json.load(open(os.path.expanduser('~/.oook/config.json'))).get('auth_token',''))" 2>/dev/null || true)}"
if [ -n "$TOKEN" ]; then
  curl -s "$URL/api/v1/mcp/tools" -H "Authorization: Bearer $TOKEN" | "$PYTHON" -c "
import json,sys
d=json.load(sys.stdin); names=[t['name'] for t in d.get('tools',[])]
if not names: sys.exit('   FAIL the shared client token was refused: %s' % d)
house=[n for n in names if n in ('get_devices_in_room','get_room_connections')]
print('   with the house client token: %d tools%s' % (len(names), '' if not house else '  <-- HOUSE tools present: wrong manifest?'))
"
else
  warn "no client token found (~/.oook/config.json or FUNKYGIBBON_TOKEN); skipped the authenticated check"
fi

log "Done."
echo "   $DOMAIN is serving on $URL. Point a walk at it with:"
echo "     export FUNKYGIBBON_${UPPER}_URL=$URL"
if [ "$NO_LAUNCHD" = 1 ]; then echo "   Stop:   kill \$(cat '$DATA_DIR/server.pid')      Logs: $DATA_DIR/server.log"
else echo "   Stop:   launchctl unload '$PLIST'      Logs: $DATA_DIR/server.log"; fi
echo "   Upgrade with the house (same tag); back up $DB like funkygibbon.db."
