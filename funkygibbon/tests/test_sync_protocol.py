"""Spec-correctness tests for the inbetweenies-v2 sync protocol (PROTOCOL.md).

Synchronous throughout: pure-function units for the version string + canonical
conflict resolver, and endpoint tests driven through a sync TestClient over an
isolated NullPool database (see test_backup for why the shared engine is patched).
"""

import asyncio
import time

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from fastapi.testclient import TestClient

import funkygibbon.database as dbmod
from funkygibbon.config import settings
from funkygibbon.api.app import create_app
from inbetweenies.models import Entity, EntityRelationship
from inbetweenies.sync import ConflictResolver


# --------------------------------------------------------------------------- #
# Pure-function units
# --------------------------------------------------------------------------- #
def test_version_format_is_canonical_and_monotonic():
    v1 = Entity.create_version("alice")
    v2 = Entity.create_version("alice")
    # No doubled Z, ends with user id, parses to a UTC timestamp.
    assert "Z-" not in v1 and "+00:00" in v1
    assert v1.endswith("-alice")
    assert Entity.version_timestamp(v1) is not None
    # Monotonic: later call sorts lexically greater (counter and/or time advance).
    assert v2 > v1


def test_version_timestamp_handles_hyphenated_user_and_legacy_z():
    canonical = "2026-06-15T13:37:41.613629+00:00-000001-local-client"
    legacy_z = "2026-05-08T07:57:54.734914+00:00Z-000000-agent"
    assert Entity.version_timestamp(canonical).isoformat() == "2026-06-15T13:37:41.613629+00:00"
    assert Entity.version_timestamp(legacy_z).isoformat() == "2026-05-08T07:57:54.734914+00:00"


def test_conflict_resolver_last_write_wins():
    local = {"updated_at": "2026-06-15T10:00:00+00:00", "version": "a"}
    remote = {"updated_at": "2026-06-15T10:00:05+00:00", "version": "b"}  # 5s newer
    res = ConflictResolver.resolve(local, remote)
    assert res.winner is remote and "newer" in res.reason


def test_conflict_resolver_tiebreak_on_version_within_one_second():
    # Same instant: the lexically greater version must win (not sync_id).
    base = "2026-06-15T10:00:00+00:00"
    local = {"updated_at": base, "version": base + "-000001-alice"}
    remote = {"updated_at": base, "version": base + "-000002-alice"}  # greater
    res = ConflictResolver.resolve(local, remote)
    assert res.winner is remote and "version" in res.reason
    # And symmetric: greater local wins.
    res2 = ConflictResolver.resolve(remote, local)  # now `remote` arg is the greater one
    assert res2.winner is remote


