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
  3. Domain-vocabulary columns (ADR-012 §1): ``entity_type``, ``source_type``,
     ``relationship_type`` and ``blob_type`` stopped being ``SQLEnum`` columns
     and became plain strings. This *does* need a data migration, contrary to
     the obvious guess: SQLAlchemy's ``Enum`` persists a PEP-435 member's
     ``.name``, not its ``.value``, so existing rows hold ``'DEVICE'`` and
     ``'LOCATED_IN'`` while every other layer — the wire format, ``to_dict()``,
     the enum comparisons throughout the code — speaks ``'device'`` and
     ``'located_in'``. The SQLEnum type was silently translating between the two
     on every read and write. Take it away and the rows must be rewritten, or
     the graph goes dark: nothing matches ``EntityType.DEVICE`` any more.
     See ``_normalise_domain_type_values``, and ``_relax_type_column_constraints``
     for the CHECK constraints that would otherwise reject the rewrite (and,
     later, a second domain's vocabulary).

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

    stats.update(_backfill_access_columns(cur))
    # Order matters: the CHECK constraints (where they exist) enumerate the enum
    # *names*, so they would reject the lowercase values the normalisation
    # writes. Drop first, rewrite second.
    stats.update(_relax_type_column_constraints(cur))
    stats.update(_normalise_domain_type_values(cur))

    if apply:
        conn.commit()
    else:
        conn.rollback()
    return stats


def _backfill_access_columns(cur) -> Dict[str, int]:
    """Add and populate is_latest / server_seq on an existing database (ADR-002).

    Idempotent: adds each column only if absent, and recomputes the values from
    the rows themselves, so re-running cannot corrupt an already-migrated file.

    Which row is "latest" is decided here by the greatest version string. That
    is the rule the server used before this column existed, so the backfill
    reproduces the state the database was already being served under rather
    than silently re-deciding history. From now on the value is written by
    conflict resolution, which is the only place that actually knows.
    """
    stats = {"is_latest_set": 0, "server_seq_set": 0}
    existing = {row[1] for row in cur.execute("PRAGMA table_info(entities)").fetchall()}

    if "is_latest" not in existing:
        cur.execute("ALTER TABLE entities ADD COLUMN is_latest BOOLEAN NOT NULL DEFAULT 1")
    if "server_seq" not in existing:
        cur.execute("ALTER TABLE entities ADD COLUMN server_seq INTEGER")

    # is_latest: exactly one per id, the greatest version.
    cur.execute("UPDATE entities SET is_latest = 0")
    cur.execute("""
        UPDATE entities SET is_latest = 1
        WHERE (id, version) IN (SELECT id, MAX(version) FROM entities GROUP BY id)
    """)
    stats["is_latest_set"] = cur.execute(
        "SELECT COUNT(*) FROM entities WHERE is_latest = 1"
    ).fetchone()[0]

    # server_seq: dense, in the closest thing to apply order we can reconstruct
    # (created_at, then version as a tiebreak). Exact ordering of history is
    # unrecoverable after the fact; what matters is that the stamps are unique
    # and monotonic so a client cursor cannot skip or repeat a row.
    rows = cur.execute(
        "SELECT id, version FROM entities ORDER BY created_at, version"
    ).fetchall()
    for seq, (eid, version) in enumerate(rows, start=1):
        cur.execute(
            "UPDATE entities SET server_seq = ? WHERE id = ? AND version = ?",
            (seq, eid, version),
        )
    stats["server_seq_set"] = len(rows)

    # Indexes are created by SQLAlchemy's metadata on a fresh database; add them
    # here for a file that predates them.
    cur.execute("CREATE INDEX IF NOT EXISTS ix_entities_is_latest_server_seq "
                "ON entities (is_latest, server_seq)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_entities_server_seq ON entities (server_seq)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_entities_id_version ON entities (id, version)")

    return stats


# The four domain-vocabulary columns of ADR-012 §1, as {table: (columns,)}.
# Deliberately excludes blobs.sync_status: pending_upload/uploaded is the blob
# transfer state machine, which is engine state and identical in every domain,
# so it stays an SQLEnum and stays constrained.
_DOMAIN_TYPE_COLUMNS = {
    "entities": ("entity_type", "source_type"),
    "entity_relationships": ("relationship_type",),
    "blobs": ("blob_type",),
}


def _split_table_body(body: str):
    """Split a CREATE TABLE body into its top-level comma-separated clauses.

    Commas nested inside parentheses (``CHECK (x IN ('a', 'b'))``, composite FK
    column lists) or inside quotes do not separate clauses, so a plain
    ``body.split(",")`` is wrong. Tracks paren depth and quoting instead.
    """
    clauses, current, depth, quote = [], [], 0, None
    for ch in body:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            clauses.append("".join(current))
            current = []
            continue
        current.append(ch)
    if "".join(current).strip():
        clauses.append("".join(current))
    return clauses


# An optionally-named CHECK: `[CONSTRAINT foo] CHECK` up to its opening paren.
_CHECK_HEAD = re.compile(
    r"(?:CONSTRAINT\s+(?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|\w+)\s+)?CHECK\s*(?=\()",
    re.IGNORECASE,
)
# The column name a column-definition clause starts with, quoted or bare.
_LEADING_NAME = re.compile(r'^\s*(?:"([^"]+)"|`([^`]+)`|\[([^\]]+)\]|(\w+))')


def _matching_paren(text: str, open_at: int) -> int:
    """Index of the ')' closing the '(' at `open_at`, or -1. Quote-aware."""
    depth, quote = 0, None
    for i in range(open_at, len(text)):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _clause_column(clause: str):
    """The column a column-definition clause defines, or None for a constraint."""
    match = _LEADING_NAME.match(clause)
    if not match:
        return None
    name = next(g for g in match.groups() if g is not None)
    if name.upper() in ("CONSTRAINT", "CHECK", "PRIMARY", "FOREIGN", "UNIQUE"):
        return None
    return name


def _strip_checks(clause: str):
    """Remove every CHECK constraint from `clause`; returns (clause, count).

    SQLite accepts a CHECK in two places and this has to handle both: as its own
    table-level clause (what SQLAlchemy emits) and inline inside a column
    definition (legal SQL, and what a hand-written or tool-generated schema may
    contain). Handling only the first would leave the constraint in place while
    reporting success — the worst possible outcome for a migration whose entire
    job is removing it.
    """
    count = 0
    while True:
        match = _CHECK_HEAD.search(clause)
        if not match:
            return clause, count
        close = _matching_paren(clause, clause.index("(", match.end() - 1))
        if close == -1:
            return clause, count      # malformed; leave well alone
        clause = clause[:match.start()] + " " + clause[close + 1:]
        count += 1


def _rebuild_without(cur, table: str, new_sql: str) -> None:
    """Recreate `table` from `new_sql`, preserving every row and index.

    SQLite has no ``ALTER TABLE ... DROP CONSTRAINT``, so removing a CHECK means
    the documented table-rebuild dance. Two details matter:

    * ``legacy_alter_table`` is turned ON for the rename. Modern SQLite helpfully
      rewrites *other* tables' foreign keys to follow a renamed table — which
      here would silently repoint ``entity_relationships``' FKs at the temporary
      table we are about to drop. Legacy mode is what the SQLite documentation
      prescribes for exactly this procedure.
    * Explicit indexes are captured before the rename and recreated after the
      temporary table is dropped; ``DROP TABLE`` takes its indexes with it, and
      recreating them earlier would collide on the index name.
    """
    columns = [row[1] for row in cur.execute(f'PRAGMA table_info("{table}")').fetchall()]
    col_list = ", ".join(f'"{c}"' for c in columns)
    # sql IS NULL for the implicit indexes behind UNIQUE/PRIMARY KEY; those come
    # back on their own with the table definition.
    index_sql = [
        row[0] for row in cur.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? "
            "AND sql IS NOT NULL", (table,)
        ).fetchall()
    ]
    tmp = f"{table}__adr012_old"

    cur.execute("PRAGMA legacy_alter_table = ON")
    try:
        cur.execute(f'ALTER TABLE "{table}" RENAME TO "{tmp}"')
        cur.execute(new_sql)
        cur.execute(f'INSERT INTO "{table}" ({col_list}) SELECT {col_list} FROM "{tmp}"')
        cur.execute(f'DROP TABLE "{tmp}"')
    finally:
        cur.execute("PRAGMA legacy_alter_table = OFF")
    for sql in index_sql:
        cur.execute(sql)


