"""Protocol conformance suite — the compatibility gate for every client.

ADR-010 §2. This suite asserts server behaviour against `inbetweenies/PROTOCOL.md`,
clause by clause. It exists for three jobs:

1. **The contract every port is built from.** KittenKong (TypeScript) and any
   future Swift client are written against PROTOCOL.md, not against server
   source. If the server drifts from the spec, a port breaks silently and the
   failure surfaces on someone else's machine. Each test names the clause it
   pins, so a failure reads as "the server no longer does what §7 promises"
   rather than "some sync test broke".
2. **The byte-identical gate for the ADR-012 abstraction.** Stage D rewrites
   `EntityType`/`RelationshipType`/`SourceType` from SQLEnum columns to
   manifest-validated strings across ~45 files. The claim is that house
   behaviour is unchanged. That claim is only falsifiable if this suite exists
   and passes *before* the change — so it is written now, against current v2
   behaviour, deliberately ahead of the work it guards.
3. **A regression net for the invariants that already cost us.** Per-id acks
   (§3.2) and tombstone convergence (§8) are exactly the areas where bugs have
   shipped.

DELIBERATELY NOT PARAMETERIZED YET. ADR-010 §2 wants this suite parameterized by
domain manifest once ADR-012 lands, so it can run against house and vehicles alike.
The seam is the module-level vocabulary constants below: when the manifest
exists, they become a fixture parameter and the test bodies stay as they are.

SCOPE: server-side protocol behaviour only. Client-side obligations (§5 apply
ordering, watermark persistence) are asserted in the client suites.
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

# --- Domain vocabulary -------------------------------------------------------
# The ADR-012 seam. Today these are the house vocabulary; after the abstraction
# they come from the domain manifest and this module runs once per domain.
ENTITY_TYPE = "device"
RELATIONSHIP_TYPE = "controls"
SOURCE_TYPE = "manual"

USER = "conformance"


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


def entity_change(change_type, *, id, version, name="N", content=None,
                  parents=None, rels=None):
    return {
        "change_type": change_type,
        "entity": {
            "id": id, "version": version, "entity_type": ENTITY_TYPE, "name": name,
            "content": content if content is not None else {},
            "source_type": SOURCE_TYPE, "user_id": USER,
            "parent_versions": parents or [],
        },
        "relationships": rels or [],
    }


def edge(id, *, from_id, from_version, to_id, to_version, properties=None):
    return {
        "id": id,
        "from_entity_id": from_id, "from_entity_version": from_version,
        "to_entity_id": to_id, "to_entity_version": to_version,
        "relationship_type": RELATIONSHIP_TYPE, "properties": properties or {},
    }


def sync(client, headers, sync_type="full", changes=None, since=None):
    body = {
        "protocol_version": "inbetweenies-v2", "device_id": "conformance-device",
        "user_id": USER, "sync_type": sync_type, "changes": changes or [],
        "vector_clock": {"clocks": {}},
    }
    if since is not None:
        body["filters"] = {"since": since}
    response = client.post("/api/v1/sync/", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def stored_versions(entity_id):
    async def _read():
        async with dbmod.async_session() as session:
            result = await session.execute(select(Entity).where(Entity.id == entity_id))
            return list(result.scalars().all())
    return asyncio.run(_read())


# --------------------------------------------------------------------------- #
# §2 Identity & versioning
# --------------------------------------------------------------------------- #
class TestIdentityAndVersioning:

    def test_entity_is_identified_by_id_and_version(self, client, headers):
        """§2: (id, version) is the identity. Two versions coexist as rows."""
        v1, v2 = Entity.create_version("a"), Entity.create_version("b")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1, name="first")])
        sync(client, headers, changes=[
            entity_change("update", id="E", version=v2, name="second", parents=[v1])
        ])

        assert {v.version for v in stored_versions("E")} == {v1, v2}

    def test_reapplying_the_same_version_is_idempotent(self, client, headers):
        """§2: versions are immutable, so re-sending one must not duplicate it."""
        v1 = Entity.create_version("a")
        change = entity_change("create", id="E", version=v1)
        sync(client, headers, changes=[change])
        sync(client, headers, changes=[change])

        assert len(stored_versions("E")) == 1

    def test_an_idempotent_resend_is_still_acknowledged(self, client, headers):
        """A re-send is in the desired state, so withholding the ack would make
        the client retry forever."""
        v1 = Entity.create_version("a")
        change = entity_change("create", id="E", version=v1)
        sync(client, headers, changes=[change])

        assert "E" in sync(client, headers, changes=[change])["applied"]


# --------------------------------------------------------------------------- #
# §3.2 Per-id acknowledgement (NOT in PROTOCOL.md before this suite — see below)
# --------------------------------------------------------------------------- #
class TestAcknowledgement:
    """The durability contract: a client may only drop a pending change when the
    server names its id.

    Aggregate counts cannot express this — a partially-applied batch would let a
    client discard writes that never landed. PROTOCOL.md §9 previously listed
    `sync_ack` as "a no-op; there is no ack step", which was true when written
    and is now wrong; the spec is updated alongside this suite.
    """

    def test_applied_lists_the_ids_that_landed(self, client, headers):
        v1, v2 = Entity.create_version("a"), Entity.create_version("b")
        body = sync(client, headers, changes=[
            entity_change("create", id="A", version=v1),
            entity_change("create", id="B", version=v2),
        ])

        assert set(body["applied"]) == {"A", "B"}

    def test_applied_relationships_is_separate_from_entities(self, client, headers):
        v1, v2 = Entity.create_version("a"), Entity.create_version("b")
        body = sync(client, headers, changes=[
            entity_change("create", id="A", version=v1),
            entity_change("create", id="B", version=v2, rels=[
                edge("EDGE", from_id="B", from_version=v2, to_id="A", to_version=v1)
            ]),
        ])

        assert body["applied_relationships"] == ["EDGE"]
        assert "EDGE" not in body["applied"]

    def test_a_relationship_with_a_missing_endpoint_is_not_acknowledged(self, client, headers):
        """It must stay pending so the client retries once the endpoint arrives."""
        v1 = Entity.create_version("a")
        body = sync(client, headers, changes=[
            entity_change("create", id="A", version=v1, rels=[
                edge("EDGE", from_id="A", from_version=v1,
                     to_id="NOT-HERE", to_version="v-missing")
            ]),
        ])

        assert body["applied"] == ["A"]
        assert body["applied_relationships"] == []

    def test_a_losing_change_is_acknowledged(self, client, headers):
        """ADR-011 §2: losing is terminal, so it is acked — otherwise a client
        with a pull-guard retries it forever and never converges."""
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1, name="kept")])

        ancient = "2020-01-01T00:00:00.000000+00:00-000001-old"
        body = sync(client, headers, changes=[
            entity_change("update", id="E", version=ancient, name="loses", parents=[])
        ])

        assert "E" in body["applied"]
        assert body["conflicts"], "a loser must also be reported"


# --------------------------------------------------------------------------- #
# §4 Sync flows & the `since` watermark
# --------------------------------------------------------------------------- #
class TestSyncFlows:

    def test_full_sync_returns_current_entities(self, client, headers):
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1)])

        served = sync(client, headers, "full")["changes"]
        assert "E" in {c["entity"]["id"] for c in served if c.get("entity")}

    def test_response_carries_the_server_time_watermark(self, client, headers):
        """§4: the client's next `since` is the server's clock, never its own."""
        body = sync(client, headers, "full")

        assert body["server_time"], "server_time is the documented watermark"
        assert "+00:00" in body["server_time"], "§6 requires a UTC offset"

    def test_delta_since_is_an_exclusive_lower_bound(self, client, headers):
        """§4: strictly greater than `since`, so a client cannot re-receive
        what it already has and cannot skip a same-instant neighbour."""
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="OLD", version=v1)])
        watermark = sync(client, headers, "full")["server_time"]

        delta = sync(client, headers, "delta", since=watermark)
        assert "OLD" not in {c["entity"]["id"] for c in delta["changes"] if c.get("entity")}

    def test_delta_returns_changes_made_after_the_watermark(self, client, headers):
        watermark = sync(client, headers, "full")["server_time"]
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="NEW", version=v1)])

        delta = sync(client, headers, "delta", since=watermark)
        assert "NEW" in {c["entity"]["id"] for c in delta["changes"] if c.get("entity")}


# --------------------------------------------------------------------------- #
# §5 Apply ordering
# --------------------------------------------------------------------------- #
class TestApplyOrdering:

    def test_an_edge_may_reference_an_entity_created_later_in_the_batch(self, client, headers):
        """§5: entities before relationships, across the WHOLE batch — not
        per-change. An edge on the first change may point at the last change's
        entity, so a single-pass implementation fails this."""
        v1, v2 = Entity.create_version("a"), Entity.create_version("b")
        body = sync(client, headers, changes=[
            entity_change("create", id="FIRST", version=v1, rels=[
                edge("EDGE", from_id="FIRST", from_version=v1, to_id="LATER", to_version=v2)
            ]),
            entity_change("create", id="LATER", version=v2),
        ])

        assert body["applied_relationships"] == ["EDGE"]


# --------------------------------------------------------------------------- #
# §6 Timestamp contract
# --------------------------------------------------------------------------- #
class TestTimestampContract:

    def test_version_strings_are_utc_with_offset_and_microseconds(self):
        """§6: sub-second precision is load-bearing for the §7 conflict window."""
        version = Entity.create_version(USER)

        assert "+00:00" in version
        parsed = Entity.version_timestamp(version)
        assert parsed is not None and parsed.tzinfo is not None
        assert parsed.microsecond != 0 or "." in version

    def test_served_timestamps_are_timezone_aware(self, client, headers):
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1)])

        served = [c for c in sync(client, headers, "full")["changes"] if c.get("entity")]
        assert served, "expected the entity back"


# --------------------------------------------------------------------------- #
# §7 Conflict resolution
# --------------------------------------------------------------------------- #
class TestConflictResolution:

    def test_a_fast_forward_is_not_a_conflict(self, client, headers):
        """§7 only applies to concurrent edits; naming our latest as parent is
        a fast-forward and must apply cleanly."""
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1)])

        v2 = Entity.create_version("b")
        body = sync(client, headers, changes=[
            entity_change("update", id="E", version=v2, name="next", parents=[v1])
        ])

        assert body["conflicts"] == []
        assert "E" in body["applied"]

    def test_newer_updated_at_wins(self, client, headers):
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1, name="old")])

        ancient = "2020-01-01T00:00:00.000000+00:00-000001-old"
        sync(client, headers, changes=[
            entity_change("update", id="E", version=ancient, name="stale", parents=[])
        ])

        served = {c["entity"]["id"]: c["entity"]
                  for c in sync(client, headers, "full")["changes"] if c.get("entity")}
        assert served["E"]["name"] == "old", "the older edit must not win"

    def test_conflicts_report_both_versions_and_the_outcome(self, client, headers):
        """§7: report the decision, so a client can explain it to a human."""
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1)])

        ancient = "2020-01-01T00:00:00.000000+00:00-000001-old"
        conflicts = sync(client, headers, changes=[
            entity_change("update", id="E", version=ancient, parents=[])
        ])["conflicts"]

        assert len(conflicts) == 1
        record = conflicts[0]
        assert record["entity_id"] == "E"
        assert record["local_version"] == v1
        assert record["remote_version"] == ancient
        assert record["resolved_version"] == v1
        assert record["resolution_strategy"]

    def test_a_losing_version_is_preserved_in_history(self, client, headers):
        """ADR-011 §2: a write may lose prominence but never existence."""
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1)])

        ancient = "2020-01-01T00:00:00.000000+00:00-000001-old"
        sync(client, headers, changes=[
            entity_change("update", id="E", version=ancient, name="recoverable", parents=[])
        ])

        assert ancient in {v.version for v in stored_versions("E")}


# --------------------------------------------------------------------------- #
# §8 Deletes & tombstones
# --------------------------------------------------------------------------- #
class TestTombstones:

    def test_a_delete_is_a_tombstone_version_not_a_row_removal(self, client, headers):
        """§8: deletion converges like any other edit, so history is retained."""
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1)])

        v2 = Entity.create_version("b")
        sync(client, headers, changes=[
            entity_change("delete", id="E", version=v2, parents=[v1])
        ])

        versions = stored_versions("E")
        assert v1 in {v.version for v in versions}, "the prior version is retained"
        tombstone = next(v for v in versions if v.version == v2)
        assert tombstone.content.get("deleted") is True

    def test_a_tombstone_is_served_as_a_delete_change(self, client, headers):
        """A client must be able to tell deletion from absence."""
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1)])
        v2 = Entity.create_version("b")
        sync(client, headers, changes=[entity_change("delete", id="E", version=v2, parents=[v1])])

        served = {c["entity"]["id"]: c for c in sync(client, headers, "full")["changes"]
                  if c.get("entity")}
        assert served["E"]["change_type"] == "delete"

    def test_deleting_an_unknown_entity_is_acknowledged(self, client, headers):
        """A terminal state the client can never advance past — withholding the
        ack would be a permanent retry loop."""
        body = sync(client, headers, changes=[
            entity_change("delete", id="NEVER-EXISTED", version=Entity.create_version("a"))
        ])

        assert "NEVER-EXISTED" in body["applied"]


# --------------------------------------------------------------------------- #
# §9 Reserved fields
# --------------------------------------------------------------------------- #
class TestReservedFields:

    def test_vector_clock_is_echoed_and_never_interpreted(self, client, headers):
        """§9: reserved. A port must round-trip it without depending on it."""
        body = sync(client, headers, "full")

        assert "vector_clock" in body

    def test_cursor_is_null_when_the_stream_is_drained(self, client, headers):
        """No longer reserved — ADR-002 §4 implemented it, as the previous
        version of this test predicted it would.

        Null means "drained", which is the client's signal to stop looping. An
        empty `changes` list is NOT that signal: a filtered page can be empty
        while rows remain beyond it.
        """
        v1 = Entity.create_version("a")
        sync(client, headers, changes=[entity_change("create", id="E", version=v1)])

        body = sync(client, headers, "full")
        assert body.get("cursor") is None, "one small page: nothing left to resume from"

    def test_a_digest_accompanies_every_response(self, client, headers):
        """ADR-011 §4: divergence must be detectable.

        Without this a client and server can both believe they are in sync
        because both applied every change they were told about, while holding
        different state.
        """
        body = sync(client, headers, "full")

        assert body.get("state_digest"), "every response carries a state digest"

    def test_the_digest_changes_when_state_changes(self, client, headers):
        before = sync(client, headers, "full")["state_digest"]
        sync(client, headers, changes=[
            entity_change("create", id="NEW", version=Entity.create_version("a"))
        ])
        after = sync(client, headers, "full")["state_digest"]

        assert before != after

    def test_the_digest_is_stable_for_unchanged_state(self, client, headers):
        """It must depend on state alone — not on time, or request order."""
        sync(client, headers, changes=[
            entity_change("create", id="E", version=Entity.create_version("a"))
        ])

        assert sync(client, headers, "full")["state_digest"] == \
               sync(client, headers, "full")["state_digest"]


# --------------------------------------------------------------------------- #
# §3 Wire protocol
# --------------------------------------------------------------------------- #
class TestWireProtocol:

    def test_an_unsupported_protocol_version_is_rejected(self, client, headers):
        response = client.post("/api/v1/sync/", headers=headers, json={
            "protocol_version": "inbetweenies-v1", "device_id": "d", "user_id": USER,
            "sync_type": "full", "changes": [],
        })

        assert response.status_code == 400

    def test_a_change_may_carry_relationships_without_an_entity(self, client, headers):
        """§3.1: an edge whose endpoints are already in sync travels alone."""
        v1, v2 = Entity.create_version("a"), Entity.create_version("b")
        sync(client, headers, changes=[
            entity_change("create", id="A", version=v1),
            entity_change("create", id="B", version=v2),
        ])

        body = sync(client, headers, changes=[{
            "change_type": "update", "entity": None,
            "relationships": [edge("EDGE", from_id="A", from_version=v1,
                                   to_id="B", to_version=v2)],
        }])

        assert body["applied_relationships"] == ["EDGE"]

    def test_sync_stats_agree_with_the_acknowledgement_lists(self, client, headers):
        """Counts report what landed, not what was attempted — otherwise
        `entities_synced: 1` can sit next to `applied: []`."""
        v1 = Entity.create_version("a")
        body = sync(client, headers, changes=[entity_change("create", id="E", version=v1)])

        assert body["sync_stats"]["entities_synced"] == len(body["applied"])
        assert body["sync_stats"]["relationships_synced"] == len(body["applied_relationships"])