# --------------------------------------------------------------------------- #
# Endpoint tests (isolated DB + sync TestClient)
# --------------------------------------------------------------------------- #
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
    token = client.post("/api/v1/auth/admin/login", json={"password": "admin"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _change(change_type, *, id, version, name="N", content=None,
            etype="device", user="alice", parents=None, rels=None):
    return {
        "change_type": change_type,
        "entity": {
            "id": id, "version": version, "entity_type": etype, "name": name,
            "content": content or {}, "source_type": "manual", "user_id": user,
            "parent_versions": parents or [],
        },
        "relationships": rels or [],
    }


def _rel(id, *, from_id, from_version, to_id, to_version,
         rel_type="located_in", properties=None):
    return {
        "id": id,
        "from_entity_id": from_id, "from_entity_version": from_version,
        "to_entity_id": to_id, "to_entity_version": to_version,
        "relationship_type": rel_type, "properties": properties or {},
    }


def _rel_only_change(rels):
    """A change carrying only edges — its endpoint entities are already in sync."""
    return {"change_type": "update", "entity": None, "relationships": rels}


def _stored_relationships():
    """Read persisted edges straight out of the isolated test DB."""
    async def _read():
        async with dbmod.async_session() as session:
            result = await session.execute(select(EntityRelationship))
            return [r.to_dict() for r in result.scalars().all()]
    return asyncio.run(_read())


def _stored_versions(entity_id):
    """Read every persisted version row for an entity out of the test DB.

    The sync response only ever carries the latest row, so preservation of a
    losing version (ADR-011 §2) is only observable at the database.
    """
    async def _read():
        async with dbmod.async_session() as session:
            result = await session.execute(
                select(Entity).where(Entity.id == entity_id)
            )
            return list(result.scalars().all())
    return asyncio.run(_read())


def _sync(client, headers, sync_type, changes=None, since=None, device="dev1", user="alice"):
    body = {
        "protocol_version": "inbetweenies-v2", "device_id": device, "user_id": user,
        "sync_type": sync_type, "changes": changes or [],
    }
    if since is not None:
        body["filters"] = {"since": since}
    return client.post("/api/v1/sync/", json=body, headers=headers)


def test_sync_requires_auth(client):
    resp = client.post("/api/v1/sync/", json={
        "protocol_version": "inbetweenies-v2", "device_id": "d", "user_id": "u",
        "sync_type": "full", "changes": [],
    })
    assert resp.status_code in (401, 403)


def test_full_sync_returns_server_time_and_created_entity(client, headers):
    eid, ver = "e1", Entity.create_version("alice")
    resp = _sync(client, headers, "full", [_change("create", id=eid, version=ver, name="Lamp")])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["server_time"]  # REQUIRED watermark
    ids = [c["entity"]["id"] for c in data["changes"]]
    assert eid in ids


def test_delta_since_is_exclusive(client, headers):
    # Create A, take server_time, then create B and delta from that watermark.
    va = Entity.create_version("alice")
    r1 = _sync(client, headers, "full", [_change("create", id="A", version=va, name="A")])
    watermark = r1.json()["server_time"]
    time.sleep(0.01)
    vb = Entity.create_version("alice")
    r2 = _sync(client, headers, "delta", [_change("create", id="B", version=vb, name="B")], since=watermark)
    ids = [c["entity"]["id"] for c in r2.json()["changes"]]
    assert "B" in ids       # changed after the watermark
    assert "A" not in ids   # at/below the watermark — excluded (strict >)


def test_update_fast_forward_creates_new_version(client, headers):
    v1 = Entity.create_version("alice")
    _sync(client, headers, "full", [_change("create", id="X", version=v1, name="v1")])
    v2 = Entity.create_version("alice")
    _sync(client, headers, "full",
          [_change("update", id="X", version=v2, name="v2", parents=[v1])])
    # Full sync now reports X at v2 (latest version wins).
    data = _sync(client, headers, "full").json()
    x = [c["entity"] for c in data["changes"] if c["entity"]["id"] == "X"][0]
    assert x["version"] == v2 and x["name"] == "v2"


def test_concurrent_update_conflict_resolved_by_version(client, headers):
    v1 = Entity.create_version("alice")
    _sync(client, headers, "full", [_change("create", id="Y", version=v1, name="v1")])
    v2 = Entity.create_version("alice")
    _sync(client, headers, "full", [_change("update", id="Y", version=v2, name="v2", parents=[v1])])
    # A stale client edits from v1 (never saw v2) with a *greater* version v3.
    v3 = Entity.create_version("alice")
    resp = _sync(client, headers, "full",
                 [_change("update", id="Y", version=v3, name="v3", parents=[v1])])
    conflicts = resp.json()["conflicts"]
    assert conflicts and conflicts[0]["entity_id"] == "Y"
    assert conflicts[0]["resolved_version"] == v3  # greater version wins the tiebreak
    latest = [c["entity"] for c in _sync(client, headers, "full").json()["changes"]
              if c["entity"]["id"] == "Y"][0]
    assert latest["version"] == v3


def test_delete_creates_tombstone_and_propagates(client, headers):
    v1 = Entity.create_version("alice")
    _sync(client, headers, "full", [_change("create", id="Z", version=v1, name="gone")])
    vt = Entity.create_version("alice")
    resp = _sync(client, headers, "full",
                 [_change("delete", id="Z", version=vt, name="gone", parents=[v1])])
    z = [c for c in resp.json()["changes"] if c["entity"]["id"] == "Z"][0]
    assert z["change_type"] == "delete"
    assert z["entity"]["content"].get("deleted") is True


def test_idempotent_resend_is_noop(client, headers):
    v1 = Entity.create_version("alice")
    change = _change("create", id="I", version=v1, name="once")
    _sync(client, headers, "full", [change])
    _sync(client, headers, "full", [change])  # same (id, version) again
    data = _sync(client, headers, "full").json()
    matches = [c for c in data["changes"] if c["entity"]["id"] == "I"]
    assert len(matches) == 1  # not duplicated


# --------------------------------------------------------------------------- #
# Empty parent_versions (§7) — a parentless update over an id we already hold is
# a blind overwrite and must be decided by the conflict rule, never waved through.
# --------------------------------------------------------------------------- #
# Hand-crafted versions whose timestamp prefix is far from "now", so the §7
# last-write-wins comparison is decided by updated_at rather than the 1s tiebreak.
_ANCIENT = "2020-01-01T00:00:00.000000+00:00-000001-alice"
_FUTURE = "2099-01-01T00:00:00.000000+00:00-000001-alice"


def test_parentless_update_over_existing_entity_is_a_conflict(client, headers):
    """Stale blind overwrite: reported as a conflict AND rejected (local wins)."""
    v1 = Entity.create_version("alice")
    _sync(client, headers, "full", [_change("create", id="P", version=v1, name="kept")])

    # No parent_versions at all, and an older version -> local must win.
    resp = _sync(client, headers, "full",
                 [_change("update", id="P", version=_ANCIENT, name="clobbered", parents=[])])
    body = resp.json()

    assert body["conflicts"], "parentless update over an existing id must conflict"
    conflict = body["conflicts"][0]
    assert conflict["entity_id"] == "P"
    assert conflict["local_version"] == v1
    assert conflict["remote_version"] == _ANCIENT
    assert conflict["resolved_version"] == v1
    assert body["sync_stats"]["conflicts_resolved"] == 1

    latest = [c["entity"] for c in _sync(client, headers, "full").json()["changes"]
              if c["entity"]["id"] == "P"][0]
    assert latest["version"] == v1 and latest["name"] == "kept"


def test_parentless_update_that_wins_records_superseded_version(client, headers):
    """A winning blind overwrite still conflicts, and keeps the version DAG linked."""
    v1 = Entity.create_version("alice")
    _sync(client, headers, "full", [_change("create", id="Q", version=v1, name="old")])

    resp = _sync(client, headers, "full",
                 [_change("update", id="Q", version=_FUTURE, name="new", parents=[])])
    conflicts = resp.json()["conflicts"]
    assert conflicts and conflicts[0]["resolved_version"] == _FUTURE

    latest = [c["entity"] for c in _sync(client, headers, "full").json()["changes"]
              if c["entity"]["id"] == "Q"][0]
    assert latest["version"] == _FUTURE and latest["name"] == "new"
    # Stored with the version it superseded, not orphaned with [].
    assert latest["parent_versions"] == [v1]


def test_parentless_create_of_unknown_entity_is_not_a_conflict(client, headers):
    """Guard against over-correcting: a first-ever create legitimately has no parents."""
    v1 = Entity.create_version("alice")
    resp = _sync(client, headers, "full",
                 [_change("create", id="R", version=v1, name="brand new", parents=[])])
    body = resp.json()
    assert body["conflicts"] == []
    assert body["sync_stats"]["conflicts_resolved"] == 0
    assert "R" in [c["entity"]["id"] for c in body["changes"]]


# --------------------------------------------------------------------------- #
# Relationship push (§3.1, §5) — inbound edges must actually be persisted.
# --------------------------------------------------------------------------- #
def test_pushed_relationships_are_persisted(client, headers):
    """Edges in the batch are stored, even when the endpoint arrives later in it."""
    dev_v, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    # The edge hangs off the *first* change but points at the room created by the
    # *second* one: entities must all be applied before any relationship (§5).
    changes = [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", from_version=dev_v,
                           to_id="room1", to_version=room_v,
                           properties={"since": "2026"})]),
        _change("create", id="room1", version=room_v, name="Kitchen", etype="room"),
    ]
    resp = _sync(client, headers, "full", changes)
    assert resp.status_code == 200, resp.text
    assert resp.json()["sync_stats"]["relationships_synced"] == 1

    stored = _stored_relationships()
    assert len(stored) == 1
    assert stored[0]["id"] == "rel1"
    assert stored[0]["from_entity_id"] == "dev1"
    assert stored[0]["from_entity_version"] == dev_v
    assert stored[0]["to_entity_id"] == "room1"
    assert stored[0]["to_entity_version"] == room_v
    assert stored[0]["relationship_type"] == "located_in"
    assert stored[0]["properties"] == {"since": "2026"}


