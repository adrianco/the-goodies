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

from funkygibbon.migrate import run_migration, fix_version, verify_db

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


def _has_column(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall())


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

    # The doubled-Z repair reached the relationship version references too --
    # observable only in the stats, because ADR-004 drops the pin columns at the
    # end of the same migration. Asserted via `relationship_versions_fixed`
    # above; the columns themselves are gone by now:
    assert not _has_column(conn, "entity_relationships", "from_entity_version")
    assert not _has_column(conn, "entity_relationships", "to_entity_version")

    # Referential integrity holds -- by ID now, not by (id, version). The pin
    # was what the old form of this check followed, and following it was the
    # defect: it asked whether an edge still pointed at a version that existed,
    # which stopped being the right question once edges gained intervals.
    dangling = conn.execute(
        "SELECT COUNT(*) FROM entity_relationships r WHERE NOT EXISTS "
        "(SELECT 1 FROM entities e WHERE e.id = r.from_entity_id)"
    ).fetchone()[0]
    assert dangling == 0

    # Every surviving edge came through with a well-formed open interval.
    intervals = conn.execute(
        "SELECT valid_from, valid_to FROM entity_relationships").fetchall()
    assert intervals and all(vf is not None and vt is None for vf, vt in intervals)

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
    # ...nor quietly repoint any FK at a temporary table it was rebuilt through.
    # entity_relationships has no foreign keys at all after ADR-004 §1: they
    # were the composite pins onto (entities.id, entities.version), and an
    # interval edge references entity IDs, resolving versions by time instead.
    # `set()` here is the assertion, not an absence of one -- a stray FK naming
    # a `__old` table is exactly the rebuild bug this test exists to catch.
    assert {row[2] for row in conn.execute("PRAGMA foreign_key_list(entity_relationships)")} \
        == set()
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_check_removal_is_idempotent(constrained_conn):
    conn = constrained_conn
    run_migration(conn, apply=True)
    assert run_migration(conn, apply=True)["type_checks_dropped"] == 0


# --------------------------------------------------------------------------- #
# Blob linking converges on one mechanism (ADR-013 §3)
# --------------------------------------------------------------------------- #

def _seed_blob_shapes(conn):
    """Every way a blob was linked, as found in the live database.

    Six conventions had accumulated: a `has_blob` edge (which pointed at a note,
    never at a blob), top-level `content.blob_id`, nested `content.images[]`,
    a `screenshot_blob_ids` array, and *two* differently-named boolean flags
    saying the same thing.
    """
    def ent(eid, etype, content):
        conn.execute(
            "INSERT INTO entities (id, version, entity_type, name, content, source_type, user_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (eid, CANON, etype, eid, json.dumps(content), "manual", "agent"),
        )

    ent("photo1", "note", {"is_blob": True, "mime_type": "image/jpeg",
                           "filename": "a.jpg", "blob_id": "b-photo"})
    ent("pdf1", "note", {"is_blob": True, "mime_type": "application/pdf",
                         "filename": "manual.pdf", "blob_id": "b-pdf"})
    ent("textnote", "note", {"session_id": "s1", "transcript": "walked the room"})
    ent("probe", "note", {"is_blob": True, "test": True})   # flag but no blob
    ent("dev1", "device", {"has_blob": True, "screenshot_blob_ids": []})
    ent("app1", "app", {"screenshot_blob_ids": ["b-keep"]})  # populated: real data

    for rid, src, dst, rtype in (
        ("hb1", "dev1", "photo1", "has_blob"),
        ("hb2", "dev1", "pdf1", "HAS_BLOB"),   # legacy enum NAME, un-normalised
    ):
        conn.execute(
            "INSERT INTO entity_relationships (id, from_entity_id, from_entity_version, "
            "to_entity_id, to_entity_version, relationship_type) VALUES (?,?,?,?,?,?)",
            (rid, src, CANON, dst, CANON, rtype))
    conn.commit()


def _content(conn, eid):
    return json.loads(conn.execute("SELECT content FROM entities WHERE id=?", (eid,)).fetchone()[0])


def _etype(conn, eid):
    return conn.execute("SELECT entity_type FROM entities WHERE id=?", (eid,)).fetchone()[0]


