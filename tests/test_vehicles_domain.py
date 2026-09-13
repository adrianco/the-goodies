"""The vehicles domain is the proof that the engine is domain-blind (ADR-012).

Three layers, each asserting the same claim from a different side:

* **The manifest** is a complete description -- vocabulary, tools, a skill --
  and restates none of the base vocabulary.
* **The engine executes it generically**: the declared tools run against an
  in-memory store and against a blowing-off replica with no vehicles code in
  either, and a house server never sees them.
* **A real FunkyGibbon serving the vehicles manifest** -- separate database,
  separate port, the same engine binary -- answers the domain's questions over
  MCP, refuses house vocabulary, and syncs a vehicle over inbetweenies-v3.
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
    def test_declares_the_vocabulary_and_inherits_the_base(self):
        assert {"vehicle", "part", "tool", "location", "purchase", "service_record", "issue"} <= VEHICLES.entity_types
        # Base, inherited, not declared here.
        assert {"photo", "app"} <= VEHICLES.entity_types
        assert {"has_photo", "manages"} <= VEHICLES.relationship_types
        assert VEHICLES.carries_blob("invoice") and VEHICLES.carries_blob("photo")

    def test_does_not_restate_base_vocabulary_in_source(self):
        source = (REPO_ROOT / "domains" / "vehicles" / "manifest.py").read_text()
        tree = ast.parse(source)
        declared = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        # `manages` is narrowed on purpose (allowed); `has_photo` and `photo`
        # must not be spelled out at all.
        assert "has_photo" not in declared
        entity_list = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "ENTITY_TYPES")
        assert "photo" not in {c.value for c in entity_list.value.elts}

    def test_endpoint_rules_hold(self):
        VEHICLES.check_relationship("fitted_to", "part", "vehicle")
        with pytest.raises(DomainValidationError):
            VEHICLES.check_relationship("fitted_to", "vehicle", "part")
        with pytest.raises(DomainValidationError):
            VEHICLES.check_entity_type("room")

    def test_declares_eight_tools_and_a_skill(self):
        assert len(VEHICLES.tools) == 8
        assert sum(1 for t in VEHICLES.tools if t.walk) == 7
        assert VEHICLES.tool("get_vehicle_history").handler is not None
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
        assert "vehicle" in by_name["create_entity"].parameters["properties"]["entity_type"]["enum"]
        assert "room" not in by_name["create_entity"].parameters["properties"]["entity_type"]["enum"]
        assert "fitted_to" in by_name["create_relationship"].parameters["properties"]["relationship_type"]["enum"]
        assert "at" in by_name["get_parts_on_vehicle"].parameters["properties"]
        assert by_name["get_parts_on_vehicle"].parameters["required"] == ["vehicle_id"]

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
    """An in-memory vehicles graph: one car, two tyre sets, one open issue."""
    g = VersionedInMemoryGraph()
    g.manifest = VEHICLES
    g.add_entity(make_entity("car", "vehicle", "Outback", {"kind": "car"}))
    g.add_entity(make_entity("bay", "location", "Bay 1"))
    g.add_entity(make_entity("old", "part", "Michelins", {"category": "tyres"}))
    g.add_entity(make_entity("new", "part", "Continentals", {"category": "tyres"}))
    g.add_entity(make_entity("wrench", "tool", "Torque wrench"))
    g.add_entity(make_entity("i1", "issue", "Squeal", {"status": "open"}))
    g.add_entity(make_entity("i2", "issue", "Creak", {"status": "resolved"}))
    g.connect("r1", "car", "bay", "located_in")
    g.connect("r2", "new", "car", "fitted_to")
    g.connect("r3", "wrench", "car", "compatible_with")
    g.connect("r4", "i1", "car", "issue_for")
    g.connect("r5", "i2", "car", "issue_for")
    return g


class TestDeclaredToolsRunOnAnyStore:
    async def test_a_walk_follows_the_declared_edge_and_keeps_the_declared_type(self, garage):
        result = await run_domain_tool(garage, VEHICLES.tool("get_parts_on_vehicle"), {"vehicle_id": "car"})
        assert result.success, result.error
        assert [p["id"] for p in result.result["parts"]] == ["new"]
        assert result.result["anchor"] == {"id": "car", "name": "Outback", "type": "vehicle"}
        assert result.result["count"] == 1

    async def test_where_filters_on_content(self, garage):
        result = await run_domain_tool(garage, VEHICLES.tool("get_open_issues"), {"vehicle_id": "car"})
        assert [i["id"] for i in result.result["issues"]] == ["i1"]

    async def test_a_walk_may_keep_several_types(self, garage):
        result = await run_domain_tool(garage, VEHICLES.tool("get_tools_for_vehicle"), {"vehicle_id": "car"})
        assert [i["id"] for i in result.result["items"]] == ["wrench"]

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
        ok = await garage.create_entity_tool("vehicle", "Tarmac", {"kind": "bicycle"}, "alice")
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
        assert "get_parts_on_vehicle" in client.tools
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

    def test_statistics_count_the_vehicles_vocabulary(self, http):
        stats = _tool(http, "get_statistics")
        assert stats["entity_types"]["vehicle"] == 3
        assert stats["entity_types"]["part"] == 4
        assert "room" not in stats["entity_types"]
        assert stats["relationship_types"]["fitted_to"] == 3  # current edges; the Michelins' interval is closed
        history = _tool(http, "list_relationships", relationship_type="fitted_to", include_history=True)
        assert history["count"] == 4

    def test_parts_now_and_parts_then(self, http):
        outback = _by_name(http, "vehicle", "2019 Subaru Outback")
        now = _tool(http, "get_parts_on_vehicle", vehicle_id=outback["id"])
        assert [p["name"] for p in now["parts"]] == ["Continental TrueContact Tour (set of 4)"]

        before_swap = (TIMELINE["tyres_swapped"].replace(month=6)).isoformat()
        then = _tool(http, "get_parts_on_vehicle", vehicle_id=outback["id"], at=before_swap)
        assert [p["name"] for p in then["parts"]] == ["Michelin CrossClimate2 (set of 4)"]
        assert then["as_of"] == before_swap

        before_michelins = TIMELINE["michelins_fitted"].replace(year=2022).isoformat()
        assert _tool(http, "get_parts_on_vehicle", vehicle_id=outback["id"], at=before_michelins)["parts"] == []

    def test_open_issues_is_the_to_do_list(self, http):
        outback = _by_name(http, "vehicle", "2019 Subaru Outback")
        tarmac = _by_name(http, "vehicle", "Specialized Tarmac SL7")
        assert [i["name"] for i in _tool(http, "get_open_issues", vehicle_id=outback["id"])["issues"]] == ["Rear brake squeal"]
        assert _tool(http, "get_open_issues", vehicle_id=tarmac["id"])["issues"] == []

    def test_history_is_one_dated_timeline(self, http):
        outback = _by_name(http, "vehicle", "2019 Subaru Outback")
        history = _tool(http, "get_vehicle_history", vehicle_id=outback["id"])
        kinds = [(e["when"][:10], e["kind"]) for e in history["events"]]
        assert kinds == [
            ("2021-05-14", "purchased"),
            ("2023-09-10", "part_fitted"),
            ("2024-04-02", "serviced"),
            ("2025-03-01", "issue_opened"),
            ("2025-08-22", "part_fitted"),
            ("2025-08-22", "part_removed"),
            ("2025-08-22", "serviced"),
        ]
        whens = [e["when"] for e in history["events"]]
        assert whens == sorted(whens)

    def test_history_as_of_knows_nothing_of_the_future(self, http):
        outback = _by_name(http, "vehicle", "2019 Subaru Outback")
        early = _tool(http, "get_vehicle_history", vehicle_id=outback["id"],
                      at=TIMELINE["outback_oil_change"].isoformat())
        assert [e["kind"] for e in early["events"]] == ["purchased", "part_fitted", "serviced"]

    def test_locations_and_tools(self, http):
        shelf = _by_name(http, "location", "Workshop Shelf")
        items = _tool(http, "get_items_in_location", location_id=shelf["id"])
        assert {i["entity_type"] for i in items["items"]} == {"part", "tool"}
        bay1 = _by_name(http, "location", "Garage Bay 1")
        assert [v["name"] for v in _tool(http, "get_vehicles_in_location", location_id=bay1["id"])["vehicles"]] == ["2019 Subaru Outback"]
        zero = _by_name(http, "vehicle", "Zero SR/F")
        assert [t["name"] for t in _tool(http, "get_tools_for_vehicle", vehicle_id=zero["id"])["items"]] == ["Level 2 EV charger"]
        assert [p["name"] for p in _tool(http, "get_purchases_for", item_id=zero["id"])["purchases"]] == ["Zero purchase"]

    def test_a_vehicle_walk_writes_through_the_tools(self, http):
        trailer = _tool(http, "create_entity", entity_type="vehicle", name="Bike trailer",
                        content={"kind": "trailer", "make": "Thule"})["entity"]
        shelf = _by_name(http, "location", "Workshop Shelf")
        _tool(http, "create_relationship", from_entity_id=trailer["id"], to_entity_id=shelf["id"],
              relationship_type="located_in")
        hitch = _tool(http, "create_entity", entity_type="part", name="Hitch", content={"category": "hitch"})["entity"]
        _tool(http, "create_relationship", from_entity_id=hitch["id"], to_entity_id=trailer["id"],
              relationship_type="fitted_to")
        assert [p["id"] for p in _tool(http, "get_parts_on_vehicle", vehicle_id=trailer["id"])["parts"]] == [hitch["id"]]
        # The vocabulary is enforced on every write path, not just the type list.
        resp = http.post(f"{API}/mcp/tools/create_relationship", json={"arguments": {
            "from_entity_id": trailer["id"], "to_entity_id": hitch["id"], "relationship_type": "fitted_to"}})
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
