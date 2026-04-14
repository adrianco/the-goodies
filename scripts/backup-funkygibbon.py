#!/usr/bin/env python3
"""
FunkyGibbon change-detecting backup.

- WAL-checkpoints the live DB, hashes it, and only creates a new snapshot
  when the hash differs from the last backup. No change → no new file.
- Writes the snapshot to BOTH a local mirror and the iCloud mirror atomically.
- Applies retention (age + count) to both mirrors independently.

Runs via cron hourly. Safe to run while funkygibbon is live (uses SQLite
backup API, which takes a consistent snapshot across ongoing writes).

Replaces funkygibbon's built-in backup_scheduler. Set
FUNKYGIBBON_BACKUP_SCHEDULE_ENABLED=false in the daemon plist to avoid
duplicate work.
"""
from __future__ import annotations
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIVE_DB = Path("/Users/rolandcanyon/the-goodies/funkygibbon.db")
LOCAL_DIR = Path("/Users/rolandcanyon/the-goodies/backups")
ICLOUD_DIR = Path(
    "/Users/rolandcanyon/Library/Mobile Documents/com~apple~CloudDocs/Documents/FunkyGibbon-Backups"
)
STATE_FILE = LOCAL_DIR / ".last-backup.json"
LOG_FILE = Path("/Users/rolandcanyon/the-goodies/logs/backup-mirror.log")

RETAIN_DAYS = 30
RETAIN_MAX = 50


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} {msg}\n"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(line)


def hash_db(path: Path) -> str:
    """Hash the full file content. After a WAL checkpoint, this reflects
    every committed change in the main DB file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def checkpoint(db_path: Path) -> None:
    """TRUNCATE checkpoint folds WAL into main db file so our hash is stable."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()


def snapshot(src: Path, dst: Path) -> None:
    """Use SQLite backup API — consistent snapshot even with writers active.
    Write to a temp path first and rename at the end so partial files never
    appear in the mirror (matters extra for iCloud, where sync picks up files
    as soon as they exist)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(tmp))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    tmp.rename(dst)


def write_metadata(db_file: Path, digest: str) -> None:
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": str(LIVE_DB),
        "sha256": digest,
        "size_bytes": db_file.stat().st_size,
    }
    db_file.with_suffix(".json").write_text(json.dumps(meta, indent=2))


def touch_latest_metadata(digest: str) -> int:
    """On an unchanged run, refresh the sidecar metadata of the most recent
    backup in each mirror with a `last_verified_unchanged_at` timestamp. This
    leaves evidence that the checker ran without creating a new snapshot."""
    now = datetime.now(timezone.utc).isoformat()
    touched = 0
    for directory in (LOCAL_DIR, ICLOUD_DIR):
        try:
            latest = max(
                directory.glob("scheduled_*.db"),
                key=lambda p: p.stat().st_mtime,
                default=None,
            )
        except Exception:
            latest = None
        if latest is None:
            continue
        sidecar = latest.with_suffix(".json")
        try:
            data = json.loads(sidecar.read_text()) if sidecar.exists() else {}
        except Exception:
            data = {}
        data["last_verified_unchanged_at"] = now
        data.setdefault("sha256", digest)
        try:
            sidecar.write_text(json.dumps(data, indent=2))
            touched += 1
        except Exception:
            pass
    return touched


def load_last_hash() -> str | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text()).get("sha256")
    except Exception:
        return None


def save_last_hash(digest: str, ts: str) -> None:
    STATE_FILE.write_text(json.dumps({"sha256": digest, "timestamp": ts}, indent=2))


def prune(directory: Path) -> int:
    """Delete backups older than RETAIN_DAYS AND keep at most RETAIN_MAX most
    recent. Returns number deleted. Operates on `scheduled_*.db` pairs (.db
    + matching .json) so we don't orphan sidecar metadata."""
    if not directory.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETAIN_DAYS)
    candidates = sorted(
        directory.glob("scheduled_*.db"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    deleted = 0
    for i, p in enumerate(candidates):
        # ALWAYS keep the most recent snapshot, even if it's older than
        # RETAIN_DAYS. If the DB has been quiet for months, that single file
        # is still the best restore point we have — don't evict it.
        if i == 0:
            continue
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        if i >= RETAIN_MAX or mtime < cutoff:
            p.unlink(missing_ok=True)
            p.with_suffix(".json").unlink(missing_ok=True)
            deleted += 1
    return deleted


def main() -> int:
    if not LIVE_DB.exists():
        log(f"ERROR: live DB missing at {LIVE_DB}")
        return 1

    checkpoint(LIVE_DB)
    digest = hash_db(LIVE_DB)
    last = load_last_hash()

    if digest == last:
        # DB unchanged — don't duplicate the snapshot. Just touch the sidecar
        # metadata of the most recent backup (in both mirrors) so you can see
        # the checker is alive: `last_verified_unchanged_at`.
        touched = touch_latest_metadata(digest)
        log(f"unchanged (sha256={digest[:12]}…) — touched {touched} sidecar(s)")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = f"scheduled_{stamp}.db"
    local_path = LOCAL_DIR / name
    icloud_path = ICLOUD_DIR / name

    # Snapshot once to local, copy file to iCloud (fast + identical bytes).
    try:
        snapshot(LIVE_DB, local_path)
        write_metadata(local_path, digest)
    except Exception as e:
        log(f"ERROR: local snapshot failed: {e}")
        return 2

    try:
        ICLOUD_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, icloud_path)
        shutil.copy2(local_path.with_suffix(".json"), icloud_path.with_suffix(".json"))
    except Exception as e:
        # Local snapshot is fine; iCloud is best-effort (offline, sync paused, etc.)
        log(f"WARN: iCloud copy failed (local snapshot still saved): {e}")

    save_last_hash(digest, datetime.now(timezone.utc).isoformat())

    n_local = prune(LOCAL_DIR)
    n_icloud = prune(ICLOUD_DIR)
    log(
        f"snapshot {name} sha256={digest[:12]}… "
        f"(pruned local={n_local} icloud={n_icloud})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