def test_attachment_notes_become_typed_attachment_entities(conn):
    """The entity type says what kind of document it is, routed by mime.

    A `note` was doing double duty: a walk-session transcript and a JPEG were
    the same type, distinguishable only by which edge happened to point at them.
    """
    _seed_blob_shapes(conn)
    stats = run_migration(conn, apply=True)

    assert _etype(conn, "photo1") == "photo"
    assert _etype(conn, "pdf1") == "manual"      # a PDF is a manual, not a photo
    assert _etype(conn, "textnote") == "note"    # carries no blob: untouched
    assert _etype(conn, "probe") == "note"       # flag but no blob_id: not an attachment
    # note1 comes from the base fixture as an inline data_b64 photo; _extract_photos
    # turns it into a top-level blob_id, so it converges here too -- 3, not 2.
    assert _etype(conn, "note1") == "photo"
    assert stats["notes_retyped_to_photo"] == 3

    # proc1 carries photos NESTED under content.images[]. That shape is not
    # converged: splitting one entity into N photo entities means synthesising
    # ids, versions and edges inside a migration, and there are zero such rows
    # in either live install. It stays an import-time shape -- see ADR-013 3.
    assert _etype(conn, "proc1") == "note"
    assert all("blob_id" in img for img in _content(conn, "proc1")["images"])


def test_has_blob_edges_are_routed_by_what_the_target_turned_out_to_be(conn):
    """A PDF is not a photo, so it must not become a has_photo edge.

    Rewriting every has_blob edge to has_photo produced `room -> manual` in the
    Corfe install, which violates the base rule that has_photo only ever points
    at a photo. A PDF attaches by documented_by -- the relationship that already
    meant this.

    Also pins both spellings: retiring HAS_BLOB from RelationshipType removed the
    only thing that knew how to rewrite rows still storing the enum *name*, so
    'HAS_BLOB' arrives at this step untranslated, and matching only 'has_blob'
    silently reported 0 re-typed while leaving the edges behind.
    """
    _seed_blob_shapes(conn)
    stats = run_migration(conn, apply=True)

    types = dict(conn.execute("SELECT id, relationship_type FROM entity_relationships").fetchall())
    assert types["hb1"] == "has_photo"        # jpeg target
    assert types["hb2"] == "documented_by"    # pdf target, and spelled 'HAS_BLOB'
    assert stats["has_blob_retyped_to_has_photo"] == 1
    assert stats["has_blob_retyped_to_documented_by"] == 1


def test_redundant_blob_flags_are_dropped_but_real_data_is_kept(conn):
    """The type is the flag; a populated array is not a flag."""
    _seed_blob_shapes(conn)
    run_migration(conn, apply=True)

    assert "is_blob" not in _content(conn, "photo1")
    assert _content(conn, "photo1")["blob_id"] == "b-photo"   # the one real link survives
    assert "is_blob" not in _content(conn, "probe")
    assert _content(conn, "dev1") == {}                       # flag + empty array both go
    # A populated screenshot_blob_ids is data, not a restatement of the type.
    # Dropping it would lose blob references with nothing to recover them from.
    assert _content(conn, "app1")["screenshot_blob_ids"] == ["b-keep"]


def test_blob_convergence_is_idempotent(conn):
    _seed_blob_shapes(conn)
    run_migration(conn, apply=True)
    again = run_migration(conn, apply=True)

    assert again["notes_retyped_to_photo"] == 0
    assert again["has_blob_retyped_to_has_photo"] == 0
    assert again["has_blob_retyped_to_documented_by"] == 0
    assert again["documentation_edges_flipped"] == 0
    assert again["blob_flags_dropped"] == 0
    assert _etype(conn, "photo1") == "photo"


def test_migration_refuses_to_finish_with_un_normalised_types(conn):
    """A retired vocabulary member must fail loudly, not silently persist.

    This is the guard for the bug above, generalised: normalisation maps names
    to values using the enums, so anything retired from an enum stops being
    translated and stays in the database as an uppercase name that every type
    filter will miss.
    """
    conn.execute(
        "INSERT INTO entity_relationships (id, from_entity_id, from_entity_version, "
        "to_entity_id, to_entity_version, relationship_type) VALUES (?,?,?,?,?,?)",
        ("rel-retired", "note1", OLD, "proc1", OLD, "RETIRED_TYPE"))
    conn.commit()

    with pytest.raises(RuntimeError, match="un-normalised domain type values"):
        run_migration(conn, apply=True)


