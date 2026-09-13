"""ADR-002 access layer + ADR-011 §3 atomic batches.

`is_latest` and `server_seq` are not primarily optimisations at this data size
(the live instance is ~500 version rows). They are here because they make two
things FACTS rather than inferences:

* **Which version is current.** Three call sites used to infer it and disagree:
  sync took the lexically greatest version, GraphRepository took the greatest
  created_at, and conflict resolution decided by LWW on updated_at. A preserved
  losing version could therefore be served as current by the REST API while
  sync correctly reported the winner. Resolution now records its outcome.
* **What order the server applied things in.** `updated_at > since` cannot
  separate two rows written in the same microsecond, and a clock adjustment can
  move rows across a cursor a client has already passed.

The scalability follows, but the correctness is the reason.
"""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from fastapi.testclient import TestClient

import funkygibbon.database as dbmod
from funkygibbon.api.app import create_app
from funkygibbon.config import settings
from inbetweenies.models import Entity, EntityRelationship

USER = "access-layer"
_ANCIENT = "2020-01-01T00:00:00.000000+00:00-000001-old"


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "funkygibbon.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(url, connect_args={"timeout": 5}, poolclass=NullPool)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "async_session", sm)
    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.chdir(tmp_path)
    yield
    asyncio.run(engine.dispose())


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "backup_schedule_enabled", False)
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def headers(client):
    token = client.post(
        "/api/v1/auth/admin/login", json={"password": "admin"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _change(change_type, *, id, version, name="N", parents=None, rels=None):
    return {
        "change_type": change_type,
        "entity": {
            "id": id, "version": version, "entity_type": "device", "name": name,
            "content": {}, "source_type": "manual", "user_id": USER,
            "parent_versions": parents or [],
        },
        "relationships": rels or [],
    }


def _sync(client, headers, changes=None, sync_type="full"):
    return client.post("/api/v1/sync/", headers=headers, json={
        "protocol_version": "inbetweenies-v3", "device_id": "d", "user_id": USER,
        "sync_type": sync_type, "changes": changes or [],
    })


def _rows(entity_id=None):
    async def _read():
        async with dbmod.async_session() as session:
            stmt = select(Entity)
            if entity_id is not None:
                stmt = stmt.where(Entity.id == entity_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())
    return asyncio.run(_read())


class TestIsLatest:
    """Exactly one current row per id, and it is the one resolution chose."""

    def test_a_new_version_demotes_its_predecessor(self, client, headers):
        v1 = Entity.create_version("a")
        _sync(client, headers, [_change("create", id="E", version=v1)])
        v2 = Entity.create_version("b")
        _sync(client, headers, [_change("update", id="E", version=v2, parents=[v1])])

        latest = [r for r in _rows("E") if r.is_latest]
        assert len(latest) == 1
        assert latest[0].version == v2

    def test_exactly_one_current_row_survives_a_long_chain(self, client, headers):
        previous = Entity.create_version("a")
        _sync(client, headers, [_change("create", id="E", version=previous)])
        for _ in range(5):
            nxt = Entity.create_version("a")
            _sync(client, headers,
                  [_change("update", id="E", version=nxt, parents=[previous])])
            previous = nxt

        rows = _rows("E")
        assert len(rows) == 6, "every version is retained"
        assert sum(1 for r in rows if r.is_latest) == 1

    def test_a_losing_version_is_stored_but_not_current(self, client, headers):
        """The bug is_latest exists to prevent: a preserved loser being served."""
        winner = Entity.create_version("a")
        _sync(client, headers, [_change("create", id="E", version=winner, name="kept")])
        _sync(client, headers,
              [_change("update", id="E", version=_ANCIENT, name="lost", parents=[])])

        rows = {r.version: r for r in _rows("E")}
        assert _ANCIENT in rows, "the loser must be preserved (ADR-011 §2)"
        assert rows[_ANCIENT].is_latest is False
        assert rows[winner].is_latest is True

    def test_the_served_entity_is_the_current_row(self, client, headers):
        """REST and sync must agree, which was the original defect."""
        winner = Entity.create_version("a")
        _sync(client, headers, [_change("create", id="E", version=winner, name="kept")])
        _sync(client, headers,
              [_change("update", id="E", version=_ANCIENT, name="lost", parents=[])])

        served = _sync(client, headers).json()["changes"]
        by_id = {c["entity"]["id"]: c["entity"] for c in served if c.get("entity")}
        assert by_id["E"]["name"] == "kept"

        via_tool = client.post("/api/v1/mcp/tools/get_entity_details", headers=headers,
                               json={"arguments": {"entity_id": "E"}})
        assert via_tool.status_code == 200
        assert via_tool.json()["result"]["entity"]["name"] == "kept", (
            "the MCP tools and sync must serve the same version"
        )

    def test_a_tombstone_becomes_the_current_row(self, client, headers):
        v1 = Entity.create_version("a")
        _sync(client, headers, [_change("create", id="E", version=v1)])
        v2 = Entity.create_version("b")
        _sync(client, headers, [_change("delete", id="E", version=v2, parents=[v1])])

        latest = [r for r in _rows("E") if r.is_latest]
        assert len(latest) == 1
        assert latest[0].content.get("deleted") is True


class TestServerSeq:
    """A gap-free stamp in apply order — the replication axis."""

    def test_every_stored_version_gets_a_stamp(self, client, headers):
        _sync(client, headers, [
            _change("create", id="A", version=Entity.create_version("a")),
            _change("create", id="B", version=Entity.create_version("b")),
        ])

        assert all(r.server_seq is not None for r in _rows())

    def test_stamps_are_unique_and_ordered_by_apply_order(self, client, headers):
        _sync(client, headers, [_change("create", id="A", version=Entity.create_version("a"))])
        _sync(client, headers, [_change("create", id="B", version=Entity.create_version("b"))])

        by_id = {r.id: r.server_seq for r in _rows()}
        assert len({*by_id.values()}) == len(by_id), "stamps must be unique"
        assert by_id["A"] < by_id["B"], "later apply gets a higher stamp"

    def test_a_losing_version_is_also_stamped(self, client, headers):
        """It is a stored row, so a replica must be able to receive it."""
        _sync(client, headers, [_change("create", id="E", version=Entity.create_version("a"))])
        _sync(client, headers,
              [_change("update", id="E", version=_ANCIENT, parents=[])])

        loser = next(r for r in _rows("E") if r.version == _ANCIENT)
        assert loser.server_seq is not None


class TestEveryWritePathMaintainsTheInvariants:
    """ADR-002 §1-2 hold for ALL writers, not just the sync apply path.

    `GraphRepository.store_entity`'s docstring already said why this matters --
    "a column that only one writer maintains is worse than no column: readers
    trust it, and the paths that skip it leave two rows claiming to be current
    with nothing to say which is right" -- and then a second writer skipped it.
    Every existing test in this file drove one of the two stamping paths, so
    nothing noticed.
    """

    def _mcp_update(self, entity_id, name):
        """Drive the MCP tools' write path (SQLGraphOperations)."""
        import asyncio as _asyncio
        from funkygibbon.repositories.graph_impl import SQLGraphOperations

        async def _run():
            async with dbmod.async_session() as session:
                await SQLGraphOperations(session).update_entity(
                    entity_id, {"name": name}, USER
                )
                await session.commit()
        _asyncio.run(_run())

    def _mcp_store(self, entity_id, version):
        import asyncio as _asyncio
        from funkygibbon.repositories.graph_impl import SQLGraphOperations
        from inbetweenies.models import EntityType, SourceType

        async def _run():
            async with dbmod.async_session() as session:
                await SQLGraphOperations(session).store_entity(Entity(
                    id=entity_id, version=version,
                    entity_type=EntityType.DEVICE, name="via-mcp", content={},
                    source_type=SourceType.MANUAL, user_id=USER, parent_versions=[],
                ))
                await session.commit()
        _asyncio.run(_run())

    def test_the_mcp_write_path_stamps_a_server_seq(self, client, headers):
        """Without a stamp the row is invisible to every cursor delta -- and
        silently so, because `server_seq > :cursor` is NULL for a NULL, which
        excludes the row rather than raising."""
        self._mcp_store("M1", Entity.create_version("a"))

        assert _rows("M1")[0].server_seq is not None

    def test_the_mcp_update_path_demotes_the_superseded_version(self, client, headers):
        """Two rows both marked current is not a cosmetic problem.

        `GraphRepository.get_entity` resolves the current row with
        `where is_latest limit 1`, so with two matches it returns whichever the
        database yields -- and REST and MCP could then report different current
        versions of the same entity.
        """
        self._mcp_store("M2", Entity.create_version("a"))
        self._mcp_update("M2", "via-mcp v2")

        rows = _rows("M2")
        assert len(rows) == 2, "an update must append a version, not overwrite"
        assert sum(1 for r in rows if r.is_latest) == 1, (
            "exactly one row per id may claim to be current"
        )
        assert next(r for r in rows if r.is_latest).name == "via-mcp v2"

    def test_the_mcp_update_path_stamps_the_new_version_too(self, client, headers):
        self._mcp_store("M3", Entity.create_version("a"))
        self._mcp_update("M3", "via-mcp v2")

        assert all(r.server_seq is not None for r in _rows("M3"))

    def test_all_three_writers_share_one_sequence(self, client, headers):
        """A cursor is a position in ONE order. Two allocators would collide,
        and a client would skip whichever row lost the tie."""
        client.post("/api/v1/mcp/tools/create_entity", headers=headers, json={"arguments": {
            "entity_type": "device", "name": "via-tool", "content": {}, "user_id": USER,
        }})
        _sync(client, headers, [_change("create", id="VIA-SYNC",
                                        version=Entity.create_version("a"))])
        self._mcp_store("VIA-MCP", Entity.create_version("a"))

        seqs = [r.server_seq for r in _rows()]
        assert None not in seqs, "every stored row carries a stamp"
        assert len(seqs) == len(set(seqs)), "stamps are unique across writers"


class TestAtomicPushBatch:
    """ADR-011 §3 — a push lands whole or not at all."""

    def test_a_failure_mid_batch_applies_nothing(self, client, headers):
        """The change before the failure must not survive.

        Committing per change left the server half-updated with no record of
        how far it got. An unknown relationship_type raises after the first
        entity has been staged, which is exactly that shape.
        """
        good = Entity.create_version("a")
        response = _sync(client, headers, [
            _change("create", id="GOOD", version=good),
            _change("create", id="BAD", version=Entity.create_version("b"), rels=[{
                "id": "R", "from_entity_id": "BAD",
                "to_entity_id": "GOOD",
                "relationship_type": "not-a-real-type", "properties": {},
            }]),
        ])

        assert response.status_code == 400, response.text
        assert _rows("GOOD") == [], (
            "an entity staged before the failure must be rolled back with it"
        )
        assert _rows("BAD") == []

    def test_nothing_is_acknowledged_when_the_batch_fails(self, client, headers):
        """The client must retry the whole batch, so it may keep every mark."""
        response = _sync(client, headers, [
            _change("create", id="GOOD", version=Entity.create_version("a"), rels=[{
                "id": "R", "from_entity_id": "GOOD",
                "to_entity_id": "GOOD",
                "relationship_type": "not-a-real-type", "properties": {},
            }]),
        ])

        assert response.status_code == 400
        assert "applied" not in response.json(), "a failed batch acknowledges nothing"

    def test_a_successful_batch_applies_everything(self, client, headers):
        body = _sync(client, headers, [
            _change("create", id="A", version=Entity.create_version("a")),
            _change("create", id="B", version=Entity.create_version("b")),
        ]).json()

        assert set(body["applied"]) == {"A", "B"}
        assert len(_rows()) == 2


class TestPaginationAndDigest:
    """ADR-002 §4 cursor pagination and ADR-011 §4 convergence digest."""

    def _make(self, client, headers, count, prefix="P"):
        _sync(client, headers, [
            _change("create", id=f"{prefix}{i}", version=Entity.create_version("a"))
            for i in range(count)
        ])

    def test_a_small_graph_fits_one_page_with_no_cursor(self, client, headers):
        self._make(client, headers, 3)

        body = _sync(client, headers).json()
        assert len(body["changes"]) == 3
        assert body["cursor"] is None, "nothing left to resume from"

    def test_an_oversized_graph_is_capped_and_returns_a_cursor(self, client, headers, monkeypatch):
        import funkygibbon.api.sync as syncmod
        monkeypatch.setattr(syncmod, "PAGE_SIZE", 2)
        self._make(client, headers, 5)

        body = _sync(client, headers).json()
        assert len(body["changes"]) == 2, "the page is capped"
        assert body["cursor"] is not None, "and says where to resume"

    def test_looping_on_the_cursor_drains_every_row_exactly_once(self, client, headers, monkeypatch):
        """The property that matters: no row skipped, none delivered twice.

        Ordering by server_seq is what makes this hold. Without a total order
        the page boundary is whatever the database happened to return, and rows
        fall through the gap between pages.
        """
        import funkygibbon.api.sync as syncmod
        monkeypatch.setattr(syncmod, "PAGE_SIZE", 2)

        # Ids deliberately sort AGAINST creation order (P6 created first, P0
        # last). If the server paged by anything other than the replication
        # axis, the first page would hold the highest server_seq values and the
        # cursor would jump straight past the rest — so this fixture is what
        # makes the test able to fail.
        for i in reversed(range(7)):
            _sync(client, headers,
                  [_change("create", id=f"P{i}", version=Entity.create_version("a"))])

        seen, cursor, pages = [], None, 0
        while True:
            body = client.post("/api/v1/sync/", headers=headers, json={
                "protocol_version": "inbetweenies-v3", "device_id": "d",
                "user_id": USER, "sync_type": "delta", "changes": [],
                "cursor": cursor,
            }).json()
            seen += [c["entity"]["id"] for c in body["changes"] if c.get("entity")]
            cursor = body["cursor"]
            pages += 1
            if cursor is None or pages > 20:
                break

        assert pages > 1, "the fixture must actually span multiple pages"
        assert len(seen) == len(set(seen)), "no row delivered twice"
        assert set(seen) == {f"P{i}" for i in range(7)}, "no row skipped"

    def test_a_non_numeric_cursor_is_rejected(self, client, headers):
        """Better a 400 than silently returning the whole graph."""
        response = client.post("/api/v1/sync/", headers=headers, json={
            "protocol_version": "inbetweenies-v3", "device_id": "d", "user_id": USER,
            "sync_type": "delta", "changes": [], "cursor": "not-a-number",
        })

        assert response.status_code == 400

    def test_the_legacy_timestamp_delta_still_works(self, client, headers):
        """KittenKong and blowing-off both persist server_time today. Breaking
        `filters.since` would strand a live client mid-upgrade."""
        watermark = _sync(client, headers).json()["server_time"]
        self._make(client, headers, 1, prefix="AFTER")

        body = client.post("/api/v1/sync/", headers=headers, json={
            "protocol_version": "inbetweenies-v3", "device_id": "d", "user_id": USER,
            "sync_type": "delta", "changes": [], "filters": {"since": watermark},
        }).json()

        ids = {c["entity"]["id"] for c in body["changes"] if c.get("entity")}
        assert "AFTER0" in ids

    def test_the_digest_ignores_superseded_versions(self, client, headers):
        """It covers current state, so history must not move it — otherwise two
        replicas that agree on the present would report divergence."""
        v1 = Entity.create_version("a")
        _sync(client, headers, [_change("create", id="E", version=v1)])
        with_one_version = _sync(client, headers).json()["state_digest"]

        _sync(client, headers,
              [_change("update", id="E", version=_ANCIENT, parents=[])])
        after_a_loser = _sync(client, headers).json()["state_digest"]

        assert after_a_loser == with_one_version, (
            "storing a losing version changes history, not current state"
        )


class TestEveryWritePathMaintainsIsLatest:
    """A column only one writer maintains is worse than no column.

    Readers trust it, and the paths that skip it leave two rows both claiming
    to be current with nothing to say which is right. That is not theoretical:
    routing the graph index at is_latest immediately exposed the repository
    write path as not maintaining it.
    """

    def test_the_repository_demotes_the_previous_version(self, client, headers):
        """A freshly built Entity has is_latest=None until flush — the column
        default is applied by the INSERT, not by __init__. A truth test on it
        silently skips the demotion for the commonest case."""
        import asyncio as _asyncio
        from funkygibbon.repositories.graph import GraphRepository
        from inbetweenies.models import EntityType, SourceType

        def _store(name, version, entity_id):
            async def _run():
                async with dbmod.async_session() as session:
                    stored = await GraphRepository(session).store_entity(Entity(
                        id=entity_id, version=version, entity_type=EntityType.DEVICE,
                        name=name, content={}, source_type=SourceType.MANUAL,
                        user_id=USER, parent_versions=[],
                    ))
                    await session.commit()
                    return stored
            return _asyncio.run(_run())

        v1 = Entity.create_version("a")
        _store("first", v1, "R1")
        v2 = Entity.create_version("b")
        _store("second", v2, "R1")

        rows = {r.version: r.is_latest for r in _rows("R1")}
        assert rows == {v1: False, v2: True}

    def test_the_repository_assigns_a_server_seq(self, client, headers):
        import asyncio as _asyncio
        from funkygibbon.repositories.graph import GraphRepository
        from inbetweenies.models import EntityType, SourceType

        async def _run():
            async with dbmod.async_session() as session:
                await GraphRepository(session).store_entity(Entity(
                    id="R2", version=Entity.create_version("a"),
                    entity_type=EntityType.DEVICE, name="n", content={},
                    source_type=SourceType.MANUAL, user_id=USER, parent_versions=[],
                ))
                await session.commit()
        _asyncio.run(_run())

        assert _rows("R2")[0].server_seq is not None

    def test_tool_and_sync_writes_share_one_sequence(self, client, headers):
        """Two writers allocating stamps independently would collide, and a
        client cursor would then skip whichever lost."""
        client.post("/api/v1/mcp/tools/create_entity", headers=headers, json={"arguments": {
            "entity_type": "device", "name": "via-tool", "content": {}, "user_id": USER,
        }})
        _sync(client, headers, [_change("create", id="VIA-SYNC",
                                        version=Entity.create_version("a"))])

        seqs = [r.server_seq for r in _rows()]
        assert len(seqs) == len(set(seqs)), "stamps must be unique across writers"


class TestEdgesOnTheReplicationAxis:
    """ADR-005 §3: edges carry server_seq from the ONE shared sequence.

    Without it the cursor was not a total order over the stream: edges had to
    be bounded by translating the entity cursor into a wall-clock instant, and
    since edges are written after entities in the same transaction, every edge
    was always "newer" -- a caught-up client re-received the whole edge table
    on every poll.
    """

    def _house(self, client, headers):
        vs = [Entity.create_version("a") for _ in range(3)]
        _sync(client, headers, [
            _change("create", id="lamp", version=vs[0]),
            _change("create", id="kitchen", version=vs[1]),
            _change("create", id="hall", version=vs[2]),
        ])

    def _edge(self, client, headers, to, valid_from=None, valid_to=None):
        rel = {"id": "e1", "from_entity_id": "lamp", "to_entity_id": to,
               "relationship_type": "located_in", "properties": {}}
        if valid_from: rel["valid_from"] = valid_from
        if valid_to: rel["valid_to"] = valid_to
        return _sync(client, headers, [{"change_type": "update", "entity": None,
                                        "relationships": [rel]}])

    def _delta(self, client, headers, cursor):
        return client.post("/api/v1/sync/", headers=headers, json={
            "protocol_version": "inbetweenies-v3", "device_id": "d",
            "user_id": USER, "sync_type": "delta", "changes": [], "cursor": cursor,
        }).json()

    @staticmethod
    def _edges(body):
        return [r for c in body["changes"] for r in c["relationships"]]

    def _top(self, client, headers):
        """The highest stamp in the stream -- what a caught-up client holds."""
        seqs = [r.server_seq for r in _rows()] + [
            r.server_seq for r in _edge_rows()]
        return max(s for s in seqs if s is not None)

    def test_every_stored_edge_interval_is_stamped(self, client, headers):
        self._house(client, headers)
        self._edge(client, headers, "kitchen")
        assert all(r.server_seq is not None for r in _edge_rows())

    def test_entities_and_edges_share_one_sequence(self, client, headers):
        self._house(client, headers)
        self._edge(client, headers, "kitchen")
        seqs = [r.server_seq for r in _rows()] + [r.server_seq for r in _edge_rows()]
        assert len(seqs) == len(set(seqs)), "a stamp may name one row, entity or edge"

    def test_a_caught_up_client_receives_no_edges(self, client, headers):
        """The resend bug, pinned: cursor at the top of the stream -> empty."""
        self._house(client, headers)
        self._edge(client, headers, "kitchen")
        top = self._top(client, headers)
        assert self._edges(self._delta(client, headers, str(top))) == []
        assert self._edges(self._delta(client, headers, str(top))) == []

    def test_a_move_after_the_cursor_is_delivered_once(self, client, headers):
        self._house(client, headers)
        self._edge(client, headers, "kitchen")
        top = self._top(client, headers)

        self._edge(client, headers, "hall")  # ends kitchen row, opens hall row
        delivered = self._edges(self._delta(client, headers, str(top)))
        # Both rows changed past the cursor: the ended one (re-stamped) and
        # the new one. A replica needs both to converge.
        assert sorted(r["to_entity_id"] for r in delivered) == ["hall", "kitchen"]
        assert next(r for r in delivered if r["to_entity_id"] == "kitchen")["valid_to"] is not None

        # And the client that took them is now caught up.
        assert self._edges(self._delta(client, headers, str(self._top(client, headers)))) == []

    def test_an_end_event_alone_crosses_the_cursor(self, client, headers):
        """Ending re-stamps the row; a replica must learn the edge is gone."""
        self._house(client, headers)
        self._edge(client, headers, "kitchen", valid_from="2026-03-01T12:00:00+00:00")
        top = self._top(client, headers)

        self._edge(client, headers, "kitchen", valid_from="2026-03-01T12:00:00+00:00",
                   valid_to="2026-06-01T12:00:00+00:00")
        delivered = self._edges(self._delta(client, headers, str(top)))
        assert len(delivered) == 1 and delivered[0]["valid_to"] is not None

    def test_a_cursor_drain_delivers_every_edge_exactly_once(self, client, headers, monkeypatch):
        import funkygibbon.api.sync as syncmod
        monkeypatch.setattr(syncmod, "PAGE_SIZE", 2)
        self._house(client, headers)
        for i, to in enumerate(["kitchen", "hall", "kitchen"]):
            rel = {"id": f"e{i}", "from_entity_id": "lamp", "to_entity_id": to,
                   "relationship_type": "located_in", "properties": {}}
            _sync(client, headers, [{"change_type": "update", "entity": None, "relationships": [rel]}])

        seen, cursor, pages = [], "0", 0
        while pages < 20:
            body = self._delta(client, headers, cursor)
            seen += [(r["id"], r["valid_from"]) for r in self._edges(body)]
            pages += 1
            if body["cursor"] is None:
                break
            cursor = body["cursor"]

        assert pages > 1, "the fixture must span pages"
        assert len(seen) == len(set(seen)), "no interval delivered twice"
        assert len(seen) == 3, "no interval skipped"


def _edge_rows():
    async def _read():
        async with dbmod.async_session() as session:
            result = await session.execute(select(EntityRelationship))
            return list(result.scalars().all())
    return asyncio.run(_read())
