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


# --------------------------------------------------------------------------- #
# ADR-012 §1: the type columns became plain strings.
#
# The trap here is that SQLEnum persisted a member's *name*, not its value, so
# real rows say 'DEVICE' while every other layer says 'device'. The column type
# was translating on every read; with it gone the rows have to be rewritten or
# nothing matches EntityType.DEVICE any more.
# --------------------------------------------------------------------------- #

def _seed_legacy_vocabulary(conn):
    """Rows written the way SQLEnum wrote them: uppercase member names."""
    conn.execute(
        "INSERT INTO entities (id, version, entity_type, name, content, source_type, user_id) "
        "VALUES (?,?,?,?,?,?,?)", ("d1", CANON, "DEVICE", "Lamp", "{}", "HOMEKIT", "agent"))
    conn.execute(
        "INSERT INTO entities (id, version, entity_type, name, content, source_type, user_id) "
        "VALUES (?,?,?,?,?,?,?)", ("r1e", CANON, "ROOM", "Den", "{}", "MANUAL", "agent"))
    conn.execute(
        "INSERT INTO entity_relationships (id, from_entity_id, from_entity_version, "
        "to_entity_id, to_entity_version, relationship_type) VALUES (?,?,?,?,?,?)",
        ("rel-legacy", "d1", CANON, "r1e", CANON, "LOCATED_IN"))
    conn.execute(
        "INSERT INTO blobs (id, name, blob_type, size, sync_status) VALUES (?,?,?,?,?)",
        ("b1", "pic", "JPEG", 3, "UPLOADED"))
    conn.commit()


def test_enum_names_are_rewritten_to_enum_values(conn):
    _seed_legacy_vocabulary(conn)
    run_migration(conn, apply=True)

    assert conn.execute("SELECT entity_type, source_type FROM entities WHERE id='d1'").fetchone() \
        == ("device", "homekit")
    assert conn.execute("SELECT entity_type FROM entities WHERE id='r1e'").fetchone()[0] == "room"
    assert conn.execute(
        "SELECT relationship_type FROM entity_relationships WHERE id='rel-legacy'"
    ).fetchone()[0] == "located_in"
    assert conn.execute("SELECT blob_type FROM blobs WHERE id='b1'").fetchone()[0] == "jpeg"


def test_sync_status_is_left_alone(conn):
    """BlobStatus is still an SQLEnum — engine state, not domain vocabulary.

    It therefore still stores names, and rewriting it would break the one column
    ADR-012 §1 deliberately did not convert.
    """
    _seed_legacy_vocabulary(conn)
    run_migration(conn, apply=True)
    assert conn.execute("SELECT sync_status FROM blobs WHERE id='b1'").fetchone()[0] == "UPLOADED"


def test_normalisation_is_idempotent_and_spares_unknown_vocabulary(conn):
    _seed_legacy_vocabulary(conn)
    first = run_migration(conn, apply=True)
    assert first["type_values_normalised"] > 0

    again = run_migration(conn, apply=True)
    assert again["type_values_normalised"] == 0

    # 'references' is in no enum: a type this build does not know is preserved
    # verbatim rather than guessed at.
    assert conn.execute(
        "SELECT relationship_type FROM entity_relationships WHERE id='r1'"
    ).fetchone()[0] == "references"


def test_dry_run_does_not_rewrite_vocabulary(conn):
    _seed_legacy_vocabulary(conn)
    run_migration(conn, apply=False)
    assert conn.execute("SELECT entity_type FROM entities WHERE id='d1'").fetchone()[0] == "DEVICE"


