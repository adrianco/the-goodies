"""Attachments as a first-class operation (ADR-013 §3).

These exist because the absence of these tools was filled by invention: with no
way to attach a photo, callers built an `entity_type=note` holding inline base64
linked by a `has_blob` edge that pointed at the note. That shape spread across
two installs and took a migration to undo. The tests below pin the intended
shape so it cannot drift back.
"""

import base64
import hashlib
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from domains.house.manifest import HOUSE
from funkygibbon.repositories.graph_impl import SQLGraphOperations
from inbetweenies.models import Entity, EntityRelationship, EntityType, SourceType
from inbetweenies.models.base import Base
from inbetweenies.models.blob import Blob

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 64).decode()
PDF = base64.b64encode(b"%PDF-1.4\n" + b"y" * 64).decode()


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def ops(async_session):
    return SQLGraphOperations(async_session)


@pytest_asyncio.fixture
async def device(async_session):
    d = Entity(
        id="dev-1", version=Entity.create_version("t"), entity_type=EntityType.DEVICE,
        name="Marantz Cinema 60", content={}, source_type=SourceType.MANUAL,
        user_id="t", parent_versions=[],
    )
    async_session.add(d)
    await async_session.flush()
    return d


async def _content(session, entity_id):
    e = (await session.execute(
        select(Entity).where(Entity.id == entity_id))).scalars().first()
    return e


class TestAttachPhoto:
    async def test_creates_a_photo_entity_not_a_note(self, ops, device, async_session):
        r = await ops.attach_photo(device.id, "keypad.jpg", PNG,
                                   mime_type="image/png", description="8-button keypad")
        assert r.success, r.error

        photo = await _content(async_session, r.result["attachment_id"])
        assert photo.entity_type == "photo"          # not "note" -- ADR-013 §3
        assert photo.name == "keypad.jpg"

    async def test_the_only_blob_link_is_top_level_blob_id(self, ops, device, async_session):
        r = await ops.attach_photo(device.id, "keypad.jpg", PNG, mime_type="image/png")
        photo = await _content(async_session, r.result["attachment_id"])

        assert photo.content["blob_id"] == r.result["blob_id"]
        # The entity type is the flag. None of the six retired conventions.
        for retired in ("is_blob", "has_blob", "blob_reference",
                        "blob_references", "screenshot_blob_ids", "data_b64"):
            assert retired not in photo.content, f"{retired} came back"

    async def test_bytes_land_in_the_blobs_table(self, ops, device, async_session):
        r = await ops.attach_photo(device.id, "keypad.jpg", PNG, mime_type="image/png")
        blob = await async_session.get(Blob, r.result["blob_id"])

        raw = base64.b64decode(PNG)
        assert blob is not None and blob.data == raw
        assert blob.size == len(raw)
        assert blob.checksum == hashlib.sha256(raw).hexdigest()
        assert blob.blob_type == "png"

    async def test_the_edge_runs_from_the_thing_to_the_photo(self, ops, device, async_session):
        r = await ops.attach_photo(device.id, "keypad.jpg", PNG, mime_type="image/png")
        rel = (await async_session.execute(select(EntityRelationship))).scalars().first()

        # Direction matters: four live edges ran backwards because nothing checked.
        assert rel.from_entity_id == device.id
        assert rel.to_entity_id == r.result["attachment_id"]
        assert rel.relationship_type == "has_photo"

    async def test_the_result_conforms_to_the_manifest(self, ops, device, async_session):
        """The shape written must be one the vocabulary actually permits."""
        r = await ops.attach_photo(device.id, "keypad.jpg", PNG, mime_type="image/png")
        photo = await _content(async_session, r.result["attachment_id"])

        HOUSE.check_entity_type(photo.entity_type)
        HOUSE.check_relationship("has_photo", device.entity_type, photo.entity_type)
        assert HOUSE.carries_blob(photo.entity_type)

    async def test_same_bytes_twice_is_one_blob(self, ops, device, async_session):
        """Content-addressed, so a retried upload cannot double the store."""
        a = await ops.attach_photo(device.id, "keypad.jpg", PNG, mime_type="image/png")
        b = await ops.attach_photo(device.id, "keypad-again.jpg", PNG, mime_type="image/png")

        assert a.result["blob_id"] == b.result["blob_id"]
        blobs = (await async_session.execute(select(Blob))).scalars().all()
        assert len(blobs) == 1
        # Two attachment entities, though -- they are different facts.
        assert a.result["attachment_id"] != b.result["attachment_id"]

    async def test_rejects_invalid_base64(self, ops, device):
        r = await ops.attach_photo(device.id, "x.jpg", "not base64 !!!")
        assert not r.success and "base64" in r.error

    async def test_rejects_a_missing_parent(self, ops):
        r = await ops.attach_photo("nope", "x.jpg", PNG)
        assert not r.success and "not found" in r.error


class TestAttachDocument:
    async def test_a_pdf_is_a_manual_reached_by_documented_by(self, ops, device, async_session):
        """A PDF is not a photo. Routing one to has_photo produced
        `room --has_photo--> manual` in the Corfe install, which the
        vocabulary rejects."""
        r = await ops.attach_document(device.id, "manual.pdf", PDF)
        assert r.success, r.error

        doc = await _content(async_session, r.result["attachment_id"])
        rel = (await async_session.execute(select(EntityRelationship))).scalars().first()

        assert doc.entity_type == "manual"
        assert rel.relationship_type == "documented_by"
        assert (await async_session.get(Blob, r.result["blob_id"])).blob_type == "pdf"
        HOUSE.check_relationship("documented_by", device.entity_type, doc.entity_type)