def test_the_guard_tolerates_sync_status(conn):
    """blobs.sync_status is engine state and still an SQLEnum: it keeps names.

    Without this the guard would reject every database, since 'UPLOADED' is
    uppercase by design.
    """
    _seed_legacy_vocabulary(conn)
    run_migration(conn, apply=True)   # must not raise
    assert conn.execute("SELECT sync_status FROM blobs WHERE id='b1'").fetchone()[0] == "UPLOADED"


def test_reversed_documentation_edges_are_flipped(conn):
    """An attachment is never documented *by* the thing it documents.

    Corfe has `manual -> device` and `manual -> procedure` alongside correct
    `room -> note` edges in the same database. Nothing rejected either
    direction, so both got written -- ADR-013 §5.
    """
    _seed_blob_shapes(conn)
    conn.execute(
        "INSERT INTO entities (id, version, entity_type, name, content, source_type, user_id) "
        "VALUES (?,?,?,?,?,?,?)", ("dev2", CANON, "device", "Amp", "{}", "manual", "agent"))
    conn.execute(
        "INSERT INTO entity_relationships (id, from_entity_id, from_entity_version, "
        "to_entity_id, to_entity_version, relationship_type) VALUES (?,?,?,?,?,?)",
        ("rev1", "pdf1", CANON, "dev2", CANON, "documented_by"))
    conn.commit()

    stats = run_migration(conn, apply=True)

    row = conn.execute(
        "SELECT from_entity_id, to_entity_id FROM entity_relationships WHERE id='rev1'"
    ).fetchone()
    assert row == ("dev2", "pdf1")          # device -> manual, the readable direction
    assert stats["documentation_edges_flipped"] == 1


def test_correctly_directed_documentation_is_left_alone(conn):
    """The flip must be narrow: it only fires when the *source* is an attachment."""
    _seed_blob_shapes(conn)
    conn.execute(
        "INSERT INTO entity_relationships (id, from_entity_id, from_entity_version, "
        "to_entity_id, to_entity_version, relationship_type) VALUES (?,?,?,?,?,?)",
        ("ok1", "dev1", CANON, "textnote", CANON, "documented_by"))
    conn.commit()

    stats = run_migration(conn, apply=True)

    assert conn.execute(
        "SELECT from_entity_id, to_entity_id FROM entity_relationships WHERE id='ok1'"
    ).fetchone() == ("dev1", "textnote")
    assert stats["documentation_edges_flipped"] == 0


# --------------------------------------------------------------------------- #
# #87 -- the v0.4.0 upgrade path that broke the Corfe install
# --------------------------------------------------------------------------- #
#
# v0.4.0's migrate.py added is_latest/server_seq to `entities` and normalised
# the vocabulary, but never touched `entity_relationships`: the model had
# gained valid_from/valid_to and the table had not. `--verify` checked
# vocabulary only and said PASS; the server then 500'd on every data endpoint.
#
# Corfe's database is therefore in a specific shape, and it is the shape the
# rebuild must be proven against: entities fully v0.4.0-migrated, the edge
# table still exactly v0.2.2 (pins, FKs, single-column PK, NO interval columns).

