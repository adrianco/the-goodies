"""Synchronous tests for the funkygibbon.migrate data-migration tool.

Builds a tiny in-memory database mirroring the real shapes (doubled-Z versions,
a top-level inline photo, a procedure with a nested images[] list, and a
relationship referencing the old versions), runs the migration, and asserts the
canonical result, referential integrity, and idempotency.
"""

import base64
import json
import sqlite3

import pytest

from funkygibbon.migrate import run_migration, fix_version

OLD = "2026-05-08T07:57:54.734914+00:00Z-000000-agent"      # doubled-Z
CANON = "2026-05-08T07:57:54.734914+00:00-000000-agent"     # expected fix
PHOTO_B64 = base64.b64encode(b"\xff\xd8\xff\xe0 jpeg bytes").decode()


def test_fix_version_strips_doubled_z_and_is_idempotent():
    assert fix_version(OLD) == CANON
    assert fix_version(CANON) == CANON          # idempotent
    assert fix_version(None) is None


def _schema(conn):
    conn.executescript(
        """
        CREATE TABLE entities (
            id TEXT NOT NULL, version TEXT NOT NULL, entity_type TEXT, name TEXT,
            content JSON, source_type TEXT, user_id TEXT, parent_versions JSON,
            created_at TEXT, updated_at TEXT, sync_id TEXT, PRIMARY KEY (id, version));
        CREATE TABLE entity_relationships (
            id TEXT PRIMARY KEY, from_entity_id TEXT, from_entity_version TEXT,
            to_entity_id TEXT, to_entity_version TEXT, relationship_type TEXT);
        CREATE TABLE blobs (
            id TEXT PRIMARY KEY, name TEXT, blob_type TEXT, mime_type TEXT,
            size INTEGER, data BLOB, blob_metadata JSON, checksum TEXT,
            sync_status TEXT, server_url TEXT, last_sync_at TEXT, user_id TEXT,
            summary TEXT, created_at TEXT, updated_at TEXT, sync_id TEXT);
        """
    )


def _seed(conn):
    def ent(eid, content):
        conn.execute(
            "INSERT INTO entities (id, version, entity_type, name, content, source_type, user_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (eid, OLD, "note", eid, json.dumps(content), "manual", "agent"),
        )
    ent("note1", {"is_blob": True, "mime_type": "image/jpeg",
                  "data_b64": PHOTO_B64, "description": "a photo"})
    ent("proc1", {"summary": "do things", "images": [
        {"label": "step 1", "mime_type": "image/jpeg", "source_file": "IMG1.heic", "data_b64": PHOTO_B64},
        {"label": "step 2", "mime_type": "image/jpeg", "source_file": "IMG2.heic", "data_b64": PHOTO_B64},
    ]})
    ent("plain1", {"text": "no photo here"})
    conn.execute(
        "INSERT INTO entity_relationships (id, from_entity_id, from_entity_version, "
        "to_entity_id, to_entity_version, relationship_type) VALUES (?,?,?,?,?,?)",
        ("r1", "note1", OLD, "proc1", OLD, "references"),
    )
    conn.commit()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    _schema(c)
    _seed(c)
    yield c
    c.close()


def test_migration_fixes_versions_and_extracts_all_photo_shapes(conn):
    stats = run_migration(conn, apply=True)

    assert stats["entities"] == 3
    assert stats["versions_fixed"] == 3
    assert stats["photos_extracted"] == 3       # 1 top-level + 2 nested
    assert stats["blobs_created"] == 3
    assert stats["relationship_versions_fixed"] == 1

    # No doubled-Z and no inline base64 anywhere.
    assert conn.execute("SELECT COUNT(*) FROM entities WHERE version LIKE '%+00:00Z-%'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM entities WHERE content LIKE '%data_b64%'").fetchone()[0] == 0

    # Top-level photo now references a blob.
    note = json.loads(conn.execute("SELECT content FROM entities WHERE id='note1'").fetchone()[0])
    assert "data_b64" not in note and note["blob_id"]

    # Nested images each reference a blob, count preserved.
    proc = json.loads(conn.execute("SELECT content FROM entities WHERE id='proc1'").fetchone()[0])
    assert len(proc["images"]) == 2
    assert all("data_b64" not in img and img["blob_id"] for img in proc["images"])

    # Relationship versions were rewritten to the canonical form.
    rel = conn.execute("SELECT from_entity_version, to_entity_version FROM entity_relationships").fetchone()
    assert rel == (CANON, CANON)

    # Referential integrity holds.
    dangling = conn.execute(
        "SELECT COUNT(*) FROM entity_relationships r WHERE NOT EXISTS "
        "(SELECT 1 FROM entities e WHERE e.id=r.from_entity_id AND e.version=r.from_entity_version)"
    ).fetchone()[0]
    assert dangling == 0

    # A blob row is well-formed.
    size, dlen = conn.execute("SELECT size, length(data) FROM blobs LIMIT 1").fetchone()
    assert size == dlen > 0


def test_migration_is_idempotent(conn):
    run_migration(conn, apply=True)
    again = run_migration(conn, apply=True)
    assert again["versions_fixed"] == 0
    assert again["photos_extracted"] == 0
    assert again["blobs_created"] == 0
    assert again["relationship_versions_fixed"] == 0


def test_dry_run_writes_nothing(conn):
    run_migration(conn, apply=False)
    # Still the old doubled-Z versions and inline photos.
    assert conn.execute("SELECT COUNT(*) FROM entities WHERE version LIKE '%+00:00Z-%'").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM blobs").fetchone()[0] == 0
