"""Unit tests for the sync PUSH path (issue #61).

REGRESSION CONTEXT:
`sync()` contained push code that was structurally unreachable. It gated on
`SyncEngine._pending_sync_entities`, an in-memory set populated only by
`mark_entity_for_sync()` — a method with no production callers. So
`_get_local_changes()` always returned [], the push never fired, and local
writes silently stayed local forever while `sync()` reported success.

Two things made it hard to see:
  * `synced_entities` counted only server-originated changes, so a pull-only
    sync still reported a large number and looked healthy.
  * The pending set was cleared BEFORE the push rather than after it, so even
    the test-only path lost writes whenever a push failed.

These tests pin the invariants that keep the push path reachable and safe.
"""

import asyncio
import shutil
import tempfile
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from blowingoff.graph.local_operations import LocalGraphOperations
from blowingoff.graph.local_storage import LocalGraphStorage
from blowingoff.sync.engine import SyncEngine
from inbetweenies.models import (
    Entity,
    EntityRelationship,
    EntityType,
    RelationshipType,
    SourceType,
)
from inbetweenies.sync import Change, SyncOperation


@pytest.fixture
def storage_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def graph_ops(storage_dir):
    return LocalGraphOperations(LocalGraphStorage(storage_dir=storage_dir))


def make_entity(name="Test Room", entity_type=EntityType.ROOM):
    return Entity(
        id=str(uuid.uuid4()),
        version=f"{datetime.now(UTC).isoformat()}Z-test",
        entity_type=entity_type,
        name=name,
        content={},
        source_type=SourceType.MANUAL,
        user_id="test-user",
        parent_versions=[],
    )


class _StubProtocol:
    """Records what got pushed and replays a canned server ack."""

    def __init__(self, applied=None, applied_relationships=None, fail=False):
        self.applied = applied
        self.applied_relationships = applied_relationships or []
        self.fail = fail
        self.pushed_changes = None

    async def sync_push(self, changes):
        if self.fail:
            raise ConnectionError("server unreachable")
        self.pushed_changes = changes
        # Default: server acknowledges everything it was sent.
        applied = self.applied
        if applied is None:
            applied = [c.entity_id for c in changes if c.entity_id]
        return {"applied": applied, "applied_relationships": self.applied_relationships}


@pytest_asyncio.fixture
async def engine(graph_ops):
    engine = SyncEngine.__new__(SyncEngine)  # bypass DB/session setup
    engine.graph_operations = graph_ops
    engine.protocol = _StubProtocol()
    return engine


class TestDirtyTracking:
    """A local write must be queued for push; a pulled write must not be."""

    @pytest.mark.asyncio
    async def test_local_write_marks_entity_pending(self, graph_ops):
        entity = make_entity()
        await graph_ops.store_entity(entity)

        assert graph_ops.get_pending_entities() == {entity.id: "create"}

    @pytest.mark.asyncio
    async def test_server_applied_write_is_not_marked_pending(self, graph_ops):
        """The core anti-echo rule: never push back what we just pulled."""
        entity = make_entity()
        await graph_ops.store_entity(entity, mark_dirty=False)

        assert graph_ops.get_pending_entities() == {}

    @pytest.mark.asyncio
    async def test_second_local_write_is_an_update(self, graph_ops):
        entity = make_entity()
        await graph_ops.store_entity(entity, mark_dirty=False)  # arrived via sync

        updated = make_entity()
        updated.id = entity.id
        await graph_ops.store_entity(updated)

        assert graph_ops.get_pending_entities() == {entity.id: "update"}

    @pytest.mark.asyncio
    async def test_create_edited_before_sync_stays_a_create(self, graph_ops):
        """The server has never seen it, so it is still a create."""
        entity = make_entity()
        await graph_ops.store_entity(entity)

        edited = make_entity()
        edited.id = entity.id
        await graph_ops.store_entity(edited)

        assert graph_ops.get_pending_entities() == {entity.id: "create"}

    @pytest.mark.asyncio
    async def test_relationship_without_an_id_gets_one(self, graph_ops):
        """An unidentified relationship must never reach the pending set.

        It was tracked under the JSON key "null": unpushable (the server keys
        on id) and unclearable (no ack can ever name it), so it accumulated
        on every sync forever. store_entity already generated ids; this did
        not.
        """
        relationship = EntityRelationship(
            from_entity_id="device-1",
            from_entity_version="v1",
            to_entity_id="room-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
        )
        stored = await graph_ops.store_relationship(relationship)

        assert stored.id, "an id must be generated"
        pending = graph_ops.get_pending_relationships()
        assert "null" not in pending
        assert list(pending) == [stored.id]

    @pytest.mark.asyncio
    async def test_local_relationship_write_marks_pending(self, graph_ops):
        relationship = EntityRelationship(
            id=str(uuid.uuid4()),
            from_entity_id="device-1",
            from_entity_version="v1",
            to_entity_id="room-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            user_id="test-user",
        )
        await graph_ops.store_relationship(relationship)

        assert graph_ops.get_pending_relationships() == {relationship.id: "create"}