def _schema_corfe_after_v040_migrate(conn):
    conn.executescript(
        """
        CREATE TABLE entities (
            id VARCHAR(36) NOT NULL, version VARCHAR(255) NOT NULL,
            entity_type VARCHAR NOT NULL, name VARCHAR(255) NOT NULL, content JSON,
            source_type VARCHAR NOT NULL, user_id VARCHAR(36), parent_versions JSON,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, sync_id VARCHAR(36),
            is_latest BOOLEAN NOT NULL DEFAULT 1, server_seq INTEGER,
            PRIMARY KEY (id, version));
        CREATE TABLE entity_relationships (
            id VARCHAR(36) NOT NULL,
            from_entity_id VARCHAR(36) NOT NULL, from_entity_version VARCHAR(255) NOT NULL,
            to_entity_id VARCHAR(36) NOT NULL,   to_entity_version VARCHAR(255) NOT NULL,
            relationship_type VARCHAR NOT NULL, properties JSON, user_id VARCHAR(36),
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, sync_id VARCHAR(36),
            PRIMARY KEY (id),
            CONSTRAINT fk_from_entity FOREIGN KEY(from_entity_id, from_entity_version)
                REFERENCES entities (id, version),
            CONSTRAINT fk_to_entity FOREIGN KEY(to_entity_id, to_entity_version)
                REFERENCES entities (id, version));
        CREATE INDEX ix_entity_relationships_relationship_type
            ON entity_relationships (relationship_type);
        CREATE TABLE blobs (
            id TEXT PRIMARY KEY, name TEXT, blob_type TEXT, mime_type TEXT,
            size INTEGER, data BLOB, blob_metadata JSON, checksum TEXT,
            sync_status TEXT, server_url TEXT, last_sync_at TEXT, user_id TEXT,
            summary TEXT, created_at TEXT, updated_at TEXT, sync_id TEXT);
        """
    )
    now = "2026-09-01T10:00:00+00:00"
    for eid, etype, name in (("dev1", "device", "Lamp"), ("room1", "room", "Kitchen")):
        conn.execute(
            "INSERT INTO entities (id, version, entity_type, name, content, source_type, "
            "user_id, parent_versions, created_at, updated_at, is_latest, server_seq) "
            "VALUES (?,?,?,?,'{}','manual','alice','[]',?,?,1,?)",
            (eid, CANON, etype, name, now, now, 1 if eid == "dev1" else 2),
        )
    conn.execute(
        "INSERT INTO entity_relationships (id, from_entity_id, from_entity_version, "
        "to_entity_id, to_entity_version, relationship_type, properties, user_id, "
        "created_at, updated_at) VALUES ('rel1','dev1',?,'room1',?,'located_in','{}','alice',?,?)",
        (CANON, CANON, "2026-03-01T12:00:00+00:00", now),
    )
    conn.commit()


@pytest.fixture
def corfe_db(tmp_path):
    """On disk, because --verify takes a path."""
    path = tmp_path / "corfe.db"
    c = sqlite3.connect(path)
    _schema_corfe_after_v040_migrate(c)
    yield path, c
    c.close()


def _rel_columns(conn):
    return [row[1] for row in conn.execute("PRAGMA table_info(entity_relationships)")]


def test_verify_refuses_the_corfe_shape_instead_of_passing_it(corfe_db):
    """The exact false PASS from #87: vocabulary fine, schema unservable."""
    path, _ = corfe_db
    assert verify_db(path, "domains.house.manifest:HOUSE") == 1


def test_the_rebuild_takes_corfe_from_v040_to_v3(corfe_db):
    path, conn = corfe_db
    assert "valid_from" not in _rel_columns(conn), "precondition: v0.4.0 never added it"

    stats = run_migration(conn, apply=True)
    assert stats["edges_migrated"] == 1

    cols = _rel_columns(conn)
    assert "valid_from" in cols and "valid_to" in cols
    assert "from_entity_version" not in cols and "to_entity_version" not in cols
    # (id, valid_from) is the key now, and nothing references entity versions.
    pk = [r[1] for r in conn.execute("PRAGMA table_info(entity_relationships)") if r[5]]
    assert sorted(pk) == ["id", "valid_from"]
    assert conn.execute("PRAGMA foreign_key_list(entity_relationships)").fetchall() == []

    # The edge survived with an open interval that starts when it was recorded,
    # not when the migration ran.
    vf, vt = conn.execute(
        "SELECT valid_from, valid_to FROM entity_relationships").fetchone()
    assert vf.startswith("2026-03-01"), vf
    assert vt is None


def test_verify_passes_once_the_rebuild_has_run(corfe_db):
    """And the schema check is what flips it, not the vocabulary check."""
    path, conn = corfe_db
    run_migration(conn, apply=True)
    conn.commit()
    assert verify_db(path, "domains.house.manifest:HOUSE") == 0


def test_verify_fails_on_any_model_column_the_database_lacks(corfe_db):
    """Generic form of #87: a future model column with no migration must fail
    --verify, not pass it and 500 in production."""
    path, conn = corfe_db
    run_migration(conn, apply=True)
    conn.commit()
    # Simulate the drift: drop a mapped column the way SQLite allows.
    conn.execute("ALTER TABLE blobs DROP COLUMN summary")
    conn.commit()
    assert verify_db(path, "domains.house.manifest:HOUSE") == 1
