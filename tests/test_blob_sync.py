"""Blobs travel by sync, so a client never needs to call the server directly.

The client's reach into the server is auth and sync. Nothing else. Attaching a
photo used to break that rule for a structural reason: the sync payload carried
entity and relationship changes and nothing else, so a client could hold an
attachment entity but had no way to move its bytes. The only route left was a
direct call, and a direct call is what quietly becomes the path everything uses.

These tests pin the carriage that removes the reason.
"""

import base64
import hashlib
import os

# Importing funkygibbon.api.sync builds the auth stack, which refuses to start
# without a signing secret. Set before the import, as funkygibbon/conftest.py does.
os.environ.setdefault("FUNKYGIBBON_TEST_MODE", "true")

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from inbetweenies.models import Entity, EntityType, SourceType
from inbetweenies.models.base import Base
from inbetweenies.models.blob import Blob
from inbetweenies.sync.protocol import (
    BlobChange, EntityChange, SyncChange, SyncRequest,
)

RAW = b"\xff\xd8\xff\xe0JFIF" + b"z" * 32
B64 = base64.b64encode(RAW).decode()
DIGEST = hashlib.sha256(RAW).hexdigest()
BLOB_ID = "blob-under-test"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def service(session):
    from funkygibbon.api.sync import SyncHandler
    return SyncHandler(session)


def _blob(**over):
    kwargs = dict(id=BLOB_ID, name="keypad.jpg", blob_type="jpeg",
                  mime_type="image/jpeg", size=len(RAW), data=B64,
                  checksum=DIGEST, user_id="adrian", summary=None)
    kwargs.update(over)
    return BlobChange(**kwargs)


def _photo_change(blob_id=BLOB_ID):
    return SyncChange(
        change_type="create",
        entity=EntityChange(
            id="photo-1", version="2026-08-03T00:00:00+00:00-000001-adrian",
            entity_type="photo", name="keypad.jpg",
            content={"filename": "keypad.jpg", "mime_type": "image/jpeg",
                     "blob_id": blob_id},
            source_type="manual", user_id="adrian", parent_versions=[],
        ),
        blobs=[_blob(id=blob_id)],
    )


class TestTheProtocolCarriesBlobs:
    def test_a_change_can_carry_blobs(self):
        assert SyncChange(change_type="create").blobs == []
        assert len(_photo_change().blobs) == 1

    def test_blobs_are_optional_so_old_clients_still_parse(self):
        """A client that has never heard of blobs must keep working."""
        req = SyncRequest(device_id="d", user_id="u", sync_type="delta",
                          changes=[{"change_type": "update"}])
        assert req.changes[0].blobs == []


class TestPushingBlobs:
    async def test_a_pushed_blob_lands_in_the_table(self, service, session):
        await service._persist_blob(_blob())

        row = await session.get(Blob, BLOB_ID)
        assert row is not None
        assert row.data == RAW
        assert row.size == len(RAW)
        assert row.checksum == DIGEST

    async def test_pushing_the_same_blob_twice_is_idempotent(self, service, session):
        assert await service._persist_blob(_blob()) is True
        assert await service._persist_blob(_blob()) is False

        rows = (await session.execute(select(Blob))).scalars().all()
        assert len(rows) == 1

    async def test_a_corrupt_blob_is_rejected_not_stored(self, service, session):
        """A silently corrupt blob is worse than a missing one: the reference
        resolves and the image is garbage."""
        bad = _blob(data=base64.b64encode(b"different bytes entirely").decode())

        assert await service._persist_blob(bad) is False
        assert await session.get(Blob, BLOB_ID) is None

    async def test_unparseable_base64_is_rejected(self, service, session):
        assert await service._persist_blob(_blob(data="not base64 !!!")) is False
        assert await session.get(Blob, BLOB_ID) is None

    async def test_a_blob_without_a_checksum_is_still_stored_and_gets_one(
            self, service, session):
        await service._persist_blob(_blob(checksum=None))

        row = await session.get(Blob, BLOB_ID)
        assert row is not None and row.checksum == DIGEST