class TestGetBlob:
    async def test_metadata_without_bytes_by_default(self, ops, device):
        r = await ops.attach_photo(device.id, "k.jpg", PNG, mime_type="image/png")
        got = await ops.get_blob_tool(r.result["blob_id"])

        assert got.success
        assert got.result["size"] == len(base64.b64decode(PNG))
        assert "data" not in got.result       # blobs are large; opt in

    async def test_bytes_when_asked(self, ops, device):
        r = await ops.attach_photo(device.id, "k.jpg", PNG, mime_type="image/png")
        got = await ops.get_blob_tool(r.result["blob_id"], include_data=True)

        assert base64.b64decode(got.result["data"]) == base64.b64decode(PNG)

    async def test_missing_blob_is_an_error_not_an_empty_result(self, ops):
        got = await ops.get_blob_tool("no-such-blob")
        assert not got.success and "not found" in got.error


class TestAppendOnlyRetraction:
    """The store never deletes. Removal is a tombstone; a wrong record is
    marked as an error behind it."""

    async def test_tombstone_appends_a_version_and_keeps_the_old_one(self, ops, device, async_session):
        r = await ops.tombstone_entity(device.id, reason="removed in the rebuild",
                                       user_id="adrian")
        assert r.success, r.error
        assert r.result["tombstone_version"] != r.result["previous_version"]

        versions = await ops.get_entity_versions(device.id)
        assert len(versions) >= 2, "the earlier version must still be readable"

    async def test_the_tombstone_records_why(self, ops, device):
        await ops.tombstone_entity(device.id, reason="sold", user_id="adrian")
        current = await ops.get_entity(device.id)

        assert current.content["deleted"] is True
        assert current.content["deleted_reason"] == "sold"
        assert "deleted_as_error" not in current.content

    async def test_an_error_is_distinguished_from_a_thing_that_is_gone(self, ops, device):
        """'this was never here' and 'this was removed' are different facts."""
        await ops.tombstone_entity(device.id, reason="wrong room, mis-catalogued",
                                   is_error=True, user_id="adrian")
        current = await ops.get_entity(device.id)

        assert current.content["deleted_as_error"] is True

    async def test_retracting_twice_is_idempotent(self, ops, device):
        await ops.tombstone_entity(device.id, reason="sold")
        again = await ops.tombstone_entity(device.id, reason="sold")

        assert again.success and again.result["already_tombstoned"] is True

    async def test_there_is_no_delete_tool(self):
        """Append-only is the design. A delete tool would be the invention."""
        from inbetweenies.mcp.catalog import TOOLS_BY_NAME

        assert not [n for n in TOOLS_BY_NAME if "delete" in n or "remove" in n]


class TestHistoryAndStats:
    async def test_versions_are_reported_newest_first_with_tombstone_flag(self, ops, device):
        await ops.update_entity(device.id, {"name": "Renamed"}, "adrian")
        await ops.tombstone_entity(device.id, reason="gone")

        r = await ops.get_entity_versions_tool(device.id)
        assert r.success
        assert r.result["version_count"] >= 3
        assert any(v["deleted"] for v in r.result["versions"])

    async def test_statistics_reports_counts(self, ops, device):
        r = await ops.get_statistics_tool()
        assert r.success and isinstance(r.result, dict)


class TestMcpWritesArePersisted:
    """The MCP REST endpoint must commit.

    `get_db` never commits and the graph operations only flush, so every write
    through this endpoint used to be rolled back when the session closed:
    create_entity and create_relationship returned success and persisted
    nothing. The graph router committed explicitly; the MCP router did not.
    The two disagreed and MCP lost -- a plausible reason callers reached for
    REST and built their own helper instead.
    """

    def test_the_mcp_router_commits_on_success(self):
        # Read the source rather than import it: importing the router builds the
        # auth stack, which needs a JWT secret this test has no business setting.
        src = pathlib.Path("funkygibbon/api/routers/mcp.py").read_text()
        body = src.split("async def execute_mcp_tool")[1].split("@router")[0]

        assert "await db.commit()" in body, "MCP writes would be rolled back"
        assert "await db.rollback()" in body, "a failed tool must not leave a partial write"

    def test_graph_operations_only_flush_so_the_router_must_commit(self):
        """Pins *why* the router carries the responsibility.

        If store_entity ever starts committing on its own, this fails and the
        router's commit should be revisited rather than silently doubling up.
        """
        import inspect

        from funkygibbon.repositories.graph_impl import SQLGraphOperations

        src = inspect.getsource(SQLGraphOperations.store_entity)
        assert "flush" in src and "commit" not in src


class TestAttachmentsAreSyncSerialisable:
    """An attachment must not poison later reads.

    The sync wire model declares `user_id: str`. An entity written with
    user_id=None serialises to a 500 for every client that subsequently pulls
    it -- the write succeeds and the *reads* break, which is far worse than
    failing at the point of the write.
    """

    async def test_an_attachment_without_an_explicit_user_still_has_an_author(
            self, ops, device, async_session):
        r = await ops.attach_photo(device.id, "k.jpg", PNG, mime_type="image/png")
        photo = await _content(async_session, r.result["attachment_id"])

        assert photo.user_id is not None

    async def test_the_edge_has_an_author_too(self, ops, device, async_session):
        await ops.attach_photo(device.id, "k.jpg", PNG, mime_type="image/png")
        rel = (await async_session.execute(select(EntityRelationship))).scalars().first()

        assert rel.user_id is not None
