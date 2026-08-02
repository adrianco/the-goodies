"""
Unit tests for GraphIndex ownership, write-through and drift detection (ADR-003).

These cover the half of finding F2 that does not need an HTTP stack:

* a change applied through the write-through path is visible immediately, with
  no rebuild and no restart (this is the shape of the sync-apply path);
* a write that bypasses the index is caught by the drift check and repaired;
* tombstoned entities never appear in traversal, at load or on write-through;
* the index has exactly one owner -- no module global, one service per app.
"""

import logging
import uuid

import pytest
import pytest_asyncio

from funkygibbon.graph.index import GraphIndex
from funkygibbon.graph.index_service import (
    GraphIndexService,
    assert_single_worker_posture,
    bind_graph_index_service,
    unbind_graph_index_service,
    write_through_applied_changes,
)
from funkygibbon.models import (
    Entity, EntityType, SourceType, EntityRelationship, RelationshipType
)


async def _store_entity(db, name, *, entity_type=EntityType.DEVICE, content=None,
                        entity_id=None, parent=None):
    """Insert an entity version straight into storage (what sync does)."""
    entity = Entity(
        id=entity_id or str(uuid.uuid4()),
        version=Entity.create_version("test-user"),
        entity_type=entity_type,
        name=name,
        content=content if content is not None else {},
        source_type=SourceType.MANUAL,
        user_id="test-user",
        parent_versions=[parent] if parent else [],
    )
    db.add(entity)
    await db.commit()
    return entity


async def _store_relationship(db, source, target,
                              rel_type=RelationshipType.CONTROLS):
    """Insert an edge straight into storage."""
    rel = EntityRelationship(
        id=str(uuid.uuid4()),
        from_entity_id=source.id,
        from_entity_version=source.version,
        to_entity_id=target.id,
        to_entity_version=target.version,
        relationship_type=rel_type,
        properties={},
        user_id="test-user",
    )
    db.add(rel)
    await db.commit()
    return rel


@pytest_asyncio.fixture
async def seeded(db_session):
    """A loaded service over a two-entity chain: hub -> lamp."""
    hub = await _store_entity(db_session, "Hub")
    lamp = await _store_entity(db_session, "Lamp")
    await _store_relationship(db_session, hub, lamp)

    service = GraphIndexService()
    await service.ensure_current(db_session)
    assert service.index.find_path(hub.id, lamp.id) == [hub.id, lamp.id]
    return service, hub, lamp


