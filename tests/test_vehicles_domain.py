"""The vehicles domain is the proof that the engine is domain-blind (ADR-012, ADR-016).

Three layers, each asserting the same claim from a different side:

* **The manifest** is a complete description -- the capture vocabulary, its
  tools, a skill -- and restates none of the base vocabulary.
* **The engine executes it generically**: the declared tools run against an
  in-memory store and against a blowing-off replica with no vehicles code in
  either, and a house server never sees them.
* **A real FunkyGibbon serving the vehicles manifest** -- separate database,
  separate port, the same engine binary -- answers the domain's questions over
  MCP for the four example lifecycles, refuses house vocabulary, and syncs a
  vehicle over inbetweenies-v3.
"""

import ast
import pathlib
import sys

import httpx
import pytest

from conftest import REPO_ROOT, TEST_ADMIN_PASSWORD, start_funkygibbon
from domains.house import HOUSE
from domains.vehicles import VEHICLES
from domains.vehicles.seed import TIMELINE
from inbetweenies.domain import DomainValidationError, Walk
from inbetweenies.mcp.catalog import ENGINE_TOOL_SPECS, catalog_for
from inbetweenies.mcp.domain_tools import run_domain_tool
from inbetweenies.models import Entity
from inbetweenies.tests.memory_graph import VersionedInMemoryGraph, make_entity

VEHICLES_SPEC = "domains.vehicles.manifest:VEHICLES"
API = "/api/v1"


# --- 1. The manifest ------------------------------------------------------- #

class TestManifest:
    def test_declares_the_capture_vocabulary_and_inherits_the_base(self):
        assert {"vehicle", "part", "tool", "location", "event", "note", "document"} <= VEHICLES.entity_types
        # ADR-016 §2: one open-kind event, not five guessed entity types.
        assert not {"service_record", "purchase", "issue", "invoice"} & VEHICLES.entity_types
        # Base, inherited, not declared here.
        assert {"photo", "app"} <= VEHICLES.entity_types
        assert {"has_photo", "manages"} <= VEHICLES.relationship_types
        assert VEHICLES.carries_blob("document") and VEHICLES.carries_blob("photo")

    def test_does_not_restate_base_vocabulary_in_source(self):
        source = (REPO_ROOT / "domains" / "vehicles" / "manifest.py").read_text()
        tree = ast.parse(source)
        declared = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert "has_photo" not in declared
        entity_list = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "ENTITY_TYPES")
        assert "photo" not in {c.value for c in entity_list.value.elts}

    def test_endpoint_rules_hold(self):
        VEHICLES.check_relationship("fitted_to", "part", "vehicle")
        VEHICLES.check_relationship("happened_to", "event", "vehicle")
        VEHICLES.check_relationship("involved", "event", "part")
        with pytest.raises(DomainValidationError):
            VEHICLES.check_relationship("fitted_to", "vehicle", "part")
        with pytest.raises(DomainValidationError):
            VEHICLES.check_entity_type("room")

    def test_declares_six_tools_and_a_skill(self):
        assert len(VEHICLES.tools) == 6
        assert sum(1 for t in VEHICLES.tools if t.walk) == 4
        assert {t.name for t in VEHICLES.tools if t.handler} == {"get_events", "get_vehicle_history"}
        path = pathlib.Path(VEHICLES.skills["vehicle-walk"])
        assert path.exists() and path.read_text().startswith("---\nname: vehicle-walk")

    def test_odometer_merge_rule_takes_the_higher_reading(self):
        rule = VEHICLES.merge_rules["vehicle"]
        assert rule({"odometer": 100}, {"odometer": 120}, {"odometer": 115}) == {"odometer": 120}
        assert rule({}, {"make": "Zero"}, {"model": "SR/F"}) == {}


# --- 2. The engine runs it generically ------------------------------------ #

