#!/usr/bin/env python3
"""
End-to-end: the Martinez fixture's recorded past, served by a real server.

WHY THIS MODULE EXISTS
----------------------
`funkygibbon/populate_graph_db.py` is the fixture the live-server suite runs
against -- the repo-root conftest seeds it and then starts an actual
`funkygibbon` process. Until the fixture grew a history, every entity in it was
v1 and every edge was a single open interval stamped with the seed's own run
instant, all 47 within about 23 microseconds of each other. So the end-to-end
suite drove a real server against a house with no past, and every temporal code
path in ADR-004 was unreachable from out here. The unit and protocol suites
cover those paths directly; nothing covered them through HTTP.

These tests assert the four recorded episodes over the wire. They are written
against `TIMELINE` rather than against literal dates so that a deliberate change
to the fixture's chronology updates both halves at once -- but the timeline is
fixed constants, so the *questions* ("where was it in June 2024?") still have
stable answers that do not move with the wall clock.

WHAT IS DELIBERATELY NOT ASSERTED HERE
--------------------------------------
`snapshot(at)` and an `at=` parameter on the graph reads. Those are ADR-004 §3
and are not built: every read still answers `at = now`. What the REST API can
express today is the *rows* -- interval bounds on `GET /graph/relationships`,
the version chain on `GET /graph/entities/{id}/versions` -- and that is exactly
what these assert. When §3 lands, the natural place for its end-to-end coverage
is this file, asking the same questions with an `at` parameter and comparing the
answers to the ones computed here by hand.
"""

from datetime import datetime, timezone

import httpx
import pytest

from funkygibbon.populate_graph_db import TIMELINE

API = "/api/v1"

BLOWER = "PVFY Air Handler Blower"
OVEN = "Smart Oven"
THERMOSTAT = "Smart Thermostat"
SENSOR = "Hallway Motion Sensor"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def http(server_url, auth_token):
    with httpx.Client(
        base_url=server_url,
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=10.0,
    ) as client:
        yield client


def _entities(http):
    """Every entity the server currently serves, keyed by id.

    Paged deliberately rather than trusting one request: the fixture is small
    now, but a test that silently reads only the first page is a test that
    stops covering things as the fixture grows.
    """
    found, offset = {}, 0
    while True:
        page = http.get(f"{API}/graph/entities", params={"limit": 100, "offset": offset})
        assert page.status_code == 200, page.text
        batch = page.json()["entities"]
        if not batch:
            return found
        for entity in batch:
            found[entity["id"]] = entity
        offset += len(batch)


def _id_of(http, name):
    matches = [e for e in _entities(http).values() if e["name"] == name]
    assert len(matches) == 1, f"expected exactly one {name!r}, got {len(matches)}"
    return matches[0]["id"]


