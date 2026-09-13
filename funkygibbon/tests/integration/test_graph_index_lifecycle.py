"""
End-to-end tests for the reported defect in ADR-003 / design-review finding F2.

The bug as reported: an entity created through the REST API was findable by
name but *invisible to `find_path`* until the process restarted, because
`create_entity` patched the index's lookup dictionaries and never touched the
`nodes` structure that traversal reads. The same hole swallowed sync-applied
changes wholesale.

Every test here drives the real HTTP surface against one long-lived
application, exactly as a client would -- the MCP tools (ADR-015; the graph
REST routes these tests were written against are gone) -- and asserts on
traversal (`find_path`, `get_connected`) rather than on internals.
"""

import pytest
import pytest_asyncio

API = "/api/v1"
USER = "index-lifecycle-test"


async def _login(client):
    resp = await client.post(f"{API}/auth/admin/login", json={"password": "admin"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def auth(async_client):
    return await _login(async_client)


@pytest_asyncio.fixture
async def warm_index(async_client, app, auth):
    """A loaded index, as on any server that has served one read.

    This is what makes these tests exercise *write-through* rather than the
    rebuild-on-drift safety net: on a cold index the first read loads everything
    from storage and would hide a broken write path. A real server is warm.
    """
    assert (await _tool(async_client, auth, "get_statistics")) is not None
    service = app.state.graph_index
    assert service.loaded
    return service


async def _tool(client, auth, tool_name, **arguments):
    """Call one MCP tool over HTTP and return its `result` (the client interface)."""
    resp = await client.post(f"{API}/mcp/tools/{tool_name}", headers=auth, json={"arguments": arguments})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "error" not in body, body
    return body["result"]


async def _create_entity(client, auth, name, entity_type="device"):
    return (await _tool(client, auth, "create_entity", entity_type=entity_type, name=name,
                        content={}, user_id=USER))["entity"]


async def _create_relationship(client, auth, source, target, rel_type="controls"):
    return (await _tool(client, auth, "create_relationship", from_entity_id=source["id"],
                        to_entity_id=target["id"], relationship_type=rel_type, properties={}))["relationship"]


async def _find_path(client, auth, source, target):
    return await _path_ids(client, auth, source["id"], target["id"])


async def _path_ids(client, auth, from_id, to_id):
    return await _tool(client, auth, "find_path", from_entity_id=from_id, to_entity_id=to_id, max_depth=5)


async def _search_ids(client, auth, query):
    """search_entities returns flat SearchResult dicts: id/name at the top level."""
    return [(r["id"], r["name"]) for r in (await _tool(client, auth, "search_entities", query=query, limit=10))["results"]]


async def _connected(client, auth, entity_id):
    return await _tool(client, auth, "get_connected", entity_id=entity_id)


async def _update(client, auth, entity_id, **changes):
    return await _tool(client, auth, "update_entity", entity_id=entity_id, changes=changes, user_id=USER)


@pytest.mark.asyncio
async def test_entity_created_via_rest_is_immediately_visible_to_find_path(
    async_client, auth, warm_index
):
    """THE reported defect: created via REST, findable by name, unreachable by path."""
    rebuilds_before = warm_index.rebuild_count
    hub = await _create_entity(async_client, auth, "Index Hub")
    lamp = await _create_entity(async_client, auth, "Index Lamp")
    await _create_relationship(async_client, auth, hub, lamp)

    # Name search saw these even before ADR-003 -- assert it still does.
    assert any(i == lamp["id"] for i, _ in await _search_ids(async_client, auth, "Index Lamp"))

    # ...and traversal, which is what was broken, must see them too.
    path = await _find_path(async_client, auth, hub, lamp)
    assert path["found"] is True, (
        "an entity created through REST is invisible to find_path -- the index "
        "was patched without maintaining `nodes` (finding F2)"
    )
    assert [step["id"] for step in path["path"]] == [hub["id"], lamp["id"]]
    assert warm_index.rebuild_count == rebuilds_before, (
        "the write must be visible because it was written through, not because "
        "the drift safety net rebuilt the whole index"
    )


@pytest.mark.asyncio
async def test_new_relationship_is_immediately_traversable(async_client, auth, warm_index):
    """The mirror half of F2: relationship creation never rebuilt `nodes` either."""
    rebuilds_before = warm_index.rebuild_count
    hub = await _create_entity(async_client, auth, "Conn Hub")
    lamp = await _create_entity(async_client, auth, "Conn Lamp")
    await _create_relationship(async_client, auth, hub, lamp)

    connected = await _connected(async_client, auth, hub["id"])
    assert connected["count"] == 1, connected
    assert connected["connected"][0]["entity"]["id"] == lamp["id"]

    stats = await _tool(async_client, auth, "get_statistics")
    assert stats["total_relationships"] == 1
    assert warm_index.rebuild_count == rebuilds_before


@pytest.mark.asyncio
async def test_multi_hop_path_across_several_writes(async_client, auth):
    """Write, read, write again: the index must stay correct across requests."""
    hub = await _create_entity(async_client, auth, "Chain Hub")
    lamp = await _create_entity(async_client, auth, "Chain Lamp")
    await _create_relationship(async_client, auth, hub, lamp)

    assert (await _find_path(async_client, auth, hub, lamp))["found"] is True

    sensor = await _create_entity(async_client, auth, "Chain Sensor")
    await _create_relationship(async_client, auth, lamp, sensor)

    path = await _find_path(async_client, auth, hub, sensor)
    assert path["found"] is True
    assert [step["id"] for step in path["path"]] == [hub["id"], lamp["id"], sensor["id"]]


@pytest.mark.asyncio
async def test_updated_entity_is_reindexed_without_restart(async_client, auth, warm_index):
    """A REST update writes through: new name searchable, topology preserved."""
    rebuilds_before = warm_index.rebuild_count
    hub = await _create_entity(async_client, auth, "Rename Hub")
    lamp = await _create_entity(async_client, auth, "Rename Lamp")
    await _create_relationship(async_client, auth, hub, lamp)

    await _update(async_client, auth, lamp["id"], name="Renamed Lamp")

    assert lamp["id"] in [i for i, _ in await _search_ids(async_client, auth, "Renamed Lamp")]
    assert all(n != "Rename Lamp" for _, n in await _search_ids(async_client, auth, "Rename Lamp"))

    assert (await _find_path(async_client, auth, hub, lamp))["found"] is True
    assert warm_index.rebuild_count == rebuilds_before


@pytest.mark.asyncio
async def test_tombstoned_entity_drops_out_of_traversal(async_client, auth, warm_index):
    """A delete tombstone written through REST must leave the graph (decision 5)."""
    rebuilds_before = warm_index.rebuild_count
    hub = await _create_entity(async_client, auth, "Tombstone Hub")
    lamp = await _create_entity(async_client, auth, "Tombstone Lamp")
    await _create_relationship(async_client, auth, hub, lamp)
    assert (await _find_path(async_client, auth, hub, lamp))["found"] is True

    await _tool(async_client, auth, "tombstone_entity", entity_id=lamp["id"], reason="test", user_id=USER)

    assert (await _find_path(async_client, auth, hub, lamp))["found"] is False
    assert (await _connected(async_client, auth, hub["id"]))["count"] == 0
    assert all(i != lamp["id"] for i, _ in await _search_ids(async_client, auth, "Tombstone Lamp"))
    assert warm_index.rebuild_count == rebuilds_before


@pytest.mark.asyncio
async def test_index_is_owned_by_the_application(async_client, app, auth):
    """The index serving requests is the one on app.state -- no hidden global."""
    from funkygibbon.graph.index_service import GraphIndexService

    service = app.state.graph_index
    assert isinstance(service, GraphIndexService)

    # A read loads the index; after that every write must be written through it.
    await _tool(async_client, auth, "get_statistics")
    assert service.loaded
    rebuilds_before = service.rebuild_count

    hub = await _create_entity(async_client, auth, "Owned Hub")
    assert hub["id"] in service.index.entities
    assert hub["id"] in service.index.nodes, (
        "write-through must maintain `nodes`, the structure traversal reads"
    )
    assert service.rebuild_count == rebuilds_before, (
        "a REST write must patch the index in place, not fall back to a rebuild"
    )


@pytest.mark.asyncio
async def test_sync_shaped_write_through_reaches_the_apps_index(
    async_client, app, auth, warm_index, test_session
):
    """The hook `api/sync.py` calls must find this application's index.

    ``SyncHandler`` only ever holds a database session, so it reaches the index
    through ``write_through_applied_changes``, which resolves the service the
    middleware bound to the in-flight request. This test makes that exact call
    from inside a real request and asserts the application's index picked the
    change up -- without a rebuild, so it is the write-through that did it.
    """
    import uuid
    from funkygibbon.graph.index_service import (
        current_graph_index_service, write_through_applied_changes,
    )
    from funkygibbon.models import Entity, EntityType, SourceType

    hub = await _create_entity(async_client, auth, "Sync Hub")
    rebuilds_before = warm_index.rebuild_count

    synced = Entity(
        id=str(uuid.uuid4()),
        version=Entity.create_version(USER),
        entity_type=EntityType.DEVICE,
        name="Synced Lamp",
        content={},
        source_type=SourceType.MANUAL,
        user_id=USER,
        parent_versions=[],
    )

    async def _sync_apply():
        """Stands in for SyncHandler.handle_sync_request applying a change."""
        assert current_graph_index_service() is app.state.graph_index, (
            "the request-scoped binding must resolve to the app-owned service"
        )
        test_session.add(synced)
        await test_session.commit()
        await write_through_applied_changes(test_session, entity_ids=[synced.id])
        return {"ok": True}

    app.add_api_route("/_test/sync-apply", _sync_apply, methods=["POST"])
    resp = await async_client.post("/_test/sync-apply")
    assert resp.status_code == 200, resp.text

    assert synced.id in warm_index.index.entities
    assert synced.id in warm_index.index.nodes
    assert warm_index.rebuild_count == rebuilds_before, (
        "sync apply must write through, not rely on rebuild-on-drift"
    )

    # And it is genuinely visible to graph reads over HTTP.
    assert any(i == synced.id for i, _ in await _search_ids(async_client, auth, "Synced Lamp"))
    assert warm_index.rebuild_count == rebuilds_before
    assert hub["id"] in warm_index.index.entities


@pytest.mark.asyncio
async def test_write_bypassing_the_index_is_repaired_by_drift_detection(
    async_client, auth, warm_index, test_session
):
    """Safety net (decision 3): storage moved behind the index's back."""
    import uuid
    from funkygibbon.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType

    hub = await _create_entity(async_client, auth, "Drift Hub")
    service = warm_index
    # The index is warm and already knows about the hub, so a stale read here
    # would be served from memory rather than repaired by a first-time load.
    assert hub["id"] in service.index.nodes
    rebuilds_before = service.rebuild_count

    # Simulate a mutation path that never learned about write-through.
    rogue = Entity(
        id=str(uuid.uuid4()),
        version=Entity.create_version(USER),
        entity_type=EntityType.DEVICE,
        name="Drift Rogue",
        content={},
        source_type=SourceType.MANUAL,
        user_id=USER,
        parent_versions=[],
    )
    test_session.add(rogue)
    await test_session.commit()
    test_session.add(EntityRelationship(
        id=str(uuid.uuid4()),
        from_entity_id=hub["id"],
        to_entity_id=rogue.id,
        relationship_type=RelationshipType.CONTROLS,
        properties={},
        user_id=USER,
    ))
    await test_session.commit()

    path = await _path_ids(async_client, auth, hub["id"], rogue.id)
    assert path["found"] is True, "drift check must repair a bypassed write"
    assert service.rebuild_count == rebuilds_before + 1


@pytest.mark.asyncio
async def test_sync_applied_entity_is_immediately_traversable(
    async_client, auth, warm_index
):
    """The sync half of F2, which is how the defect was actually reported.

    "Sync-applied changes never touch it" -- an entity arriving over
    /api/v1/sync was findable by name but invisible to find_path until the
    process restarted. REST create and sync apply are different code paths, so
    covering one says nothing about the other; this drives the real sync
    endpoint rather than a repository call.

    Asserting rebuild_count is unchanged is what makes this a write-through
    test: without it the drift detector would repair the index on the next read
    and the test would pass against the very bug it exists to catch.
    """
    from inbetweenies.models import Entity

    hub = await _create_entity(async_client, auth, "sync-index-hub")
    rebuilds_before = warm_index.rebuild_count

    arrived_id = "sync-arrival-entity"
    arrived_version = Entity.create_version(USER)
    resp = await async_client.post(
        f"{API}/sync/",
        headers=auth,
        json={
            "protocol_version": "inbetweenies-v3",
            "device_id": "index-sync-device",
            "user_id": USER,
            "sync_type": "full",
            "changes": [{
                "change_type": "create",
                "entity": {
                    "id": arrived_id,
                    "version": arrived_version,
                    "entity_type": "device",
                    "name": "arrived-by-sync",
                    "content": {},
                    "source_type": "manual",
                    "user_id": USER,
                    "parent_versions": [],
                },
                "relationships": [{
                    "id": "sync-arrival-edge",
                    "from_entity_id": hub["id"],
                    "to_entity_id": arrived_id,
                    "relationship_type": "controls",
                    "properties": {},
                }],
            }],
        },
    )
    assert resp.status_code == 200, resp.text
    assert arrived_id in resp.json()["applied"], resp.json()

    path_body = await _path_ids(async_client, auth, hub["id"], arrived_id)
    class _R:  # keep the assertions below unchanged in shape
        status_code = 200
        def json(self): return path_body
    path = _R()
    assert path.json()["found"] is True, (
        "an entity applied by sync is invisible to find_path -- the sync path "
        "did not write through to the index (finding F2)"
    )
    assert warm_index.rebuild_count == rebuilds_before, (
        "the index must be maintained by the sync write-through, not repaired "
        "afterwards by the drift detector"
    )


# ======================================================================
# ADR-004 §1 — the index caches `at = now`, so it holds CURRENT edges only.
#
# The index is the one reader that queries edges with no endpoint filter,
# which is exactly the shape the currency gate used to skip. That made
# these the cheapest bugs in the temporal work to ship and the hardest to
# see: every unit test filtered by an endpoint and passed.
# ======================================================================

async def _retire_edge(session, relationship_id, at=None):
    """End an edge's open interval directly in storage.

    There is no REST delete-relationship endpoint yet, and going through the
    session has a second benefit: it bypasses write-through, so the read that
    follows exercises the drift-detection rebuild — which is the code path that
    loads every edge with no endpoint filter.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from funkygibbon.models import EntityRelationship

    row = await session.scalar(
        select(EntityRelationship).where(
            EntityRelationship.id == relationship_id,
            EntityRelationship.valid_to.is_(None),
        )
    )
    assert row is not None, "no open interval to retire"
    row.valid_to = at or datetime.now(timezone.utc)
    await session.commit()
    return row


@pytest.mark.asyncio
async def test_a_retired_edge_does_not_come_back_on_rebuild(
    async_client, auth, warm_index, test_session
):
    """A full load must not resurrect history as state.

    `load_from_storage` calls `get_relationships()` with no endpoint filter, and
    the currency filter was gated on one being supplied — so every retired
    interval came back as a live edge. A device that had ever been in the
    kitchen stayed connected to it forever, from the first rebuild onward.
    """
    hub = await _create_entity(async_client, auth, "Retire Hub")
    lamp = await _create_entity(async_client, auth, "Retire Lamp")
    rel = await _create_relationship(async_client, auth, hub, lamp)

    assert (await _connected(async_client, auth, hub["id"]))["count"] == 1, "precondition: the edge starts live"

    await _retire_edge(test_session, rel["id"])

    # Drift detection notices the bypassed write and rebuilds from storage.
    assert (await _connected(async_client, auth, hub["id"]))["count"] == 0, "a retired edge came back as a live one"
    assert (await _tool(async_client, auth, "get_statistics"))["total_relationships"] == 0


@pytest.mark.asyncio
async def test_a_moved_edge_leaves_the_index_holding_only_the_new_placement(
    async_client, auth, warm_index, test_session
):
    """One logical edge, two intervals: the index must hold the open one.

    `apply_external_writes` re-read edges by id alone. With `(id, valid_from)`
    as the primary key that returns every interval, and since the index keys on
    `rel.id`, whichever row the database yielded last won — a coin flip between
    the live placement and a retired one, on the sync-apply path.
    """
    import uuid
    from datetime import datetime, timedelta, timezone
    from funkygibbon.models import EntityRelationship, RelationshipType
    from funkygibbon.graph.index_service import write_through_applied_changes

    lamp = await _create_entity(async_client, auth, "Move Lamp")
    kitchen = await _create_entity(async_client, auth, "Move Kitchen", entity_type="room")
    hall = await _create_entity(async_client, auth, "Move Hall", entity_type="room")

    edge_id = str(uuid.uuid4())
    march = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    june = march + timedelta(days=92)

    # Two intervals of one edge, written straight to storage as sync would.
    test_session.add(EntityRelationship(
        id=edge_id, valid_from=march, valid_to=june,
        from_entity_id=lamp["id"], to_entity_id=kitchen["id"],
        relationship_type=RelationshipType.LOCATED_IN, properties={}, user_id=USER,
    ))
    test_session.add(EntityRelationship(
        id=edge_id, valid_from=june, valid_to=None,
        from_entity_id=lamp["id"], to_entity_id=hall["id"],
        relationship_type=RelationshipType.LOCATED_IN, properties={}, user_id=USER,
    ))
    await test_session.commit()

    await write_through_applied_changes(
        test_session, entity_ids=[], relationship_ids=[edge_id]
    )

    connected = await _connected(async_client, auth, lamp["id"])
    rooms = [c["entity"]["id"] for c in connected["connected"]]
    assert rooms == [hall["id"]], f"index holds the wrong interval: {rooms}"