class TestCatalog:
    def test_each_domain_gets_the_engine_tools_plus_its_own_and_nothing_else(self):
        engine = {t.name for t in ENGINE_TOOL_SPECS}
        vehicles = {t.name for t in catalog_for(VEHICLES)}
        house = {t.name for t in catalog_for(HOUSE)}
        assert vehicles == engine | set(VEHICLES.tool_names)
        assert house == engine | set(HOUSE.tool_names)
        assert not (set(VEHICLES.tool_names) & house)
        assert not (set(HOUSE.tool_names) & vehicles)

    def test_vocabulary_parameters_are_narrowed_to_the_domain(self):
        by_name = {t.name: t for t in catalog_for(VEHICLES)}
        assert "event" in by_name["create_entity"].parameters["properties"]["entity_type"]["enum"]
        assert "room" not in by_name["create_entity"].parameters["properties"]["entity_type"]["enum"]
        assert "happened_to" in by_name["create_relationship"].parameters["properties"]["relationship_type"]["enum"]
        assert "at" in by_name["get_parts_on_vehicle"].parameters["properties"]
        assert by_name["get_parts_on_vehicle"].parameters["required"] == ["vehicle_id"]
        assert {"kind", "since", "until", "at"} <= set(by_name["get_events"].parameters["properties"])

    def test_a_domain_may_not_redeclare_an_engine_tool(self):
        from inbetweenies.domain import DomainTool, build_manifest
        clash = build_manifest(
            name="bad", entity_types=["x"], source_types=["manual"], relationship_rules=[],
            tools=[DomainTool(name="get_statistics", description="", anchor="x_id",
                              walk=(Walk("has_photo"),))],
        )
        with pytest.raises(ValueError, match="redeclares engine tools"):
            catalog_for(clash)


@pytest.fixture
def garage():
    """An in-memory vehicles graph: one car, two tyre sets, three events."""
    g = VersionedInMemoryGraph()
    g.manifest = VEHICLES
    g.add_entity(make_entity("car", "vehicle", "Boxster", {"kind": "car"}))
    g.add_entity(make_entity("bay", "location", "Bay 1"))
    g.add_entity(make_entity("old", "part", "Old tyres", {"category": "tyres"}))
    g.add_entity(make_entity("new", "part", "New tyres", {"category": "tyres"}))
    g.add_entity(make_entity("wrench", "tool", "Torque wrench"))
    g.add_entity(make_entity("e1", "event", "Bought", {"kind": "purchase", "when": "2009-05-16"}))
    g.add_entity(make_entity("e2", "event", "Clutch", {"kind": "service", "when": "2016-03-12"}))
    g.add_entity(make_entity("e3", "event", "Fuel", {"kind": "fuel", "when": "2026-09-06"}))
    g.connect("r1", "car", "bay", "located_in")
    g.connect("r2", "new", "car", "fitted_to")
    g.connect("r3", "wrench", "car", "compatible_with")
    for i, e in enumerate(("e1", "e2", "e3")):
        g.connect(f"h{i}", e, "car", "happened_to")
    return g


class TestDeclaredToolsRunOnAnyStore:
    async def test_a_walk_follows_the_declared_edge_and_keeps_the_declared_type(self, garage):
        result = await run_domain_tool(garage, VEHICLES.tool("get_parts_on_vehicle"), {"vehicle_id": "car"})
        assert result.success, result.error
        assert [p["id"] for p in result.result["parts"]] == ["new"]
        assert result.result["anchor"] == {"id": "car", "name": "Boxster", "type": "vehicle"}
        assert result.result["count"] == 1

    async def test_a_walk_may_keep_several_types(self, garage):
        result = await run_domain_tool(garage, VEHICLES.tool("get_tools_for_vehicle"), {"vehicle_id": "car"})
        assert [i["id"] for i in result.result["items"]] == ["wrench"]

    async def test_get_events_filters_by_kind_and_date_on_the_events_own_axis(self, garage):
        everything = await run_domain_tool(garage, VEHICLES.tool("get_events"), {"vehicle_id": "car"})
        assert [e["kind"] for e in everything.result["events"]] == ["purchase", "service", "fuel"]
        services = await run_domain_tool(garage, VEHICLES.tool("get_events"), {"vehicle_id": "car", "kind": "service"})
        assert [e["entity"]["id"] for e in services.result["events"]] == ["e2"]
        window = await run_domain_tool(garage, VEHICLES.tool("get_events"),
                                       {"vehicle_id": "car", "since": "2010-01-01", "until": "2020-12-31"})
        assert [e["entity"]["id"] for e in window.result["events"]] == ["e2"]

    async def test_anchor_of_the_wrong_type_is_an_error(self, garage):
        result = await run_domain_tool(garage, VEHICLES.tool("get_parts_on_vehicle"), {"vehicle_id": "bay"})
        assert result.success is False
        assert result.error == "Vehicle bay not found"

    async def test_undeclared_arguments_are_refused(self, garage):
        result = await run_domain_tool(garage, VEHICLES.tool("get_parts_on_vehicle"),
                                       {"vehicle_id": "car", "room_id": "x"})
        assert result.success is False and "room_id" in result.error

    async def test_the_store_enforces_the_vehicles_vocabulary(self, garage):
        refused = await garage.create_entity_tool("room", "Kitchen", {}, "alice")
        assert refused.success is False and "unknown entity_type 'room'" in refused.error
        ok = await garage.create_entity_tool("event", "Smog", {"kind": "inspection", "when": "2023-02-11"}, "alice")
        assert ok.success, ok.error
        wrong_way = await garage.create_relationship_tool("car", "new", "fitted_to")
        assert wrong_way.success is False and "does not permit" in wrong_way.error

    async def test_a_house_tool_is_simply_not_there(self):
        with pytest.raises(KeyError):
            VEHICLES.tool("get_devices_in_room")