@pytest.fixture
def constrained_conn():
    """A database whose type columns carry the enum CHECK constraints.

    SQLAlchemy has defaulted to ``Enum(create_constraint=False)`` since 1.4, so
    neither the live database nor a freshly created one has these. A file
    created under 1.3 would, and a surviving CHECK is worse than cosmetic: the
    *database* would reject a second domain's vocabulary no matter what the
    manifest declared.

    Deliberately mixes the two legal placements — inline in the column
    definition (``entities``, ``blobs.sync_status``) and as a table-level clause
    (``entity_relationships``, ``blobs.blob_type``, which is the form SQLAlchemy
    emits) — because handling only one would silently leave the other standing.
    """
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE entities (
            id TEXT NOT NULL, version TEXT NOT NULL,
            entity_type VARCHAR(10) NOT NULL CONSTRAINT entitytype
                CHECK (entity_type IN ('HOME', 'ROOM', 'DEVICE')),
            name TEXT, content JSON,
            source_type VARCHAR(9) NOT NULL CONSTRAINT sourcetype
                CHECK (source_type IN ('HOMEKIT', 'MANUAL')),
            user_id TEXT, parent_versions JSON, created_at TEXT, updated_at TEXT,
            sync_id TEXT, PRIMARY KEY (id, version));
        CREATE INDEX ix_entities_entity_type ON entities (entity_type);
        CREATE TABLE entity_relationships (
            id TEXT PRIMARY KEY, from_entity_id TEXT, from_entity_version TEXT,
            to_entity_id TEXT, to_entity_version TEXT,
            relationship_type VARCHAR(13) NOT NULL,
            CONSTRAINT relationshiptype
                CHECK (relationship_type IN ('LOCATED_IN', 'CONTROLS')),
            CONSTRAINT fk_from_entity FOREIGN KEY (from_entity_id, from_entity_version)
                REFERENCES entities (id, version));
        CREATE TABLE blobs (
            id TEXT PRIMARY KEY, name TEXT,
            blob_type VARCHAR(8) NOT NULL,
            mime_type TEXT, size INTEGER, data BLOB, blob_metadata JSON, checksum TEXT,
            sync_status VARCHAR(16) NOT NULL CONSTRAINT blobstatus
                CHECK (sync_status IN ('PENDING_UPLOAD', 'UPLOADED')),
            server_url TEXT, last_sync_at TEXT, user_id TEXT, summary TEXT,
            created_at TEXT, updated_at TEXT, sync_id TEXT,
            CONSTRAINT blobtype CHECK (blob_type IN ('PDF', 'JPEG')));
        """
    )
    _seed_legacy_vocabulary(c)
    yield c
    c.close()


def _table_sql(conn, table):
    return conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()[0]


def test_vocabulary_check_constraints_are_dropped(constrained_conn):
    conn = constrained_conn
    stats = run_migration(conn, apply=True)
    assert stats["type_checks_dropped"] == 4       # 3 tables, 4 columns

    for table, column in (("entities", "entity_type"), ("entities", "source_type"),
                          ("entity_relationships", "relationship_type"),
                          ("blobs", "blob_type")):
        assert f"{column} IN" not in _table_sql(conn, table)

    # ...but the engine-state constraint stays. That distinction is the point.
    assert "sync_status IN" in _table_sql(conn, "blobs")


def test_dropping_the_check_is_what_lets_a_new_domain_store_its_types(constrained_conn):
    conn = constrained_conn
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO entities (id, version, entity_type, name, content, "
                     "source_type) VALUES ('c1', 'v1', 'car', 'Elan', '{}', 'manual')")
    conn.rollback()

    run_migration(conn, apply=True)

    # The capability ADR-012 §2 needs: the store keeps what a domain declares.
    # The API boundary still rejects it until the manifest exists — that is the
    # right place for the check, and it is not this layer's job.
    conn.execute("INSERT INTO entities (id, version, entity_type, name, content, "
                 "source_type) VALUES ('c1', 'v1', 'car', 'Elan', '{}', 'manual')")
    assert conn.execute("SELECT entity_type FROM entities WHERE id='c1'").fetchone()[0] == "car"


def test_check_removal_preserves_rows_indexes_and_foreign_keys(constrained_conn):
    conn = constrained_conn
    before = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("entities", "entity_relationships", "blobs")}

    run_migration(conn, apply=True)

    after = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in ("entities", "entity_relationships", "blobs")}
    assert after == before

    # The table rebuild must not lose the index the column change promised to keep...
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='ix_entities_entity_type'"
    ).fetchone()[0] == 1
    # ...nor quietly repoint the FK at the temporary table it was rebuilt through.
    assert {row[2] for row in conn.execute("PRAGMA foreign_key_list(entity_relationships)")} \
        == {"entities"}
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_check_removal_is_idempotent(constrained_conn):
    conn = constrained_conn
    run_migration(conn, apply=True)
    assert run_migration(conn, apply=True)["type_checks_dropped"] == 0