def _relax_type_column_constraints(cur) -> Dict[str, int]:
    """Drop CHECK constraints pinning the domain-vocabulary columns (ADR-012 §1).

    The columns became plain ``String`` so that a new domain is a manifest rather
    than a schema migration. A leftover ``CHECK (entity_type IN ('home', ...))``
    would defeat that entirely: the *database* would reject ``'car'`` no matter
    what the manifest declared, and the failure would surface as an opaque
    IntegrityError on first write.

    On the installs that exist today this is a no-op, and that is a finding
    rather than an assumption: SQLAlchemy has defaulted ``Enum(create_constraint
    =False)`` since 1.4, so both the live ``funkygibbon.db`` and a freshly
    created one declare these columns as bare ``VARCHAR(n)`` with no CHECK — and
    SQLite does not enforce VARCHAR lengths, so the declared width is not a
    barrier either. The function stays because a file created under SQLAlchemy
    1.3 (or by anything that passed ``create_constraint=True``) *would* carry the
    constraint, and it is cheap to be certain rather than hopeful.

    Idempotent: it rebuilds a table only when a matching CHECK is actually
    present, so a second run finds nothing to do.
    """
    stats = {"type_checks_dropped": 0}

    for table, columns in _DOMAIN_TYPE_COLUMNS.items():
        row = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if not row or not row[0]:
            continue  # table absent on this file; nothing to relax
        sql = row[0]

        open_paren = sql.find("(")
        close_paren = sql.rfind(")")
        if open_paren == -1 or close_paren <= open_paren:
            continue
        head, body, tail = sql[:open_paren + 1], sql[open_paren + 1:close_paren], sql[close_paren:]

        kept, dropped = [], 0
        for clause in _split_table_body(body):
            column = _clause_column(clause)
            relevant = (
                column in columns if column is not None
                else any(re.search(rf"\b{re.escape(col)}\b", clause) for col in columns)
            )
            if not relevant:
                kept.append(clause)          # another column, or an unrelated constraint
                continue

            stripped, removed = _strip_checks(clause)
            if not removed:
                kept.append(clause)          # relevant but not a CHECK: a FK, UNIQUE, ...
                continue
            dropped += removed
            if stripped.strip():
                kept.append(stripped)        # column definition minus its inline CHECK
            # else the clause was nothing but a table-level CHECK: drop it whole.

        if not dropped:
            continue

        _rebuild_without(cur, table, head + ",".join(kept) + tail)
        stats["type_checks_dropped"] += dropped

    return stats