class TestReplicaPicksItsDomain:
    def test_blowing_off_exposes_the_vehicles_tools_when_told_to(self, monkeypatch):
        monkeypatch.setenv("DOMAIN_MANIFEST", VEHICLES_SPEC)
        from blowingoff.mcp.client import LocalMCPClient
        client = LocalMCPClient()
        assert client.manifest is VEHICLES
        assert "get_vehicle_history" in client.tools
        assert "get_devices_in_room" not in client.tools
        assert {t.name for t in catalog_for(VEHICLES)} == set(client.tools)

    async def test_blowing_off_runs_a_declared_tool_against_its_local_store(self, monkeypatch):
        monkeypatch.setenv("DOMAIN_MANIFEST", VEHICLES_SPEC)
        from blowingoff.mcp.client import LocalMCPClient
        client = LocalMCPClient()
        car = await client.execute_tool("create_entity", entity_type="vehicle", name="Zero", content={"kind": "motorcycle"})
        battery = await client.execute_tool("create_entity", entity_type="part", name="Battery", content={})
        assert car["success"] and battery["success"], (car, battery)
        car_id, battery_id = car["result"]["entity"]["id"], battery["result"]["entity"]["id"]
        linked = await client.execute_tool("create_relationship", from_entity_id=battery_id,
                                           to_entity_id=car_id, relationship_type="fitted_to")
        assert linked["success"], linked
        parts = await client.execute_tool("get_parts_on_vehicle", vehicle_id=car_id)
        assert parts["success"] and [p["id"] for p in parts["result"]["parts"]] == [battery_id]


# --- 3. A real vehicles server --------------------------------------------- #

@pytest.fixture(scope="module")
def vehicles_server():
    """A FunkyGibbon serving VEHICLES on its own database and port."""
    server = start_funkygibbon(
        TEST_ADMIN_PASSWORD,
        seed=[sys.executable, str(REPO_ROOT / "domains" / "vehicles" / "seed.py")],
        env_extra={"DOMAIN_MANIFEST": VEHICLES_SPEC},
    )
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(scope="module")
def http(vehicles_server):
    with httpx.Client(base_url=vehicles_server.base_url,
                      headers={"Authorization": f"Bearer {vehicles_server.token}"}, timeout=30) as client:
        yield client


def _tool(http, tool_name, **arguments):
    resp = http.post(f"{API}/mcp/tools/{tool_name}", json={"arguments": arguments})
    assert resp.status_code == 200, f"{tool_name}: {resp.status_code} {resp.text}"
    return resp.json()["result"]


def _by_name(http, entity_type, name):
    found = [e for e in _tool(http, "list_entities", entity_type=entity_type)["entities"] if e["name"] == name]
    assert found, f"no {entity_type} named {name!r}"
    return found[0]


def _iso(key):
    return TIMELINE[key].isoformat()


