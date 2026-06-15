"""Spec-correctness tests for the inbetweenies-v2 sync protocol (PROTOCOL.md).

Synchronous throughout: pure-function units for the version string + canonical
conflict resolver, and endpoint tests driven through a sync TestClient over an
isolated NullPool database (see test_backup for why the shared engine is patched).
"""

import asyncio
import time

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from fastapi.testclient import TestClient

import funkygibbon.database as dbmod
from funkygibbon.config import settings
from funkygibbon.api.app import create_app
from inbetweenies.models import Entity
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
            etype="device", user="alice", parents=None):
    return {
        "change_type": change_type,
        "entity": {
            "id": id, "version": version, "entity_type": etype, "name": name,
            "content": content or {}, "source_type": "manual", "user_id": user,
            "parent_versions": parents or [],
        },
        "relationships": [],
    }


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