def test_relationship_push_is_idempotent(client, headers):
    """Re-pushing the same edge must not duplicate it or error."""
    dev_v, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    changes = [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", from_version=dev_v,
                           to_id="room1", to_version=room_v)]),
        _change("create", id="room1", version=room_v, name="Kitchen", etype="room"),
    ]
    first = _sync(client, headers, "full", changes)
    second = _sync(client, headers, "full", changes)  # byte-identical re-push

    assert first.status_code == 200 and second.status_code == 200, second.text
    assert second.json()["sync_stats"]["relationships_synced"] == 1
    assert len(_stored_relationships()) == 1  # not duplicated


def test_relationship_repush_follows_new_entity_version(client, headers):
    """Relationships are not versioned: the same edge id re-points at new versions."""
    dev_v1, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v1, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", from_version=dev_v1,
                           to_id="room1", to_version=room_v)]),
        _change("create", id="room1", version=room_v, name="Kitchen", etype="room"),
    ])

    # Device gets a new version; the client re-pushes the same edge id against it.
    dev_v2 = Entity.create_version("alice")
    resp = _sync(client, headers, "full", [
        _change("update", id="dev1", version=dev_v2, name="Lamp", etype="device",
                parents=[dev_v1],
                rels=[_rel("rel1", from_id="dev1", from_version=dev_v2,
                           to_id="room1", to_version=room_v)]),
    ])
    assert resp.status_code == 200, resp.text

    stored = _stored_relationships()
    assert len(stored) == 1  # still one edge, moved rather than duplicated
    assert stored[0]["from_entity_version"] == dev_v2