def _domain_vocabulary_maps():
    """{(table, column): {ENUM_NAME: enum_value}} for the four ADR-012 columns.

    Derived from the enum classes rather than hardcoded, so the mapping cannot
    drift away from the vocabulary it is translating. Members whose name already
    equals their value contribute nothing and are skipped.
    """
    from inbetweenies.models.blob import BlobType
    from inbetweenies.models.entity import EntityType, SourceType
    from inbetweenies.models.relationship import RelationshipType

    targets = {
        ("entities", "entity_type"): EntityType,
        ("entities", "source_type"): SourceType,
        ("entity_relationships", "relationship_type"): RelationshipType,
        ("blobs", "blob_type"): BlobType,
    }
    return {
        key: {m.name: m.value for m in enum_cls if m.name != m.value}
        for key, enum_cls in targets.items()
    }


def _normalise_domain_type_values(cur) -> Dict[str, int]:
    """Rewrite stored enum *names* to enum *values* (ADR-012 §1).

    ``SQLEnum(EntityType)`` persisted ``EntityType.DEVICE`` as the string
    ``'DEVICE'`` — SQLAlchemy uses a PEP-435 member's ``.name`` — and converted
    it back to the member on read. Everything above the ORM speaks the *value*:
    the wire ``EntityChange.entity_type`` is ``'device'``, ``to_dict()`` emits
    ``.value``, and ``EntityType.DEVICE == 'device'`` is what the comparisons
    throughout the codebase rely on. That gap was invisible only because the
    column type closed it on every read.

    With the column a plain String there is no translator left, so an
    un-migrated row would come back as the literal ``'DEVICE'`` and match
    nothing: every type filter would return empty and the graph would look
    wiped while the rows sat there intact. Hence this runs on every migration.

    Idempotent by construction: names are uppercase, values lowercase, and the
    two sets are disjoint, so an already-migrated row matches no key and is left
    alone. Unrecognised values (a domain type this build has never heard of) are
    likewise left alone rather than being guessed at.

    Note ``blobs.sync_status`` is absent from the mapping. It is still an
    SQLEnum — engine state, not domain vocabulary — so it must keep storing
    names. Rewriting it would break exactly the column this change does not touch.
    """
    stats = {"type_values_normalised": 0}

    for (table, column), name_to_value in _domain_vocabulary_maps().items():
        if not _table_has_column(cur, table, column):
            continue
        for name, value in name_to_value.items():
            cur.execute(
                f'UPDATE "{table}" SET "{column}" = ? WHERE "{column}" = ?',
                (value, name),
            )
            stats["type_values_normalised"] += cur.rowcount

    return stats


def _table_has_column(cur, table: str, column: str) -> bool:
    """True if `table` exists on this file and carries `column`."""
    return any(row[1] == column
               for row in cur.execute(f'PRAGMA table_info("{table}")').fetchall())


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