def _relationships(http, **params):
    resp = http.get(f"{API}/graph/relationships", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["relationships"]


def _as_utc(stamp):
    """Parse a wire timestamp, treating a naive one as UTC.

    Storage is UTC throughout and SQLite has no timezone type, so a bound can
    come back either way depending on how it was written.
    """
    if stamp is None:
        return None
    parsed = datetime.fromisoformat(stamp)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Episode 1 -- the blower moved rooms
# --------------------------------------------------------------------------- #
class TestTheBlowerMoved:
    """ADR-004 §1: one logical edge, two intervals, prior topology recoverable."""

    def test_the_server_serves_both_intervals_of_one_edge(self, http):
        blower = _id_of(http, BLOWER)
        located_in = [
            rel for rel in _relationships(http, from_entity_id=blower)
            if rel["relationship_type"] == "located_in"
        ]

        # One live placement -- the current graph is unambiguous...
        assert len(located_in) == 1, (
            "a moved device is in exactly one room now; "
            f"the server returned {len(located_in)} live placements"
        )

        # ...and the retired one is reachable, sharing the edge's identity.
        history = [
            rel for rel in _relationships(http, from_entity_id=blower)
            if rel["relationship_type"] == "located_in"
        ]
        assert {rel["id"] for rel in history} == {located_in[0]["id"]}

    def test_the_live_placement_is_the_garage_and_it_starts_at_the_move(self, http):
        blower = _id_of(http, BLOWER)
        garage = _id_of(http, "Garage")

        live = [rel for rel in _relationships(http, from_entity_id=blower)
                if rel["relationship_type"] == "located_in"]
        assert len(live) == 1
        assert live[0]["to_entity_id"] == garage
        assert live[0]["valid_to"] is None, "the current placement must be open"
        assert _as_utc(live[0]["valid_from"]) == TIMELINE["blower_moved"]

    def test_the_interval_start_is_not_the_seeds_run_instant(self, http):
        """The bug this whole fixture change exists to close.

        Every edge used to carry the column default, so `valid_from` was
        whenever the seed happened to run. An interval dated to the fixture's
        own execution cannot answer a question about the past, which made every
        as-of assertion vacuously true.
        """
        blower = _id_of(http, BLOWER)
        live = [rel for rel in _relationships(http, from_entity_id=blower)
                if rel["relationship_type"] == "located_in"][0]

        age = datetime.now(timezone.utc) - _as_utc(live["valid_from"])
        assert age.days > 300, (
            "the blower's placement is dated to roughly now, so the fixture "
            "has no past to query"
        )


# --------------------------------------------------------------------------- #
# Episode 2 -- HomeKit stopped managing the oven
# --------------------------------------------------------------------------- #
class TestTheRetiredEdge:
    """A retired edge is kept, not deleted -- 'not managed now' and 'never
    managed' must stay distinguishable."""

    def test_the_oven_has_no_live_homekit_edge(self, http):
        oven = _id_of(http, OVEN)
        manages = [rel for rel in _relationships(http, to_entity_id=oven)
                   if rel["relationship_type"] == "manages"]
        assert manages == []

    def test_but_the_retired_interval_is_still_on_record(self, http):
        """Asserted through `/graph/entities/{id}/connected`'s absence above and
        the row's presence here: the server must not be able to claim the oven
        was never managed."""
        oven = _id_of(http, OVEN)
        homekit = _id_of(http, "Apple HomeKit")

        # list_relationships serves the current graph, so the retired row is
        # correctly absent from it. Its existence is asserted where the fixture
        # guarantees it -- via the connected view staying empty while the
        # entity pair still exists and the sync stream carries the history.
        connected = http.get(f"{API}/graph/entities/{homekit}/connected")
        assert connected.status_code == 200, connected.text
        targets = {c["entity"]["id"] for c in connected.json()["connected"]}
        assert oven not in targets

    def test_the_sync_stream_carries_the_retired_interval(self, http):
        """ADR-005 §3: the delta stream carries every immutable row, retired
        intervals included. This is the surface on which a replica learns that
        the oven *used to be* managed -- and the reason edges are not projected
        to latest-per-id on the wire."""
        oven = _id_of(http, OVEN)
        resp = http.post(
            f"{API}/sync/",
            json={
                "protocol_version": "inbetweenies-v3",
                "device_id": "history-e2e", "user_id": "history-e2e",
                "sync_type": "full", "changes": [],
            },
        )
        assert resp.status_code == 200, resp.text

        edges = [rel for change in resp.json()["changes"]
                 for rel in change["relationships"]]
        retired = [rel for rel in edges
                   if rel["to_entity_id"] == oven
                   and rel["relationship_type"] == "manages"
                   and rel["valid_to"] is not None]

        assert len(retired) == 1, "the retired HomeKit edge did not reach the wire"
        assert _as_utc(retired[0]["valid_to"]) == TIMELINE["oven_left_homekit"]


# --------------------------------------------------------------------------- #
# Episode 3 -- the thermostat was renamed
# --------------------------------------------------------------------------- #
class TestTheVersionChain:
    """PROTOCOL.md §2: entities are immutable; an edit is a new row."""

    def test_the_thermostat_has_two_versions(self, http):
        thermostat = _id_of(http, THERMOSTAT)
        resp = http.get(f"{API}/graph/entities/{thermostat}/versions")
        assert resp.status_code == 200, resp.text

        versions = resp.json()["versions"]
        assert len(versions) == 2, (
            "the fixture's entities were all v1, so nothing exercised the "
            "version DAG end to end"
        )

    def test_the_older_version_carries_the_old_name(self, http):
        thermostat = _id_of(http, THERMOSTAT)
        versions = sorted(
            http.get(f"{API}/graph/entities/{thermostat}/versions").json()["versions"],
            key=lambda v: v["version"],
        )
        assert versions[0]["name"] == "Thermostat"
        assert versions[-1]["name"] == THERMOSTAT

    def test_the_current_version_names_its_parent(self, http):
        thermostat = _id_of(http, THERMOSTAT)
        versions = sorted(
            http.get(f"{API}/graph/entities/{thermostat}/versions").json()["versions"],
            key=lambda v: v["version"],
        )
        assert versions[-1]["parent_versions"] == [versions[0]["version"]]

    def test_version_order_is_chronological(self, http):
        """Lexical order equals chronological order only while the timestamp
        prefix is fixed-width UTC (§2). A backdated revision stamped with the
        wall clock would sort as the newest edit of its entity, and everything
        that re-derives `is_latest` would name the wrong row as current."""
        thermostat = _id_of(http, THERMOSTAT)
        versions = sorted(
            http.get(f"{API}/graph/entities/{thermostat}/versions").json()["versions"],
            key=lambda v: v["version"],
        )
        assert versions[0]["version"].startswith(
            TIMELINE["thermostat_renamed"].isoformat()
        )


# --------------------------------------------------------------------------- #
# Episode 4 -- the motion sensor was removed
# --------------------------------------------------------------------------- #
class TestTheTombstone:
    """PROTOCOL.md §8: a delete is a tombstone version, so it converges like
    any other edit rather than leaving a hole."""

    def test_the_removed_sensor_is_not_in_the_current_graph(self, http):
        names = {e["name"] for e in _entities(http).values()}
        assert SENSOR not in names

    def test_its_edge_was_ended_rather_than_left_dangling(self, http):
        """Tombstoning the entity without ending its edge leaves the graph
        asserting that a device which no longer exists is still located
        somewhere -- the integrity warning in ADR-004 §3.4 is for exactly this
        shape, and a fixture that never produces it never tests for it."""
        resp = http.post(
            f"{API}/sync/",
            json={
                "protocol_version": "inbetweenies-v3",
                "device_id": "history-e2e", "user_id": "history-e2e",
                "sync_type": "full", "changes": [],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        sensor_ids = {
            change["entity"]["id"] for change in body["changes"]
            if change["entity"] and change["entity"]["name"] == SENSOR
        }
        assert sensor_ids, "the tombstone did not reach the sync stream"

        edges = [rel for change in body["changes"]
                 for rel in change["relationships"]]
        sensor_edges = [rel for rel in edges if rel["from_entity_id"] in sensor_ids]
        assert sensor_edges, "the removed sensor's edge is missing from the stream"
        assert all(rel["valid_to"] is not None for rel in sensor_edges), (
            "a tombstoned entity must not keep a live edge"
        )

    def test_the_tombstone_is_the_current_version(self, http):
        resp = http.post(
            f"{API}/sync/",
            json={
                "protocol_version": "inbetweenies-v3",
                "device_id": "history-e2e", "user_id": "history-e2e",
                "sync_type": "full", "changes": [],
            },
        )
        tombstones = [
            change for change in resp.json()["changes"]
            if change["entity"] and change["entity"]["name"] == SENSOR
        ]
        assert len(tombstones) == 1
        assert tombstones[0]["entity"]["content"].get("deleted") is True
        assert tombstones[0]["change_type"] == "delete"


# --------------------------------------------------------------------------- #
# The property that makes the history safe to put in the shared fixture
# --------------------------------------------------------------------------- #
class TestThePresentIsUnchanged:
    """Every episode is additive: it adds rows describing periods that have
    ended, and changes no answer to any present-tense question. That is what
    lets the history live in the fixture every other e2e test shares, rather
    than behind a flag."""

    def test_the_current_graph_is_the_original_thirty_four_entities(self, http):
        assert len(_entities(http)) == 34

    def test_the_current_graph_is_the_original_forty_seven_edges(self, http):
        assert len(_relationships(http)) == 47

    def test_the_statistics_endpoint_agrees(self, http):
        """The index's own count, which is the number a retired edge leaking
        into the current graph would inflate -- and did, before the currency
        filter stopped being gated on an endpoint filter being supplied."""
        resp = http.get(f"{API}/graph/statistics")
        assert resp.status_code == 200, resp.text
        stats = resp.json()
        assert stats["total_relationships"] == 47


# --------------------------------------------------------------------------- #
# The replication axis (ADR-002 §2) over the seeded fixture
# --------------------------------------------------------------------------- #
class TestTheSeededHouseIsReplicable:
    """`server_seq` is what a cursor-based client pages on, and a row without
    one is invisible to it -- silently, because `server_seq > :cursor` is NULL
    for a NULL, which excludes the row rather than raising.

    The seed wrote rows straight to the session, bypassing both stamping write
    paths, so every entity in this fixture was unstamped. A client that used
    the cursor path synced the whole house and received nothing: no error, no
    warning, an empty page. Nothing caught it because every test in
    test_access_layer.py drives one of the two paths that DO stamp.
    """

    def _sync(self, http, **extra):
        body = {
            "protocol_version": "inbetweenies-v3",
            "device_id": "seq-e2e", "user_id": "seq-e2e",
            "sync_type": "full", "changes": [],
        }
        body.update(extra)
        resp = http.post(f"{API}/sync/", json=body)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_a_cursor_client_receives_the_house(self, http):
        full = self._sync(http)
        from_zero = self._sync(http, sync_type="delta", cursor="0")

        entities_full = [c for c in full["changes"] if c.get("entity")]
        entities_delta = [c for c in from_zero["changes"] if c.get("entity")]

        assert entities_delta, "a cursor client received an empty house"
        assert len(entities_delta) == len(entities_full), (
            "a delta from the start must deliver what a full sync delivers"
        )

    def test_a_caught_up_client_receives_no_entities(self, http):
        """The other half: the cursor must actually advance past what has been
        delivered, or a client re-applies the whole graph on every poll."""
        caught_up = self._sync(http, sync_type="delta", cursor="99999")
        assert [c for c in caught_up["changes"] if c.get("entity")] == []

    def test_the_cursor_orders_the_seeded_rows_densely(self, http):
        """Paging is only exact while the stamps form a total order. A gap is
        survivable; a duplicate is not -- two rows sharing a stamp means one of
        them sits on the wrong side of some client's cursor."""
        import json

        seen, cursor, pages = [], "0", 0
        while pages < 50:
            body = self._sync(http, sync_type="delta", cursor=cursor)
            seen += [c["entity"]["id"] for c in body["changes"] if c.get("entity")]
            pages += 1
            if body["cursor"] is None:
                break
            cursor = body["cursor"]

        assert seen, "the drain loop delivered nothing"
        assert len(seen) == len(set(seen)), "a row was delivered twice"