class TestWriteThrough:
    """ADR-003 decision 2: mutations update storage and index together."""

    @pytest.mark.asyncio
    async def test_write_through_makes_new_entity_traversable_without_rebuild(
        self, db_session, seeded
    ):
        """A change applied through write-through is visible immediately.

        This is the sync-apply shape: rows land in storage by some other code
        path, which then tells the index the ids it applied. No restart, and --
        asserted here -- no rebuild either.
        """
        service, hub, lamp = seeded
        rebuilds_before = service.rebuild_count

        sensor = await _store_entity(db_session, "Motion Sensor")
        edge = await _store_relationship(db_session, lamp, sensor)

        await service.apply_external_writes(
            db_session, entity_ids=[sensor.id], relationship_ids=[edge.id]
        )

        assert service.index.find_path(hub.id, sensor.id) == [hub.id, lamp.id, sensor.id]
        assert [c["entity"].id for c in
                service.index.get_connected_entities(lamp.id, direction="outgoing")] == [sensor.id]
        assert service.rebuild_count == rebuilds_before, "write-through must not rebuild"
        assert service.generation > 0

    @pytest.mark.asyncio
    async def test_sync_hook_writes_through_the_bound_service(self, db_session, seeded):
        """`write_through_applied_changes` is the entry point api/sync.py calls."""
        service, hub, lamp = seeded
        rebuilds_before = service.rebuild_count

        sensor = await _store_entity(db_session, "Motion Sensor")
        edge = await _store_relationship(db_session, lamp, sensor)

        token = bind_graph_index_service(service)
        try:
            await write_through_applied_changes(
                db_session, entity_ids=[sensor.id], relationship_ids=[edge.id]
            )
        finally:
            unbind_graph_index_service(token)

        assert service.index.find_path(hub.id, sensor.id) == [hub.id, lamp.id, sensor.id]
        assert service.rebuild_count == rebuilds_before

    @pytest.mark.asyncio
    async def test_sync_hook_is_a_noop_with_no_bound_service(self, db_session):
        """Outside a request there is no index to update; must not explode."""
        await write_through_applied_changes(db_session, entity_ids=["nope"])

    @pytest.mark.asyncio
    async def test_write_through_replaces_a_renamed_entity_in_place(
        self, db_session, seeded
    ):
        """A new version updates name search and keeps the topology intact."""
        service, hub, lamp = seeded

        await _store_entity(db_session, "Reading Lamp", entity_id=lamp.id,
                            parent=lamp.version)
        await service.apply_external_writes(db_session, entity_ids=[lamp.id])

        assert [e.name for e in service.index.find_entities_by_name("reading lamp")] == \
            ["Reading Lamp"]
        assert service.index.find_entities_by_name("lamp", fuzzy=False) == []
        assert service.index.find_path(hub.id, lamp.id) == [hub.id, lamp.id]

    @pytest.mark.asyncio
    async def test_write_through_before_first_load_does_not_lose_the_write(
        self, db_session
    ):
        """A write that lands before anything loaded the index is not lost."""
        service = GraphIndexService()
        hub = await _store_entity(db_session, "Hub")
        lamp = await _store_entity(db_session, "Lamp")
        edge = await _store_relationship(db_session, hub, lamp)

        await service.apply_external_writes(
            db_session, entity_ids=[hub.id, lamp.id], relationship_ids=[edge.id]
        )
        index = await service.ensure_current(db_session)

        assert index.find_path(hub.id, lamp.id) == [hub.id, lamp.id]


class TestDriftDetection:
    """ADR-003 decision 3: a missed write is caught on the next read."""

    @pytest.mark.asyncio
    async def test_bypassing_write_through_triggers_a_rebuild(
        self, db_session, seeded, caplog
    ):
        service, hub, lamp = seeded
        rebuilds_before = service.rebuild_count

        # A write path that forgot rule 2 entirely.
        sensor = await _store_entity(db_session, "Rogue Sensor")
        await _store_relationship(db_session, lamp, sensor)

        assert service.index.find_path(hub.id, sensor.id) == [], \
            "precondition: the index has not been told about this write"

        with caplog.at_level(logging.WARNING, logger="funkygibbon.graph.index_service"):
            index = await service.ensure_current(db_session)

        assert service.rebuild_count == rebuilds_before + 1
        assert index.find_path(hub.id, sensor.id) == [hub.id, lamp.id, sensor.id]
        assert any("drift" in record.message.lower() for record in caplog.records), \
            "drift must be logged loudly -- it means a write path bypassed write-through"

    @pytest.mark.asyncio
    async def test_reads_after_write_through_do_not_rebuild(self, db_session, seeded):
        """Write-through re-records the marker, so the drift net stays quiet."""
        service, hub, lamp = seeded
        sensor = await _store_entity(db_session, "Motion Sensor")
        edge = await _store_relationship(db_session, lamp, sensor)
        await service.apply_external_writes(
            db_session, entity_ids=[sensor.id], relationship_ids=[edge.id]
        )

        rebuilds_before = service.rebuild_count
        for _ in range(3):
            await service.ensure_current(db_session)
        assert service.rebuild_count == rebuilds_before

    @pytest.mark.asyncio
    async def test_rebuild_keeps_the_same_index_object(self, db_session, seeded):
        """Holders of the index (MCP server, search engine) must not go stale."""
        service, hub, lamp = seeded
        held = service.index
        await _store_entity(db_session, "Rogue Sensor")

        rebuilt = await service.ensure_current(db_session)
        assert rebuilt is held