class TestPendingPersistence:
    """An offline write must survive a restart, or it is lost."""

    @pytest.mark.asyncio
    async def test_pending_survives_storage_restart(self, storage_dir):
        storage = LocalGraphStorage(storage_dir=storage_dir)
        entity = make_entity()
        await LocalGraphOperations(storage).store_entity(entity)

        # Simulate process restart: brand-new storage over the same directory.
        reopened = LocalGraphStorage(storage_dir=storage_dir)

        assert reopened.get_pending_entities() == {entity.id: "create"}


class TestGetLocalChanges:
    """The push payload must actually be built from pending state."""

    @pytest.mark.asyncio
    async def test_pending_entity_becomes_a_change(self, engine, graph_ops):
        entity = make_entity()
        await graph_ops.store_entity(entity)

        changes = await engine._get_local_changes(since=None)

        assert len(changes) == 1
        assert changes[0].entity_id == entity.id
        assert changes[0].operation == SyncOperation.CREATE

    @pytest.mark.asyncio
    async def test_no_pending_means_no_changes(self, engine, graph_ops):
        await graph_ops.store_entity(make_entity(), mark_dirty=False)

        assert await engine._get_local_changes(since=None) == []

    @pytest.mark.asyncio
    async def test_get_local_changes_does_not_clear_pending(self, engine, graph_ops):
        """Clearing here loses the write whenever the push then fails."""
        entity = make_entity()
        await graph_ops.store_entity(entity)

        await engine._get_local_changes(since=None)

        assert graph_ops.get_pending_entities() == {entity.id: "create"}

    @pytest.mark.asyncio
    async def test_relationship_rides_on_its_source_entity_change(self, engine, graph_ops):
        entity = make_entity()
        await graph_ops.store_entity(entity)
        relationship = EntityRelationship(
            id=str(uuid.uuid4()),
            from_entity_id=entity.id,
            from_entity_version=entity.version,
            to_entity_id="room-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            user_id="test-user",
        )
        await graph_ops.store_relationship(relationship)

        changes = await engine._get_local_changes(since=None)

        assert len(changes) == 1
        assert [r["id"] for r in changes[0].relationships] == [relationship.id]

    @pytest.mark.asyncio
    async def test_relationship_with_synced_endpoints_still_pushes(self, engine, graph_ops):
        """An edge whose endpoints are already in sync must not be dropped."""
        entity = make_entity()
        await graph_ops.store_entity(entity, mark_dirty=False)
        relationship = EntityRelationship(
            id=str(uuid.uuid4()),
            from_entity_id=entity.id,
            from_entity_version=entity.version,
            to_entity_id="room-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            user_id="test-user",
        )
        await graph_ops.store_relationship(relationship)

        changes = await engine._get_local_changes(since=None)

        assert len(changes) == 1
        assert [r["id"] for r in changes[0].relationships] == [relationship.id]


class TestPushClearsPendingSafely:
    """Pending marks may only be dropped on a per-id server acknowledgement."""

    @pytest.mark.asyncio
    async def test_acknowledged_change_is_cleared(self, engine, graph_ops):
        entity = make_entity()
        await graph_ops.store_entity(entity)

        changes = await engine._get_local_changes(since=None)
        await engine._push_local_changes(changes)

        assert graph_ops.get_pending_entities() == {}

    @pytest.mark.asyncio
    async def test_unacknowledged_change_stays_pending(self, engine, graph_ops):
        """A server that applied nothing must not cause us to drop the write."""
        entity = make_entity()
        await graph_ops.store_entity(entity)
        engine.protocol = _StubProtocol(applied=[])

        changes = await engine._get_local_changes(since=None)
        await engine._push_local_changes(changes)

        assert graph_ops.get_pending_entities() == {entity.id: "create"}

    @pytest.mark.asyncio
    async def test_partial_ack_clears_only_the_acknowledged_id(self, engine, graph_ops):
        kept = make_entity(name="Kept")
        acked = make_entity(name="Acked")
        await graph_ops.store_entity(kept)
        await graph_ops.store_entity(acked)
        engine.protocol = _StubProtocol(applied=[acked.id])

        changes = await engine._get_local_changes(since=None)
        await engine._push_local_changes(changes)

        assert graph_ops.get_pending_entities() == {kept.id: "create"}

    @pytest.mark.asyncio
    async def test_failed_push_preserves_pending(self, engine, graph_ops):
        """The data-loss case: a raising push must not consume the write."""
        entity = make_entity()
        await graph_ops.store_entity(entity)
        engine.protocol = _StubProtocol(fail=True)

        changes = await engine._get_local_changes(since=None)
        with pytest.raises(ConnectionError):
            await engine._push_local_changes(changes)

        assert graph_ops.get_pending_entities() == {entity.id: "create"}

    @pytest.mark.asyncio
    async def test_skipped_relationship_stays_pending(self, engine, graph_ops):
        """Server skips an edge with a dangling endpoint; we must retry it."""
        entity = make_entity()
        await graph_ops.store_entity(entity)
        relationship = EntityRelationship(
            id=str(uuid.uuid4()),
            from_entity_id=entity.id,
            from_entity_version=entity.version,
            to_entity_id="not-on-server-yet",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            user_id="test-user",
        )
        await graph_ops.store_relationship(relationship)
        engine.protocol = _StubProtocol(
            applied=[entity.id], applied_relationships=[]
        )

        changes = await engine._get_local_changes(since=None)
        await engine._push_local_changes(changes)

        assert graph_ops.get_pending_entities() == {}
        assert graph_ops.get_pending_relationships() == {relationship.id: "create"}