class TestVehiclesServer:
    def test_advertises_exactly_the_vehicles_catalog(self, http):
        names = {t["name"] for t in http.get(f"{API}/mcp/tools").json()["tools"]}
        assert names == {t.name for t in catalog_for(VEHICLES)}
        assert "get_devices_in_room" not in names

    def test_a_house_tool_is_unknown_here(self, http):
        resp = http.post(f"{API}/mcp/tools/get_devices_in_room", json={"arguments": {"room_id": "x"}})
        assert resp.status_code == 400 and "Unknown tool" in resp.text

    def test_house_vocabulary_is_refused_at_the_boundary(self, http):
        resp = http.post(f"{API}/mcp/tools/create_entity",
                         json={"arguments": {"entity_type": "room", "name": "Kitchen", "content": {}}})
        assert resp.status_code == 400 and "unknown entity_type 'room'" in resp.text

    def test_statistics_count_the_capture_vocabulary(self, http):
        stats = _tool(http, "get_statistics")
        assert stats["entity_types"]["vehicle"] == 6   # Mini, Roadster, Lemons, trailer, Boxster, Elise
        assert stats["entity_types"]["event"] >= 25
        assert stats["entity_types"]["app"] == 2       # the MINI app and OVMS
        assert "room" not in stats["entity_types"]

    # -- the Roadster: telemetry summarised, a part with its own history ---- #

    def test_ovms_module_before_and_after_the_v3_swap(self, http):
        roadster = _by_name(http, "vehicle", "2010 Tesla Roadster Sport")
        now = {p["name"] for p in _tool(http, "get_parts_on_vehicle", vehicle_id=roadster["id"])["parts"]}
        assert "OVMS v3 module" in now and "OVMS v2 module" not in now
        before = _tool(http, "get_parts_on_vehicle", vehicle_id=roadster["id"],
                       at=TIMELINE["roadster_ovms_v3"].replace(year=2022).isoformat())
        names = {p["name"] for p in before["parts"]}
        assert "OVMS v2 module" in names and "OVMS v3 module" not in names

    def test_battery_condition_reports_are_events_not_telemetry(self, http):
        roadster = _by_name(http, "vehicle", "2010 Tesla Roadster Sport")
        reports = _tool(http, "get_events", vehicle_id=roadster["id"], kind="condition_report")["events"]
        assert [e["entity"]["content"]["cac_ah"] for e in reports] == [135, 129]
        assert all(e["entity"]["content"]["source"] == "feed" for e in reports)

    # -- the Lemons car: identity as parts over time, hours, off-site ------ #

    def test_the_shell_is_a_part_and_the_reshell_is_history(self, http):
        lemons = _by_name(http, "vehicle", "E30 Lemons car #4471-L")
        assert lemons["content"]["identity"]["lemons_logbook"] == "4471-L"
        now = {p["name"] for p in _tool(http, "get_parts_on_vehicle", vehicle_id=lemons["id"])["parts"]}
        assert "Shell WBAAA1300K8129083" in now and "M20B25 engine #2" in now
        then = _tool(http, "get_parts_on_vehicle", vehicle_id=lemons["id"], at=_iso("lemons_race_1"))
        assert {p["name"] for p in then["parts"]} == {"Shell WBAAA1300K8124471", "M20B25 engine #1"}
        races = _tool(http, "get_events", vehicle_id=lemons["id"], kind="race")["events"]
        assert [e["entity"]["content"]["hours"] for e in races] == [14, 96]

    def test_spares_and_the_trailer_live_at_the_yard(self, http):
        yard = _by_name(http, "location", "Team storage yard, Hollister")
        items = {i["name"] for i in _tool(http, "get_items_in_location", location_id=yard["id"])["items"]}
        assert "M20B25 engine #3 (spare)" in items
        assert "Fuel pump (spare)" not in items  # fitted at Sonoma; its yard interval ended
        vehicles_now = {v["name"] for v in _tool(http, "get_vehicles_in_location", location_id=yard["id"])["vehicles"]}
        assert vehicles_now == {"E30 Lemons car #4471-L"}  # the trailer came home in March
        vehicles_then = {v["name"] for v in _tool(http, "get_vehicles_in_location", location_id=yard["id"],
                                                   at=_iso("lemons_race_2"))["vehicles"]}
        assert vehicles_then == {"E30 Lemons car #4471-L", "Car trailer"}

    # -- the Boxster: a long family history ------------------------------- #

    def test_boxster_history_is_one_dated_timeline(self, http):
        boxster = _by_name(http, "vehicle", "2009 Porsche Boxster S")
        history = _tool(http, "get_vehicle_history", vehicle_id=boxster["id"])
        kinds = [(e["when"][:10], e["kind"]) for e in history["events"]]
        assert kinds[:3] == [("2009-05-16", "purchase"), ("2009-05-16", "moved_in"), ("2011-06-04", "service")]
        assert ("2019-10-05", "transfer") in kinds
        assert ("2016-03-12", "part_fitted") in kinds and ("2016-03-12", "service") in kinds
        assert kinds[-1] == ("2026-09-06", "fuel")
        whens = [e["when"] for e in history["events"]]
        assert whens == sorted(whens)

    def test_boxster_events_in_a_window(self, http):
        boxster = _by_name(http, "vehicle", "2009 Porsche Boxster S")
        window = _tool(http, "get_events", vehicle_id=boxster["id"], since="2019-01-01", until="2021-12-31")["events"]
        assert [e["kind"] for e in window] == ["transfer", "repair"]

    def test_history_as_of_knows_nothing_of_the_future(self, http):
        boxster = _by_name(http, "vehicle", "2009 Porsche Boxster S")
        early = _tool(http, "get_vehicle_history", vehicle_id=boxster["id"], at=_iso("boxster_road_trip"))
        assert [e["kind"] for e in early["events"]] == ["purchase", "moved_in", "service", "road_trip"]

    # -- the Mini: the feed writes logbook-grade facts --------------------- #

    def test_the_mini_app_manages_the_car_and_its_facts_are_events(self, http):
        mini = _by_name(http, "vehicle", "2026 Mini Cooper SE")
        from_feed = [e for e in _tool(http, "get_events", vehicle_id=mini["id"])["events"]
                     if e["entity"]["content"]["source"] == "feed"]
        assert [e["kind"] for e in from_feed] == ["software_update", "charge", "odometer"]
        connected = _tool(http, "get_connected", entity_id=mini["id"], relationship_type="manages", direction="incoming")
        assert [c["entity"]["name"] for c in connected["connected"]] == ["MINI app"]

    # -- the Elise: a UK-registered car, MOT history as a feed, GBP --------- #

    def test_uk_vehicle_carries_its_own_units_and_admin(self, http):
        elise = _by_name(http, "vehicle", "1998 Lotus Elise S1")
        assert elise["content"]["country"] == "UK"
        assert elise["content"]["identity"]["registration_country"] == "UK"
        mots = _tool(http, "get_events", vehicle_id=elise["id"], kind="inspection")["events"]
        assert [e["entity"]["content"]["test"] for e in mots] == ["MOT", "MOT"]
        assert all(e["entity"]["content"]["currency"] == "GBP" for e in mots)
        fuel = _tool(http, "get_events", vehicle_id=elise["id"], kind="fuel")["events"]
        assert fuel[0]["entity"]["content"]["litres"] == 45.2
        lockup = _by_name(http, "location", "Lock-up, Cambridge")
        assert lockup["content"]["country"] == "UK"
        assert [v["name"] for v in _tool(http, "get_vehicles_in_location", location_id=lockup["id"])["vehicles"]] == ["1998 Lotus Elise S1"]

    # -- writes through the tools, the way a walk commits ------------------ #

    def test_a_vehicle_walk_writes_through_the_tools(self, http):
        boxster = _by_name(http, "vehicle", "2009 Porsche Boxster S")
        smog = _tool(http, "create_entity", entity_type="event", name="Smog check 2026",
                     content={"kind": "inspection", "when": "2026-09-20", "odometer": 91500, "result": "pass",
                              "source": "walk"})["entity"]
        _tool(http, "create_relationship", from_entity_id=smog["id"], to_entity_id=boxster["id"],
              relationship_type="happened_to")
        inspections = _tool(http, "get_events", vehicle_id=boxster["id"], kind="inspection")["events"]
        assert [e["when"] for e in inspections] == ["2023-02-11", "2026-09-20"]
        # The vocabulary is enforced on every write path, not just the type list.
        resp = http.post(f"{API}/mcp/tools/create_relationship", json={"arguments": {
            "from_entity_id": boxster["id"], "to_entity_id": smog["id"], "relationship_type": "happened_to"}})
        assert resp.status_code == 400 and "does not permit" in resp.text

    def test_sync_is_domain_blind(self, http):
        """A replica pushes a vehicle over inbetweenies-v3; the same protocol, a different vocabulary."""
        version = Entity.create_version("walker")
        body = {
            "protocol_version": "inbetweenies-v3", "device_id": "phone", "user_id": "walker",
            "sync_type": "delta", "changes": [{
                "change_type": "create",
                "entity": {"id": "ebike-1", "version": version, "entity_type": "vehicle",
                           "name": "Rad Power RadRunner", "content": {"kind": "ebike"},
                           "source_type": "manual", "user_id": "walker", "parent_versions": []},
                "relationships": [],
            }],
        }
        resp = http.post(f"{API}/sync/", json=body)
        assert resp.status_code == 200, resp.text
        assert "ebike-1" in resp.json()["applied"]
        assert _tool(http, "get_entity_details", entity_id="ebike-1")["entity"]["entity_type"] == "vehicle"

        body["changes"][0]["entity"].update({"id": "room-1", "entity_type": "room", "version": Entity.create_version("walker")})
        resp = http.post(f"{API}/sync/", json=body)
        assert resp.status_code == 400 and "unknown entity_type 'room'" in resp.text
