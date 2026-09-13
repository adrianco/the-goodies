"""Spec-correctness tests for the inbetweenies-v3 sync protocol (PROTOCOL.md).

Synchronous throughout: pure-function units for the version string + canonical
conflict resolver, and endpoint tests driven through a sync TestClient over an
isolated NullPool database (see test_backup for why the shared engine is patched).
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from fastapi.testclient import TestClient

import funkygibbon.database as dbmod
from funkygibbon.config import settings
from funkygibbon.api.app import create_app
from funkygibbon.api.sync import _to_utc
from funkygibbon.repositories.graph import GraphRepository
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


def _rel(id, *, from_id, to_id, rel_type="located_in", properties=None,
         valid_from=None, valid_to=None):
    """One edge interval, as it travels on the wire (ADR-004 §6).

    ``from_version``/``to_version`` used to be required here and were then
    thrown away by the body — vestigial arguments from the pinned-edge era that
    every call site still had to invent a value for. ``valid_from``/``valid_to``
    replace them and are genuinely read: they are what makes an edge end, and
    they carry the client's edit time onto the valid-time axis.
    """
    edge = {
        "id": id,
        "from_entity_id": from_id,
        "to_entity_id": to_id,
        "relationship_type": rel_type, "properties": properties or {},
    }
    if valid_from is not None:
        edge["valid_from"] = valid_from.isoformat()
    if valid_to is not None:
        edge["valid_to"] = valid_to.isoformat()
    return edge


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


def _stored_relationship_rows():
    """Persisted edges as ORM objects, so interval predicates can be applied.

    `_stored_relationships()` returns to_dict() output, which is the right shape
    for asserting on wire fields but loses `is_current_at`.
    """
    async def _read():
        async with dbmod.async_session() as session:
            result = await session.execute(select(EntityRelationship))
            return list(result.scalars().all())
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
        "protocol_version": "inbetweenies-v3", "device_id": device, "user_id": user,
        "sync_type": sync_type, "changes": changes or [],
    }
    if since is not None:
        body["filters"] = {"since": since}
    return client.post("/api/v1/sync/", json=body, headers=headers)


def test_sync_requires_auth(client):
    resp = client.post("/api/v1/sync/", json={
        "protocol_version": "inbetweenies-v3", "device_id": "d", "user_id": "u",
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
    latest = [c["entity"] for c in _sync(client, headers, "full").json()["changes"]
              if c["entity"]["id"] == "Y"][0]
    # ADR-005 §2: the two edits share v1, so they are MERGED (rung 3). Both
    # changed `name`, so that key is settled by the ordering rule (rung 4) --
    # v3 is later, so its name wins -- and the result is a server-authored
    # merge version with both edits as parents, not v3 itself.
    assert conflicts[0]["resolved_version"] == latest["version"]
    assert latest["name"] == "v3"
    assert set(latest["parent_versions"]) == {v2, v3}
    assert "lww:name" in conflicts[0]["resolution_strategy"]


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
                rels=[_rel("rel1", from_id="dev1", to_id="room1",
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
    assert stored[0]["to_entity_id"] == "room1"
    assert stored[0]["relationship_type"] == "located_in"
    assert stored[0]["properties"] == {"since": "2026"}


def test_relationship_push_is_idempotent(client, headers):
    """Re-pushing the same edge must not duplicate it or error."""
    dev_v, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    changes = [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", to_id="room1")]),
        _change("create", id="room1", version=room_v, name="Kitchen", etype="room"),
    ]
    first = _sync(client, headers, "full", changes)
    second = _sync(client, headers, "full", changes)  # byte-identical re-push

    assert first.status_code == 200 and second.status_code == 200, second.text
    assert second.json()["sync_stats"]["relationships_synced"] == 1
    assert len(_stored_relationships()) == 1  # not duplicated


def test_relationship_repush_follows_new_entity_version(client, headers):
    """An endpoint version bump leaves the edge alone (ADR-004 §1).

    This used to read "the same edge id re-points at new versions", which
    described the pinned-edge behaviour: the edge carried its endpoints'
    versions, so bumping one rewrote the edge. It no longer does — an edge
    references entity IDs, and the version an endpoint resolves to is a function
    of time. So the assertion below is unchanged and its reason is the opposite
    one: still a single row not because the re-point was absorbed, but because
    nothing about the edge changed and no new interval was opened.
    """
    dev_v1, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v1, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", to_id="room1")]),
        _change("create", id="room1", version=room_v, name="Kitchen", etype="room"),
    ])

    # Device gets a new version; the client re-pushes the same edge id against it.
    dev_v2 = Entity.create_version("alice")
    resp = _sync(client, headers, "full", [
        _change("update", id="dev1", version=dev_v2, name="Lamp", etype="device",
                parents=[dev_v1],
                rels=[_rel("rel1", from_id="dev1", to_id="room1")]),
    ])
    assert resp.status_code == 200, resp.text

    stored = _stored_relationships()
    assert len(stored) == 1  # still one edge, moved rather than duplicated


def test_relationship_with_missing_endpoint_is_skipped(client, headers):
    """A dangling edge is dropped, not persisted and not fatal.

    The endpoint check is by id now, not by (id, version) — there is no
    composite FK left to violate (ADR-004 §1). An unknown endpoint id still
    means the entity has not reached us yet, so the edge is skipped and the
    shortfall reported rather than failing the batch.
    """
    dev_v = Entity.create_version("alice")
    resp = _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", to_id="nope")]),
    ])
    assert resp.status_code == 200, resp.text
    assert resp.json()["sync_stats"]["relationships_synced"] == 0
    assert _stored_relationships() == []


def test_unknown_relationship_type_is_rejected(client, headers):
    """Malformed input gets a 400, matching the protocol_version check."""
    dev_v, room_v = Entity.create_version("alice"), Entity.create_version("alice")
    resp = _sync(client, headers, "full", [
        _change("create", id="dev1", version=dev_v, name="Lamp", etype="device",
                rels=[_rel("rel1", from_id="dev1", to_id="room1",
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
                rels=[_rel("rel1", from_id="dev1", to_id="room1")]),
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
                rels=[_rel("rel1", from_id="dev1", to_id="nope")]),
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
        _rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")]),
    ])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] == []  # no entity id to acknowledge
    assert body["applied_relationships"] == ["rel1"]
    assert len(_stored_relationships()) == 1


# ======================================================================
# ADR-004 §1/§6 — the edge write path
#
# tests/test_interval_edges.py covers the interval predicate on an
# in-memory object. Everything below drives the same rules through the
# server, because the predicate being right is not the same claim as the
# write path producing rows it holds over. Every test here failed before
# the fixes it pins, and each names the wrong answer it prevents.
# ======================================================================

def _intervals(rel_id="rel1"):
    """Every stored interval of one edge, oldest first."""
    rows = [r for r in _stored_relationships() if r["id"] == rel_id]
    return sorted(rows, key=lambda r: r["valid_from"] or "")


def _two_rooms(client, headers):
    """A lamp and two rooms, all synced. Returns nothing; ids are fixed."""
    versions = [Entity.create_version("alice") for _ in range(3)]
    _sync(client, headers, "full", [
        _change("create", id="dev1", version=versions[0], name="Lamp", etype="device"),
        _change("create", id="room1", version=versions[1], name="Kitchen", etype="room"),
        _change("create", id="room2", version=versions[2], name="Hall", etype="room"),
    ])


class TestEndAndInsert:
    """Moving an edge must ADD history, never overwrite it (review finding C4)."""

    def test_repointing_an_edge_ends_the_old_row_and_opens_a_new_one(self, client, headers):
        _two_rooms(client, headers)
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])])
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room2")])])

        rows = _intervals()
        assert len(rows) == 2, "the move overwrote history instead of appending to it"

        old, new = rows
        assert old["to_entity_id"] == "room1"
        assert old["valid_to"] is not None, "the superseded row was left open"
        assert new["to_entity_id"] == "room2"
        assert new["valid_to"] is None

    def test_the_handover_instant_is_shared_so_exactly_one_edge_is_current(self, client, headers):
        """Half-open intervals only tile if the boundary is ONE instant.

        Ending the old row at its own `now` and starting the new one at a later
        `now` leaves a gap in which the device is in no room at all.
        """
        _two_rooms(client, headers)
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])])
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room2")])])

        old, new = _intervals()
        assert old["valid_to"] == new["valid_from"]

    def test_prior_placement_is_still_answerable_after_the_move(self, client, headers):
        """The whole point of ADR-004: 'where was it in March?' survives the move.

        Driven with explicit client times rather than back-to-back syncs, so the
        two intervals are months wide and "some instant while it was in the
        kitchen" is a real point rather than a millisecond either side of a
        boundary — which is also how this actually happens: a device installed
        in March and moved in June.
        """
        _two_rooms(client, headers)
        march = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        june = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

        _sync(client, headers, "full", [
            _rel_only_change([
                _rel("rel1", from_id="dev1", to_id="room1", valid_from=march)
            ]),
        ])
        _sync(client, headers, "full", [
            _rel_only_change([
                _rel("rel1", from_id="dev1", to_id="room2", valid_from=june)
            ]),
        ])

        rows = _stored_relationship_rows()
        in_april = [r.to_entity_id for r in rows
                    if r.is_current_at(datetime(2026, 4, 1, tzinfo=timezone.utc))]
        in_july = [r.to_entity_id for r in rows
                   if r.is_current_at(datetime(2026, 7, 1, tzinfo=timezone.utc))]

        assert in_april == ["room1"], "the March placement was destroyed by the move"
        assert in_july == ["room2"]

    def test_no_instant_has_two_current_placements(self, client, headers):
        """Half-open intervals must tile: exactly one edge live at every point,
        including the handover instant itself."""
        _two_rooms(client, headers)
        march = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        june = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        _sync(client, headers, "full", [_rel_only_change(
            [_rel("rel1", from_id="dev1", to_id="room1", valid_from=march)])])
        _sync(client, headers, "full", [_rel_only_change(
            [_rel("rel1", from_id="dev1", to_id="room2", valid_from=june)])])

        rows = _stored_relationship_rows()
        for moment in (march, june, june + timedelta(days=1)):
            live = [r for r in rows if r.is_current_at(moment)]
            assert len(live) == 1, f"{len(live)} edges current at {moment}"

    def test_an_unchanged_repush_does_not_shred_the_edge_into_slivers(self, client, headers):
        _two_rooms(client, headers)
        edge = _rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])
        for _ in range(3):
            _sync(client, headers, "full", [edge])

        assert len(_intervals()) == 1

    def test_a_reattribution_is_a_real_change(self, client, headers):
        """user_id is part of what the edge says, and was omitted from the
        content comparison — so an edge changing hands compared equal and the
        new attribution was silently discarded."""
        _two_rooms(client, headers)
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])],
              user="alice")
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])],
              user="bob")

        rows = _intervals()
        assert len(rows) == 2
        assert [r["user_id"] for r in rows] == ["alice", "bob"]


class TestTheWireCarriesTheInterval:
    """ADR-004 §2/§6: valid_from/valid_to are read, not decorative."""

    def test_a_client_supplied_valid_to_ends_the_edge(self, client, headers):
        """Deleting an edge is an ordinary change carrying `valid_to`.

        The server used to ignore both interval fields, so an end-event was
        indistinguishable from an unchanged re-push: the idempotence guard
        swallowed it and the edge stayed open forever. Edge deletion was simply
        not expressible on the wire.
        """
        _two_rooms(client, headers)
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])])
        assert _intervals()[0]["valid_to"] is None

        ended_at = datetime.now(timezone.utc) + timedelta(minutes=1)
        resp = _sync(client, headers, "full", [
            _rel_only_change([
                _rel("rel1", from_id="dev1", to_id="room1", valid_to=ended_at)
            ]),
        ])
        assert resp.status_code == 200, resp.text
        assert resp.json()["applied_relationships"] == ["rel1"]

        rows = _intervals()
        assert len(rows) == 1, "ending an edge must close a row, not open one"
        assert rows[0]["valid_to"] is not None

    def test_the_clients_edit_time_becomes_valid_from(self, client, headers):
        """ADR-004 §2: the as-of axis is client time, stored verbatim.

        An edit made offline at 14:00 and synced at 18:00 belongs at 14:00.
        Stamping the server's clock put every historical answer off by the sync
        lag the temporal model exists to absorb.
        """
        _two_rooms(client, headers)
        edited_at = datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)
        _sync(client, headers, "full", [
            _rel_only_change([
                _rel("rel1", from_id="dev1", to_id="room1", valid_from=edited_at)
            ]),
        ])

        stored = datetime.fromisoformat(_intervals()[0]["valid_from"])
        assert _to_utc(stored) == edited_at

    def test_an_end_can_never_precede_its_own_start(self, client, headers):
        """A lagging or lying client clock must not mint a negative interval."""
        _two_rooms(client, headers)
        started = datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)
        _sync(client, headers, "full", [
            _rel_only_change([
                _rel("rel1", from_id="dev1", to_id="room1", valid_from=started)
            ]),
        ])
        _sync(client, headers, "full", [
            _rel_only_change([
                _rel("rel1", from_id="dev1", to_id="room1",
                     valid_to=started - timedelta(days=30))
            ]),
        ])

        row = _intervals()[0]
        assert _to_utc(datetime.fromisoformat(row["valid_to"])) >= started

    def test_a_closed_interval_for_an_unseen_edge_is_backfilled(self, client, headers):
        """A replica that missed the live window still converges on the history."""
        _two_rooms(client, headers)
        began = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        ended = datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc)
        resp = _sync(client, headers, "full", [
            _rel_only_change([
                _rel("rel1", from_id="dev1", to_id="room1",
                     valid_from=began, valid_to=ended)
            ]),
        ])
        assert resp.json()["applied_relationships"] == ["rel1"]

        rows = _intervals()
        assert len(rows) == 1
        assert rows[0]["valid_to"] is not None

    def test_replaying_an_identical_interval_is_idempotent(self, client, headers):
        """(id, valid_from) is the primary key, so a replayed change would
        otherwise raise IntegrityError and fail the whole batch (ADR-011 §3)."""
        _two_rooms(client, headers)
        began = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        change = _rel_only_change([
            _rel("rel1", from_id="dev1", to_id="room1", valid_from=began)
        ])
        for _ in range(3):
            resp = _sync(client, headers, "full", [change])
            assert resp.status_code == 200, resp.text

        assert len(_intervals()) == 1


class TestCurrentGraphExcludesRetiredEdges:
    """ADR-004 §1: a retired interval is history, never state."""

    def test_a_moved_device_is_in_exactly_one_room(self, client, headers):
        """The currency filter was gated on an endpoint filter being supplied,
        so an unfiltered read — which is the one GraphIndex performs — returned
        both the old and the new placement as live edges."""
        _two_rooms(client, headers)
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])])
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room2")])])

        async def _read():
            async with dbmod.async_session() as session:
                repo = GraphRepository(session)
                unfiltered = await repo.get_relationships()
                history = await repo.get_relationships(include_all_versions=True)
                return unfiltered, history

        unfiltered, history = asyncio.run(_read())
        assert [r.to_entity_id for r in unfiltered] == ["room2"]
        assert len(history) == 2, "history must still be reachable on request"


class TestStateDigestCoversTopology:
    """ADR-011 §4: the convergence check must see the half ADR-004 changed."""

    def test_moving_an_edge_changes_the_digest(self, client, headers):
        """Hashing only entity (id, version) left topology outside the check:
        two replicas could disagree about every device's room and still agree
        on the digest, so the one mechanism meant to catch silent divergence
        was blind to exactly this."""
        _two_rooms(client, headers)
        before = _sync(client, headers, "full",
                       [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])]
                       ).json()["state_digest"]
        after = _sync(client, headers, "full",
                      [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room2")])]
                      ).json()["state_digest"]

        assert before != after

    def test_an_unchanged_graph_keeps_its_digest(self, client, headers):
        _two_rooms(client, headers)
        edge = _rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])
        first = _sync(client, headers, "full", [edge]).json()["state_digest"]
        second = _sync(client, headers, "full", [edge]).json()["state_digest"]

        assert first == second


class TestThePullCarriesEdges:
    """ADR-005 §3: the delta stream carries every immutable row.

    The pull direction never mentioned a relationship — `SyncChange.relationships`
    was populated inbound and left empty outbound — so a client could push
    topology and never learn any. A fresh replica synced every entity in the
    house and no edges between them, which makes "clients hold the whole graph"
    true of the nodes only.
    """

    def _edges_in(self, body):
        return [rel for change in body["changes"] for rel in change["relationships"]]

    def test_a_full_sync_returns_the_edges_as_well_as_the_entities(self, client, headers):
        _two_rooms(client, headers)
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])])

        edges = self._edges_in(_sync(client, headers, "full").json())
        assert [e["id"] for e in edges] == ["rel1"]
        assert edges[0]["to_entity_id"] == "room1"

    def test_the_interval_bounds_travel_verbatim(self, client, headers):
        """ADR-004 §2: a replica that recomputed these locally would disagree
        with every other replica about the past."""
        _two_rooms(client, headers)
        march = datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)
        _sync(client, headers, "full", [
            _rel_only_change([
                _rel("rel1", from_id="dev1", to_id="room1", valid_from=march)
            ]),
        ])

        edge = self._edges_in(_sync(client, headers, "full").json())[0]
        assert _to_utc(datetime.fromisoformat(edge["valid_from"])) == march
        assert edge["valid_to"] is None

    def test_retired_intervals_travel_too(self, client, headers):
        """Not a latest-per-id projection: a replica that only received open
        intervals could answer "where is it now?" and nothing else, which is the
        whole capability the temporal model exists to provide."""
        _two_rooms(client, headers)
        march = datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)
        june = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
        _sync(client, headers, "full", [_rel_only_change(
            [_rel("rel1", from_id="dev1", to_id="room1", valid_from=march)])])
        _sync(client, headers, "full", [_rel_only_change(
            [_rel("rel1", from_id="dev1", to_id="room2", valid_from=june)])])

        edges = self._edges_in(_sync(client, headers, "full").json())
        assert len(edges) == 2, "history was projected away on the wire"
        assert sorted(e["to_entity_id"] for e in edges) == ["room1", "room2"]

    def test_an_edge_rides_the_change_for_its_source_entity(self, client, headers):
        """PROTOCOL.md §3.1/§5: bundling the edge onto its source entity's
        change is what makes 'entities before relationships' satisfiable within
        one batch."""
        _two_rooms(client, headers)
        _sync(client, headers, "full",
              [_rel_only_change([_rel("rel1", from_id="dev1", to_id="room1")])])

        body = _sync(client, headers, "full").json()
        carrier = [c for c in body["changes"] if c["relationships"]]
        assert len(carrier) == 1
        assert carrier[0]["entity"]["id"] == "dev1"

    def test_no_edges_means_no_relationship_payload(self, client, headers):
        _two_rooms(client, headers)
        assert self._edges_in(_sync(client, headers, "full").json()) == []


class TestRelationshipToolsOverMcp:
    """Issue #85 / ADR-015: everything a client does to the graph is a tool.

    Driven through /api/v1/mcp/tools/<name> -- the transport every client
    uses -- not through the graph REST routes, which are oook's maintenance
    surface.
    """

    def _tool(self, client, headers, tool_name, **args):
        resp = client.post(f"/api/v1/mcp/tools/{tool_name}", headers=headers, json={"arguments": args})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "error" not in body, body
        return body["result"]

    def _seed_edge(self, client, headers, to="room1", valid_from=None):
        _two_rooms(client, headers)
        rel = _rel("rel1", from_id="dev1", to_id=to, valid_from=valid_from)
        _sync(client, headers, "full", [_rel_only_change([rel])])

    def test_list_relationships_enumerates_the_current_graph(self, client, headers):
        self._seed_edge(client, headers)
        out = self._tool(client, headers, "list_relationships", from_entity_id="dev1")
        assert out["count"] == 1 and out["relationships"][0]["to_entity_id"] == "room1"

    def test_end_relationship_is_the_delete_and_keeps_history(self, client, headers):
        self._seed_edge(client, headers)
        out = self._tool(client, headers, "end_relationship", relationship_id="rel1", reason="mis-recorded")
        assert out["ended_at"] is not None and out["reason"] == "mis-recorded"

        current = self._tool(client, headers, "list_relationships", from_entity_id="dev1")
        assert current["count"] == 0, "an ended edge is not part of the current graph"
        history = self._tool(client, headers, "list_relationships", from_entity_id="dev1", include_history=True)
        assert history["count"] == 1 and history["relationships"][0]["valid_to"] is not None

        # Idempotent: ending again is a no-op that says so.
        again = self._tool(client, headers, "end_relationship", relationship_id="rel1")
        assert again["already_ended"] is True

    def test_end_relationship_leaves_the_index_immediately(self, client, headers):
        """ADR-003 decision 2: the write and the index update share a code path."""
        self._seed_edge(client, headers)
        self._tool(client, headers, "end_relationship", relationship_id="rel1")
        stats = self._tool(client, headers, "get_statistics")
        assert stats["total_relationships"] == 0

    def test_get_connected_is_the_generic_neighbourhood(self, client, headers):
        self._seed_edge(client, headers)
        out = self._tool(client, headers, "get_connected", entity_id="room1")
        assert out["count"] == 1
        assert out["connected"][0]["direction"] == "incoming"
        assert out["connected"][0]["entity"]["id"] == "dev1"

    def test_an_ended_edge_replicates_as_an_end_event(self, client, headers):
        """The tool's effect reaches a replica: the pull carries the ended row."""
        self._seed_edge(client, headers)
        self._tool(client, headers, "end_relationship", relationship_id="rel1")
        body = _sync(client, headers, "full").json()
        rows = [r for c in body["changes"] for r in c["relationships"] if r["id"] == "rel1"]
        assert len(rows) == 1 and rows[0]["valid_to"] is not None

    def test_as_of_reads_answer_for_the_past(self, client, headers):
        """ADR-004 §3: `at` on a read tool, over the wire.

        The entities are created with versions stamped in January: an entity
        is only "there" at T if a version of it existed by T (§3.2), so a room
        created today has no April state at all -- the first draft of this
        test tripped exactly that, which is the model being right.
        """
        march = datetime(2026, 3, 1, 12, tzinfo=timezone.utc)
        june = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
        jan = "2026-01-01T00:00:00.000000+00:00-000001-alice"
        _sync(client, headers, "full", [
            _change("create", id="dev1", version=jan, name="Lamp", etype="device"),
            _change("create", id="room1", version=jan, name="Kitchen", etype="room"),
            _change("create", id="room2", version=jan, name="Hall", etype="room"),
        ])
        _sync(client, headers, "full", [_rel_only_change([
            _rel("rel1", from_id="dev1", to_id="room1", valid_from=march)])])
        _sync(client, headers, "full", [_rel_only_change([
            _rel("rel1", from_id="dev1", to_id="room2", valid_from=june)])])

        april = self._tool(client, headers, "list_relationships", from_entity_id="dev1",
                           at="2026-04-01T00:00:00Z")
        july = self._tool(client, headers, "list_relationships", from_entity_id="dev1",
                          at="2026-07-01T00:00:00Z")
        assert [r["to_entity_id"] for r in april["relationships"]] == ["room1"]
        assert [r["to_entity_id"] for r in july["relationships"]] == ["room2"]

        devices_then = self._tool(client, headers, "get_devices_in_room", room_id="room1",
                                  at="2026-04-01T00:00:00Z")
        assert [d["id"] for d in devices_then["devices"]] == ["dev1"]
        devices_now = self._tool(client, headers, "get_devices_in_room", room_id="room1")
        assert devices_now["devices"] == []

    def test_get_graph_diff_reports_the_move(self, client, headers):
        march = datetime(2026, 3, 1, 12, tzinfo=timezone.utc)
        june = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
        self._seed_edge(client, headers, to="room1", valid_from=march)
        _sync(client, headers, "full", [_rel_only_change([
            _rel("rel1", from_id="dev1", to_id="room2", valid_from=june)])])

        out = self._tool(client, headers, "get_graph_diff",
                         since="2026-05-01T00:00:00Z", until="2026-07-01T00:00:00Z")
        assert [e["to_entity_id"] for e in out["edges_started"]] == ["room2"]
        assert [e["to_entity_id"] for e in out["edges_ended"]] == ["room1"]

    def test_the_catalog_advertises_the_new_tools(self, client, headers):
        tools = {t["name"] for t in client.get("/api/v1/mcp/tools", headers=headers).json()["tools"]}
        assert {"list_relationships", "get_connected", "end_relationship", "get_graph_diff"} <= tools