class TestPendingCount:
    """pending_changes_count reported 0 unconditionally before the fix."""

    @pytest.mark.asyncio
    async def test_counts_entities_and_relationships(self, graph_ops):
        await graph_ops.store_entity(make_entity())
        await graph_ops.store_relationship(
            EntityRelationship(
                id=str(uuid.uuid4()),
                from_entity_id="a",
                from_entity_version="v1",
                to_entity_id="b",
                to_entity_version="v1",
                relationship_type=RelationshipType.LOCATED_IN,
                properties={},
                user_id="test-user",
            )
        )

        assert graph_ops.pending_count() == 2

    @pytest.mark.asyncio
    async def test_zero_when_nothing_local(self, graph_ops):
        await graph_ops.store_entity(make_entity(), mark_dirty=False)

        assert graph_ops.pending_count() == 0


class _OrderingProbe:
    """Protocol double that serves one server change and records the push."""

    def __init__(self, server_entity):
        self.server_entity = server_entity
        self.pushed_names = None

    async def sync_request(self, last_sync=None, entity_types=None):
        return {"server_time": datetime.now(UTC).isoformat()}

    def parse_sync_delta(self, response):
        entity = self.server_entity
        return [Change(
            entity_type="room",
            entity_id=entity.id,
            operation=SyncOperation.UPDATE,
            data=entity.to_dict(),
            updated_at=datetime.now(UTC),
            sync_id=entity.version,
        )], []

    async def sync_push(self, changes):
        self.pushed_names = [c.data.get("name") for c in changes]
        return {"applied": [c.entity_id for c in changes], "applied_relationships": []}


class _NullMetadataRepo:
    async def get_metadata(self, client_id):
        return None

    async def update_sync_time(self, watermark, client_id):
        return None


class TestPullDoesNotClobberThePushPayload:
    """Guards the ordering that keeps this client clear of issue #69.

    sync() captures the push payload BEFORE the pull applies server changes.
    If that capture ever moves after the pull, the payload is rebuilt from
    storage the pull just overwrote, and the client pushes the server's own
    version back — the server acks it idempotently, the pending mark clears,
    and the local edit is destroyed with the server never seeing it.

    KittenKong had exactly that ordering and needed an explicit pull-guard
    (ADR-011 §1). This client is safe only because of statement order, which
    nothing else expresses — hence this test. It exercises the real sync()
    rather than the phases individually, so a reordering inside sync() fails
    it.
    """

    @pytest.mark.asyncio
    async def test_push_carries_the_local_edit_not_the_pulled_version(self, graph_ops):
        local = make_entity(name="LOCAL-EDIT")
        await graph_ops.store_entity(local)

        server_version = make_entity(name="SERVER-EDIT")
        server_version.id = local.id

        engine = SyncEngine.__new__(SyncEngine)
        engine.graph_operations = graph_ops
        engine.protocol = _OrderingProbe(server_version)
        engine.metadata_repo = _NullMetadataRepo()
        engine.client_id = "test-client"
        engine._sync_lock = asyncio.Lock()
        engine._is_syncing = False

        result = await engine.sync()

        assert result.success, result.errors
        assert engine.protocol.pushed_names == ["LOCAL-EDIT"], (
            "the push must carry the local edit; seeing SERVER-EDIT means the "
            "payload was rebuilt from storage after the pull overwrote it "
            "(issue #69)"
        )

    @pytest.mark.asyncio
    async def test_local_edit_survives_the_pull_in_storage(self, graph_ops):
        """The pulled version may become latest, but the edit is not erased."""
        local = make_entity(name="LOCAL-EDIT")
        await graph_ops.store_entity(local)

        server_version = make_entity(name="SERVER-EDIT")
        server_version.id = local.id

        engine = SyncEngine.__new__(SyncEngine)
        engine.graph_operations = graph_ops
        engine.protocol = _OrderingProbe(server_version)
        engine.metadata_repo = _NullMetadataRepo()
        engine.client_id = "test-client"
        engine._sync_lock = asyncio.Lock()
        engine._is_syncing = False

        await engine.sync()

        stored = [v.name for v in graph_ops.storage._entities[local.id]]
        assert "LOCAL-EDIT" in stored, "the local edit must remain in version history"