class TestPullingBlobs:
    async def _photo_entity(self, session, content):
        e = Entity(id="photo-1", version="v1", entity_type=EntityType.PHOTO,
                   name="keypad.jpg", content=content, source_type=SourceType.MANUAL,
                   user_id="adrian", parent_versions=[])
        session.add(e)
        session.add(Blob(id=BLOB_ID, name="keypad.jpg", blob_type="jpeg",
                         mime_type="image/jpeg", size=len(RAW), data=RAW,
                         blob_metadata={}, checksum=DIGEST, sync_status="UPLOADED"))
        await session.flush()
        return e

    async def test_an_outgoing_attachment_carries_its_bytes(self, service, session):
        entity = await self._photo_entity(session, {"blob_id": BLOB_ID})

        blobs = await service._blobs_for(entity)

        assert len(blobs) == 1
        assert base64.b64decode(blobs[0].data) == RAW
        assert blobs[0].checksum == DIGEST

    async def test_ordered_inline_images_carry_their_bytes_too(self, service, session):
        """The other live shape (ADR-013 §3): an ordered sequence stays inline."""
        entity = await self._photo_entity(
            session, {"images": [{"step": 1, "blob_id": BLOB_ID}]})

        blobs = await service._blobs_for(entity)
        assert [b.id for b in blobs] == [BLOB_ID]

    async def test_a_reference_named_twice_is_sent_once(self, service, session):
        entity = await self._photo_entity(
            session, {"blob_id": BLOB_ID, "images": [{"blob_id": BLOB_ID}]})

        assert len(await service._blobs_for(entity)) == 1

    async def test_a_dangling_reference_does_not_break_the_entity(self, service, session):
        """One missing blob must not make an entity unsyncable."""
        entity = await self._photo_entity(session, {"blob_id": "no-such-blob"})

        assert await service._blobs_for(entity) == []

    async def test_an_entity_with_no_attachment_sends_no_blobs(self, service, session):
        entity = await self._photo_entity(session, {"text": "just a note"})

        assert await service._blobs_for(entity) == []


class TestRoundTrip:
    async def test_bytes_survive_push_then_pull(self, service, session):
        """The whole point: a client can move a photo using sync alone."""
        change = _photo_change()
        await service._persist_blob(change.blobs[0])
        session.add(Entity(
            id=change.entity.id, version=change.entity.version,
            entity_type=change.entity.entity_type, name=change.entity.name,
            content=change.entity.content, source_type=change.entity.source_type,
            user_id=change.entity.user_id, parent_versions=[]))
        await session.flush()

        entity = (await session.execute(
            select(Entity).where(Entity.id == "photo-1"))).scalars().first()
        outgoing = await service._blobs_for(entity)

        assert base64.b64decode(outgoing[0].data) == RAW


class TestTheResponseActuallyCarriesThem:
    """Wiring, not just the helper.

    The tests above call `_blobs_for` directly, so they all still passed when
    the response was mutated to send `blobs=[]` -- the helper was correct and
    unused. This is the test that fails in that case, which is the one that
    matters: a client pulling an attachment must receive its bytes.
    """

    async def test_a_pulled_attachment_arrives_with_its_bytes(self, service, session):
        session.add(Entity(
            id="photo-1", version="v1", entity_type=EntityType.PHOTO,
            name="keypad.jpg", content={"blob_id": BLOB_ID},
            source_type=SourceType.MANUAL, user_id="adrian", parent_versions=[],
            is_latest=True, server_seq=1))
        session.add(Blob(id=BLOB_ID, name="keypad.jpg", blob_type="jpeg",
                         mime_type="image/jpeg", size=len(RAW), data=RAW,
                         blob_metadata={}, checksum=DIGEST, sync_status="UPLOADED"))
        await session.flush()

        response = await service.handle_sync_request(SyncRequest(
            device_id="d", user_id="adrian", sync_type="full", changes=[]))

        photo = next(c for c in response.changes if c.entity.id == "photo-1")
        assert photo.blobs, "the attachment arrived with no bytes"
        assert base64.b64decode(photo.blobs[0].data) == RAW

    async def test_an_ordinary_entity_carries_no_blobs(self, service, session):
        """Every change carrying every blob would make a full sync enormous."""
        session.add(Entity(
            id="room-1", version="v1", entity_type=EntityType.ROOM, name="Kitchen",
            content={"area": 250}, source_type=SourceType.MANUAL, user_id="adrian",
            parent_versions=[], is_latest=True, server_seq=1))
        await session.flush()

        response = await service.handle_sync_request(SyncRequest(
            device_id="d", user_id="adrian", sync_type="full", changes=[]))

        assert next(c for c in response.changes if c.entity.id == "room-1").blobs == []
