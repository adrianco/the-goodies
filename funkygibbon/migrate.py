#!/usr/bin/env python3
"""
FunkyGibbon - data migration to the canonical inbetweenies-v2 shape.

Run as:  python -m funkygibbon.migrate [--db PATH] [--apply]

Brings an existing knowledge-graph database into line with PROTOCOL.md:

  1. Version strings: strip the legacy doubled ``Z`` (e.g.
     ``...+00:00Z-000000-agent`` -> ``...+00:00-000000-agent``). The same
     transform is applied to entity rows and to the version references on
     relationships, so the graph stays internally consistent.
  2. Inline photos: entity content carrying a base64 ``data_b64`` blob is moved
     into the ``blobs`` table (decoded, sized, SHA-256 checksummed) and the
     content is rewritten to reference the blob by id instead of inlining it.

Safe by design: **dry-run by default** (pass ``--apply`` to write), backs up the
database file first, runs in a single transaction, idempotent (re-running is a
no-op), and verifies entity/relationship counts are unchanged before committing.

Intended to be run once per install (this user's, then Roland's) as part of the
upgrade. See UPGRADE.md.
"""

import argparse
import base64
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

# A stray Z immediately after a ±HH:MM UTC offset is the doubled-Z bug.
_DOUBLED_Z = re.compile(r"([+-]\d{2}:\d{2})Z")

_MIME_TO_BLOB_TYPE = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "application/pdf": "pdf",
}


def fix_version(version: Optional[str]) -> Optional[str]:
    """Remove a doubled trailing-Z from a version string (idempotent)."""
    if not version:
        return version
    return _DOUBLED_Z.sub(r"\1", version)


def resolve_db_path(arg_db: Optional[str]) -> Path:
    """Resolve the SQLite file path from --db or settings.database_url."""
    if arg_db:
        return Path(arg_db)
    try:
        from funkygibbon.config import settings
        url = settings.database_url
    except Exception:
        url = "sqlite+aiosqlite:///./funkygibbon.db"
    # sqlite+aiosqlite:///./funkygibbon.db  ->  ./funkygibbon.db
    path = url.split(":///", 1)[1] if ":///" in url else "./funkygibbon.db"
    return Path(path)


def _blob_type_for(mime: str) -> str:
    return _MIME_TO_BLOB_TYPE.get((mime or "").lower(), "data")


# Fixed namespace so blob ids are deterministic across re-runs (idempotency).
_BLOB_NS = uuid.UUID("6f1b6e2a-9c3d-5e2f-8a1b-0d0e0f000001")