def test_relationship_with_missing_endpoint_is_skipped(client, headers):
    """A dangling edge is dropped, not persisted and not fatal (composite FK)."""
    dev_v = Entity.create_version("alice")
    resp = _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", from_version=dev_v,
                           to_id="nope", to_version="no-such-version")]),
    ])
    assert resp.status_code == 200, resp.text
    assert resp.json()["sync_stats"]["relationships_synced"] == 0
    assert _stored_relationships() == []


def test_relationship_referencing_stale_entity_version_is_skipped(client, headers):
    """The FK is on (entity_id, entity_version) — a known id at an unknown
    version is still dangling."""
    dev_v, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    resp = _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", from_version="never-stored",
                           to_id="room1", to_version=room_v)]),
        _change("create", id="room1", version=room_v, name="Kitchen", etype="room"),
    ])
    assert resp.status_code == 200, resp.text
    assert resp.json()["sync_stats"]["relationships_synced"] == 0
    assert _stored_relationships() == []


def test_unknown_relationship_type_is_rejected(client, headers):
    """Malformed input gets a 400, matching the protocol_version check."""
    dev_v, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    resp = _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", from_version=dev_v,
                           to_id="room1", to_version=room_v,
                           rel_type="teleports_to")]),
        _change("create", id="room1", version=room_v, name="Kitchen", etype="room"),
    ])
    assert resp.status_code == 400
    assert "teleports_to" in resp.json()["detail"]
    assert _stored_relationships() == []


# --------------------------------------------------------------------------- #
# Per-id acknowledgement — the client clears pending marks from `applied` /
# `applied_relationships`, so an id may only appear once it genuinely landed.
# --------------------------------------------------------------------------- #
def test_push_reports_applied_ids(client, headers):
    dev_v, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    resp = _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", from_version=dev_v,
                           to_id="room1", to_version=room_v)]),
        _change("create", id="room1", version=room_v, name="Kitchen", etype="room"),
    ])
    body = resp.json()
    assert sorted(body["applied"]) == ["dev1", "room1"]
    assert body["applied_relationships"] == ["rel1"]
    # Counts agree with the acknowledgement lists.
    assert body["sync_stats"]["entities_synced"] == 2
    assert body["sync_stats"]["relationships_synced"] == 1


def test_losing_change_is_acked_so_the_client_stops_retrying(client, headers):
    """A change that LOSES resolution is still acknowledged (ADR-011 §2).

    This reverses the earlier rule that a loser stayed unacked to force a
    retry. That was safe only while clients applied every pulled change. A
    client implementing the ADR-011 §1 pull-guard (KittenKong does) livelocks
    under it: the guard blocks our version because the id is pending, the push
    loses and is not acked, the pending mark survives, and every later sync
    repeats identically -- the entity never converges on that client.

    Losing is terminal. Retrying cannot change it, so it is acknowledged.
    """
    v1 = Entity.create_version("alice")
    _sync(client, headers, "full", [_change("create", id="P", version=v1, name="kept")])

    resp = _sync(client, headers, "full",
                 [_change("update", id="P", version=_ANCIENT, name="clobbered", parents=[])])
    body = resp.json()

    assert body["conflicts"], "the losing overwrite must still be reported"
    assert "P" in body["applied"], "a loser is processed, so it is acked"

    # Acked, but it did NOT win: the served latest is unchanged.
    served = {c["entity"]["id"]: c["entity"] for c in body["changes"] if c.get("entity")}
    assert served["P"]["name"] == "kept"


