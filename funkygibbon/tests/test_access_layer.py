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
from inbetweenies.models import Entity

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
        "protocol_version": "inbetweenies-v2", "device_id": "d", "user_id": USER,
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

        rest = client.get(f"/api/v1/graph/entities/E", headers=headers)
        assert rest.status_code == 200
        assert rest.json()["entity"]["name"] == "kept", (
            "the REST API and sync must serve the same version"
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
                "id": "R", "from_entity_id": "BAD", "from_entity_version": "v",
                "to_entity_id": "GOOD", "to_entity_version": good,
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
                "id": "R", "from_entity_id": "GOOD", "from_entity_version": "v",
                "to_entity_id": "GOOD", "to_entity_version": "v",
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