def _insert_blob(cur, blob_id, name, mime, b64, user_id, now, summary) -> bool:
    """Insert a blob row from base64 data. Returns True if a row was created."""
    data = base64.b64decode(b64)
    cur.execute(
        """INSERT OR IGNORE INTO blobs
           (id, name, blob_type, mime_type, size, data, blob_metadata, checksum,
            sync_status, server_url, last_sync_at, user_id, summary,
            created_at, updated_at, sync_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (blob_id, (name or "photo")[:255], _blob_type_for(mime), mime, len(data),
         data, None, hashlib.sha256(data).hexdigest(), "uploaded", None, None,
         user_id, summary, now, now, None),
    )
    return bool(cur.rowcount)


def _extract_photos(cur, eid, name, user_id, content, now) -> Tuple[dict, int, int]:
    """Move any inline base64 photos in `content` into the blobs table.

    Handles two shapes: a top-level ``data_b64`` (notes/manuals) and a nested
    ``images: [{..., data_b64}]`` list (procedures). Returns the rewritten
    content (blob references instead of inline data), the number of photos seen,
    and the number of blob rows newly created. Idempotent: content already
    referencing a blob (no data_b64) is left untouched.
    """
    photos = 0
    blobs_created = 0

    # Top-level inline photo.
    if isinstance(content, dict) and content.get("data_b64"):
        blob_id = str(uuid.uuid5(_BLOB_NS, eid))
        if _insert_blob(cur, blob_id, name, content.get("mime_type", "application/octet-stream"),
                        content["data_b64"], user_id, now, content.get("description")):
            blobs_created += 1
        photos += 1
        content = {k: v for k, v in content.items() if k != "data_b64"}
        content["blob_id"] = blob_id

    # Nested images list.
    if isinstance(content, dict) and isinstance(content.get("images"), list):
        new_images = []
        for idx, image in enumerate(content["images"]):
            if isinstance(image, dict) and image.get("data_b64"):
                key = image.get("source_file") or str(idx)
                blob_id = str(uuid.uuid5(_BLOB_NS, f"{eid}/{key}"))
                if _insert_blob(cur, blob_id, image.get("label") or key,
                                image.get("mime_type", "application/octet-stream"),
                                image["data_b64"], user_id, now, image.get("label")):
                    blobs_created += 1
                photos += 1
                image = {k: v for k, v in image.items() if k != "data_b64"}
                image["blob_id"] = blob_id
            new_images.append(image)
        content = {**content, "images": new_images}

    return content, photos, blobs_created


def run_migration(conn: sqlite3.Connection, *, apply: bool) -> Dict[str, int]:
    """Apply the migration on an open connection. Returns a stats dict.

    When apply is False the work is done in the transaction and rolled back, so
    the stats reflect exactly what --apply would change.
    """
    cur = conn.cursor()
    stats = {
        "entities": 0, "versions_fixed": 0, "photos_extracted": 0,
        "blobs_created": 0, "relationship_versions_fixed": 0,
    }

    entities_before = cur.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    rels_before = cur.execute("SELECT COUNT(*) FROM entity_relationships").fetchone()[0]
    stats["entities"] = entities_before

    now = datetime.now(timezone.utc).isoformat()

    # --- entities: fix version + extract inline photos --------------------- #
    rows = cur.execute(
        "SELECT id, version, name, content, user_id FROM entities"
    ).fetchall()
    for eid, version, name, content_json, user_id in rows:
        new_version = fix_version(version)
        try:
            content = json.loads(content_json) if content_json else {}
        except (ValueError, TypeError):
            content = {}

        original_content_json = json.dumps(content, sort_keys=True) if isinstance(content, dict) else None
        if isinstance(content, dict):
            content, photos, blobs_created = _extract_photos(cur, eid, name, user_id, content, now)
            stats["photos_extracted"] += photos
            stats["blobs_created"] += blobs_created
        content_changed = (
            isinstance(content, dict)
            and json.dumps(content, sort_keys=True) != original_content_json
        )

        if new_version != version or content_changed:
            cur.execute(
                "UPDATE entities SET version = ?, content = ? WHERE id = ? AND version = ?",
                (new_version, json.dumps(content), eid, version),
            )
            if new_version != version:
                stats["versions_fixed"] += 1

    # --- relationships: fix the version references ------------------------- #
    rel_rows = cur.execute(
        "SELECT id, from_entity_version, to_entity_version FROM entity_relationships"
    ).fetchall()
    for rid, from_v, to_v in rel_rows:
        new_from, new_to = fix_version(from_v), fix_version(to_v)
        if new_from != from_v or new_to != to_v:
            cur.execute(
                "UPDATE entity_relationships SET from_entity_version = ?, "
                "to_entity_version = ? WHERE id = ?",
                (new_from, new_to, rid),
            )
            stats["relationship_versions_fixed"] += 1

    # --- verify invariants before committing ------------------------------- #
    entities_after = cur.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    rels_after = cur.execute("SELECT COUNT(*) FROM entity_relationships").fetchone()[0]
    if entities_after != entities_before:
        raise RuntimeError(f"entity count changed {entities_before} -> {entities_after}")
    if rels_after != rels_before:
        raise RuntimeError(f"relationship count changed {rels_before} -> {rels_after}")
    remaining_z = cur.execute(
        "SELECT COUNT(*) FROM entities WHERE version LIKE '%+00:00Z-%'"
    ).fetchone()[0]
    remaining_inline = cur.execute(
        "SELECT COUNT(*) FROM entities WHERE content LIKE '%data_b64%'"
    ).fetchone()[0]
    if remaining_z or remaining_inline:
        raise RuntimeError(
            f"post-migration check failed: {remaining_z} doubled-Z versions, "
            f"{remaining_inline} inline photos remain"
        )

    if apply:
        conn.commit()
    else:
        conn.rollback()
    return stats


def backup_db(db_path: Path) -> Path:
    """Copy the database (and any -wal/-shm) to a timestamped backup."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = db_path.with_name(f"{db_path.name}.backup-premigrate-{stamp}")
    shutil.copy2(db_path, backup)
    for suffix in ("-wal", "-shm"):
        side = db_path.with_name(db_path.name + suffix)
        if side.exists():
            shutil.copy2(side, backup.with_name(backup.name + suffix))
    return backup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m funkygibbon.migrate",
        description="Migrate a FunkyGibbon database to the canonical protocol shape.",
    )
    parser.add_argument("--db", help="Path to the SQLite database (default: from settings).")
    parser.add_argument("--apply", action="store_true",
                        help="Write the changes (default: dry-run).")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip the pre-migration backup (only with --apply).")
    args = parser.parse_args(argv)

    db_path = resolve_db_path(args.db)
    if not db_path.is_file():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        return 1

    print(f"Database: {db_path}")
    print(f"Mode:     {'APPLY' if args.apply else 'dry-run (no changes written)'}")

    if args.apply and not args.no_backup:
        backup = backup_db(db_path)
        print(f"Backup:   {backup}")

    conn = sqlite3.connect(db_path)
    try:
        stats = run_migration(conn, apply=args.apply)
    finally:
        conn.close()

    print("\nResults:")
    for key, value in stats.items():
        print(f"  {key:30s} {value}")
    if not args.apply:
        print("\nDry run — re-run with --apply to write these changes.")
    else:
        print("\nMigration applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
