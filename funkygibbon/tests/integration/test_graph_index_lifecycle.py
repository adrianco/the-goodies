"""
End-to-end tests for the reported defect in ADR-003 / design-review finding F2.

The bug as reported: an entity created through the REST API was findable by
name but *invisible to `find_path`* until the process restarted, because
`create_entity` patched the index's lookup dictionaries and never touched the
`nodes` structure that traversal reads. The same hole swallowed sync-applied
changes wholesale.

Every test here drives the real HTTP endpoints against one long-lived
application, exactly as a client would, and asserts on traversal endpoints
(`/graph/path`, `/graph/entities/{id}/connected`) rather than on internals.
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
    resp = await async_client.get(f"{API}/graph/statistics", headers=auth)
    assert resp.status_code == 200, resp.text
    service = app.state.graph_index
    assert service.loaded
    return service


async def _create_entity(client, auth, name, entity_type="device"):
    resp = await client.post(
        f"{API}/graph/entities",
        headers=auth,
        json={"entity_type": entity_type, "name": name, "content": {}, "user_id": USER},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["entity"]


async def _create_relationship(client, auth, source, target, rel_type="controls"):
    resp = await client.post(
        f"{API}/graph/relationships",
        headers=auth,
        json={
            "source_id": source["id"],
            "target_id": target["id"],
            "relationship_type": rel_type,
            "properties": {},
            "user_id": USER,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["relationship"]


async def _find_path(client, auth, source, target):
    resp = await client.post(
        f"{API}/graph/path",
        headers=auth,
        json={"from_entity_id": source["id"], "to_entity_id": target["id"], "max_depth": 5},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


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
    search = await async_client.post(
        f"{API}/graph/search", headers=auth, json={"query": "Index Lamp", "limit": 10}
    )
    assert search.status_code == 200, search.text
    assert any(r["entity"]["id"] == lamp["id"] for r in search.json()["results"])

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

    resp = await async_client.get(
        f"{API}/graph/entities/{hub['id']}/connected", headers=auth
    )
    assert resp.status_code == 200, resp.text
    connected = resp.json()
    assert connected["count"] == 1, connected
    assert connected["connected"][0]["entity"]["id"] == lamp["id"]

    stats = await async_client.get(f"{API}/graph/statistics", headers=auth)
    assert stats.json()["total_relationships"] == 1
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

    resp = await async_client.put(
        f"{API}/graph/entities/{lamp['id']}",
        headers=auth,
        json={"name": "Renamed Lamp", "user_id": USER},
    )
    assert resp.status_code == 200, resp.text

    search = await async_client.post(
        f"{API}/graph/search", headers=auth, json={"query": "Renamed Lamp", "limit": 10}
    )
    ids = [r["entity"]["id"] for r in search.json()["results"]]
    assert lamp["id"] in ids

    stale = await async_client.post(
        f"{API}/graph/search", headers=auth, json={"query": "Rename Lamp", "limit": 10}
    )
    assert all(r["entity"]["name"] != "Rename Lamp" for r in stale.json()["results"])

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

    resp = await async_client.put(
        f"{API}/graph/entities/{lamp['id']}",
        headers=auth,
        json={"content": {"deleted": True}, "user_id": USER},
    )
    assert resp.status_code == 200, resp.text

    assert (await _find_path(async_client, auth, hub, lamp))["found"] is False

    connected = await async_client.get(
        f"{API}/graph/entities/{hub['id']}/connected", headers=auth
    )
    assert connected.json()["count"] == 0

    search = await async_client.post(
        f"{API}/graph/search", headers=auth, json={"query": "Tombstone Lamp", "limit": 10}
    )
    assert all(r["entity"]["id"] != lamp["id"] for r in search.json()["results"])
    assert warm_index.rebuild_count == rebuilds_before


@pytest.mark.asyncio
async def test_index_is_owned_by_the_application(async_client, app, auth):
    """The index serving requests is the one on app.state -- no hidden global."""
    from funkygibbon.graph.index_service import GraphIndexService

    service = app.state.graph_index
    assert isinstance(service, GraphIndexService)

    # A read loads the index; after that every write must be written through it.
    assert (await async_client.get(f"{API}/graph/statistics", headers=auth)).status_code == 200
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
    search = await async_client.post(
        f"{API}/graph/search", headers=auth, json={"query": "Synced Lamp", "limit": 10}
    )
    assert any(r["entity"]["id"] == synced.id for r in search.json()["results"])
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
        from_entity_version=hub["version"],
        to_entity_id=rogue.id,
        to_entity_version=rogue.version,
        relationship_type=RelationshipType.CONTROLS,
        properties={},
        user_id=USER,
    ))
    await test_session.commit()

    path = await async_client.post(
        f"{API}/graph/path",
        headers=auth,
        json={"from_entity_id": hub["id"], "to_entity_id": rogue.id, "max_depth": 5},
    )
    assert path.json()["found"] is True, "drift check must repair a bypassed write"
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
            "protocol_version": "inbetweenies-v2",
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
                    "from_entity_version": hub["version"],
                    "to_entity_id": arrived_id,
                    "to_entity_version": arrived_version,
                    "relationship_type": "controls",
                    "properties": {},
                }],
            }],
        },
    )
    assert resp.status_code == 200, resp.text
    assert arrived_id in resp.json()["applied"], resp.json()

    path = await async_client.post(
        f"{API}/graph/path",
        headers=auth,
        json={"from_entity_id": hub["id"], "to_entity_id": arrived_id, "max_depth": 5},
    )
    assert path.status_code == 200, path.text
    assert path.json()["found"] is True, (
        "an entity applied by sync is invisible to find_path -- the sync path "
        "did not write through to the index (finding F2)"
    )
    assert warm_index.rebuild_count == rebuilds_before, (
        "the index must be maintained by the sync write-through, not repaired "
        "afterwards by the drift detector"
    )