class TestTombstones:
    """ADR-003 decision 5: deleted entities are excluded everywhere."""

    @pytest.mark.asyncio
    async def test_tombstoned_entity_is_excluded_at_load(self, db_session):
        hub = await _store_entity(db_session, "Hub")
        lamp = await _store_entity(db_session, "Lamp")
        await _store_relationship(db_session, hub, lamp)
        await _store_entity(db_session, "Lamp", entity_id=lamp.id,
                            parent=lamp.version, content={"deleted": True})

        service = GraphIndexService()
        index = await service.ensure_current(db_session)

        assert lamp.id not in index.entities
        assert lamp.id not in index.nodes
        assert index.find_path(hub.id, lamp.id) == []
        assert index.get_connected_entities(hub.id) == []
        assert index.find_entities_by_name("lamp") == []

    @pytest.mark.asyncio
    async def test_tombstone_write_through_removes_from_traversal(
        self, db_session, seeded
    ):
        service, hub, lamp = seeded

        await _store_entity(db_session, "Lamp", entity_id=lamp.id,
                            parent=lamp.version, content={"deleted": True})
        await service.apply_external_writes(db_session, entity_ids=[lamp.id])

        assert service.index.find_path(hub.id, lamp.id) == []
        assert service.index.get_connected_entities(hub.id) == []
        assert lamp.id not in service.index.entities
        assert service.index.get_statistics()["total_relationships"] == 0
        assert service.rebuild_count == 1, "removal is incremental, not a rebuild"

    @pytest.mark.asyncio
    async def test_relationship_to_a_deleted_endpoint_is_not_indexed(
        self, db_session, seeded
    ):
        """An edge whose endpoint is gone must not resurrect it in traversal."""
        service, hub, lamp = seeded
        ghost = await _store_entity(db_session, "Ghost", content={"deleted": True})
        edge = await _store_relationship(db_session, lamp, ghost)

        await service.apply_external_writes(
            db_session, entity_ids=[ghost.id], relationship_ids=[edge.id]
        )

        assert service.index.find_path(hub.id, ghost.id) == []
        assert service.index.get_connected_entities(lamp.id, direction="outgoing") == []


class TestOwnership:
    """ADR-003 decision 1: one owner, no module global."""

    def test_graph_router_has_no_module_level_index(self):
        from funkygibbon.api.routers import graph as graph_router

        assert not hasattr(graph_router, "_graph_index"), (
            "the module-global GraphIndex is what ADR-003 removes; the index now "
            "lives on app.state"
        )

    def test_each_application_owns_exactly_one_service(self):
        from funkygibbon.api.app import create_app

        first, second = create_app(), create_app()
        assert isinstance(first.state.graph_index, GraphIndexService)
        assert first.state.graph_index is not second.state.graph_index

    def test_mcp_router_has_no_cached_server(self):
        """The cached MCP server pinned the first request's DB session."""
        from funkygibbon.api.routers import mcp as mcp_router

        assert not hasattr(mcp_router, "_mcp_server")

    def test_service_wraps_the_index_it_is_given(self):
        index = GraphIndex()
        assert GraphIndexService(index).index is index


class TestConcurrencyPosture:
    """ADR-003 decision 4: one worker, asserted rather than assumed."""

    def test_single_worker_is_accepted(self, monkeypatch):
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        monkeypatch.delenv("GRAPH_INDEX_ENABLED", raising=False)
        assert_single_worker_posture()

    def test_multiple_workers_are_refused_while_the_index_is_enabled(self, monkeypatch):
        monkeypatch.setenv("WEB_CONCURRENCY", "4")
        monkeypatch.delenv("GRAPH_INDEX_ENABLED", raising=False)
        with pytest.raises(RuntimeError, match="worker"):
            assert_single_worker_posture()

    def test_multiple_workers_are_allowed_with_the_index_disabled(self, monkeypatch):
        monkeypatch.setenv("WEB_CONCURRENCY", "4")
        monkeypatch.setenv("GRAPH_INDEX_ENABLED", "false")
        assert_single_worker_posture()

    @pytest.mark.asyncio
    async def test_disabled_service_is_inert(self, db_session):
        service = GraphIndexService(enabled=False)
        entity = await _store_entity(db_session, "Hub")
        await service.entity_written(db_session, entity)
        index = await service.ensure_current(db_session)
        assert index.entities == {}
        assert service.rebuild_count == 0