def test_losing_version_is_preserved_in_history(client, headers):
    """Acking a loser is only safe if its content survives (ADR-011 §2).

    Ack without preservation would be worse than the livelock it fixes: the
    client drops its pending mark, later pulls the winner over its own edit,
    and the losing content is gone everywhere.
    """
    v1 = Entity.create_version("alice")
    _sync(client, headers, "full", [_change("create", id="R", version=v1, name="kept")])
    _sync(client, headers, "full",
          [_change("update", id="R", version=_ANCIENT, name="lost-but-recoverable", parents=[])])

    versions = _stored_versions("R")
    names = {v.version: v.name for v in versions}
    assert _ANCIENT in names, "the losing version row must be recoverable from history"
    assert names[_ANCIENT] == "lost-but-recoverable"
    assert names[v1] == "kept"


def test_losing_version_that_would_sort_latest_is_not_promoted(client, headers):
    """The preservation guard: never let a loser become the served latest.

    Resolution is LWW on updated_at; _latest_entities() picks the lexically
    greatest version string. They can disagree, and where they do, inserting
    the loser would silently promote it. Such a row is skipped (and logged)
    rather than corrupting state -- it is still acked and still reported.
    """
    old_edit_time = Entity.create_version("alice")
    _sync(client, headers, "full",
          [_change("create", id="S", version=old_edit_time, name="kept")])

    # Sorts ABOVE the stored version, but loses LWW because the stored row's
    # updated_at (its server insert time) is later than this claimed edit time.
    later_sorting = Entity.create_version("bob")
    resp = _sync(client, headers, "full",
                 [_change("update", id="S", version=later_sorting, name="must-not-win",
                          parents=[])])
    body = resp.json()

    served = {c["entity"]["id"]: c["entity"] for c in body["changes"] if c.get("entity")}
    if served["S"]["name"] == "kept":
        # It lost: it must be acked, and must NOT have been stored.
        assert "S" in body["applied"]
        assert later_sorting not in {v.version for v in _stored_versions("S")}
    else:
        # It won on time ordering; then it is simply the new latest.
        assert served["S"]["name"] == "must-not-win"


def test_conflict_winner_is_reported_as_applied(client, headers):
    """The other side of the same rule: a winning remote IS acknowledged."""
    v1 = Entity.create_version("alice")
    _sync(client, headers, "full", [_change("create", id="Q", version=v1, name="old")])

    resp = _sync(client, headers, "full",
                 [_change("update", id="Q", version=_FUTURE, name="new", parents=[])])
    body = resp.json()
    assert body["conflicts"] and body["applied"] == ["Q"]


def test_idempotent_repush_is_still_reported_as_applied(client, headers):
    """Already in the desired state counts as applied, or the client retries forever."""
    v1 = Entity.create_version("alice")
    change = _change("create", id="I", version=v1, name="once")
    assert _sync(client, headers, "full", [change]).json()["applied"] == ["I"]
    assert _sync(client, headers, "full", [change]).json()["applied"] == ["I"]


def test_delete_of_unknown_entity_is_reported_as_applied(client, headers):
    """Nothing to delete: the intent already holds, so acknowledge it."""
    vt = Entity.create_version("alice")
    body = _sync(client, headers, "full",
                 [_change("delete", id="ghost", version=vt, name="ghost")]).json()
    assert body["applied"] == ["ghost"]


def test_skipped_dangling_relationship_is_not_reported_as_applied(client, headers):
    """A skipped edge must stay pending so the client retries once the endpoint lands."""
    dev_v = Entity.create_version("alice")
    body = _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", from_version=dev_v,
                           to_id="nope", to_version="no-such-version")]),
    ]).json()
    assert body["applied"] == ["dev1"]          # the entity did land
    assert body["applied_relationships"] == []  # the edge did not


def test_relationship_only_change_without_entity(client, headers):
    """`entity: None` carrying only edges must not crash, and must be acknowledged."""
    dev_v, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device"),
        _change("create", id="room1", version=room_v, name="Kitchen", etype="room"),
    ])

    # Endpoints already in sync — a later push carries the edge on its own.
    resp = _sync(client, headers, "full", [
        _rel_only_change([_rel("rel1", from_id="dev1", from_version=dev_v,
                               to_id="room1", to_version=room_v)]),
    ])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] == []  # no entity id to acknowledge
    assert body["applied_relationships"] == ["rel1"]
    assert len(_stored_relationships()) == 1
