"""Test the MCP tool layer (inbetweenies/mcp/tools.py).

Every tool returns a ToolResult rather than raising, so both halves matter: the
exact success payload (this is the wire contract an MCP client parses) and the
error paths -- missing entity, wrong entity type, malformed argument, backend
failure.
"""

import pytest

from inbetweenies.mcp import ToolResult
from inbetweenies.models import Entity, EntityType, RelationshipType
from inbetweenies.tests.memory_graph import (
    ExplodingGraph,
    VersionedInMemoryGraph,
    make_entity,
)


@pytest.fixture
def exploding():
    """A backend whose get_entity always raises."""
    return ExplodingGraph()


class TestToolResult:
    """The envelope every tool returns."""

    def test_success_payload(self):
        result = ToolResult(True, {"count": 1})

        assert result.to_dict() == {"success": True, "result": {"count": 1}, "error": None}

    def test_error_payload(self):
        result = ToolResult(False, None, "Room r1 not found")

        assert result.to_dict() == {
            "success": False,
            "result": None,
            "error": "Room r1 not found",
        }


class TestGetDevicesInRoom:
    async def test_lists_the_devices_located_in_the_room(self, house):
        result = await house.get_devices_in_room("room-kitchen")

        assert result.success is True
        assert result.error is None
        assert result.result["room_id"] == "room-kitchen"
        assert result.result["count"] == 1
        assert [d["id"] for d in result.result["devices"]] == ["device-light"]
        # Devices are returned fully serialized, not as bare ids.
        assert result.result["devices"][0]["name"] == "Kitchen Light"
        assert result.result["devices"][0]["entity_type"] == "device"

    async def test_room_with_no_devices_reports_zero(self, house):
        result = await house.get_devices_in_room("room-hall")

        assert result.success is True
        assert result.result == {"room_id": "room-hall", "devices": [], "count": 0}

    async def test_ignores_non_device_entities_located_in_the_room(self, house):
        # A zone can also be LOCATED_IN a room; only devices may be reported.
        house.add_entity(make_entity("zone-1", EntityType.ZONE, "Ground Floor"))
        house.connect("rel-zone-kitchen", "zone-1", "room-kitchen", RelationshipType.LOCATED_IN)

        result = await house.get_devices_in_room("room-kitchen")

        assert [d["id"] for d in result.result["devices"]] == ["device-light"]

    async def test_unknown_room_is_an_error(self, house):
        result = await house.get_devices_in_room("no-such-room")

        assert result.success is False
        assert result.result is None
        assert result.error == "Room no-such-room not found"

    async def test_entity_that_is_not_a_room_is_an_error(self, house):
        result = await house.get_devices_in_room("device-light")

        assert result.success is False
        assert result.error == "Room device-light not found"


class TestFindDeviceControls:
    async def test_reports_capabilities_and_services(self, house):
        result = await house.find_device_controls("device-light")

        assert result.success is True
        assert result.result["device_id"] == "device-light"
        assert result.result["device_name"] == "Kitchen Light"
        assert result.result["capabilities"] == ["on_off", "brightness"]
        assert result.result["services"] == ["lightbulb"]

    async def test_reports_controlled_devices(self, house):
        result = await house.find_device_controls("device-hub")

        assert result.result["controlled_devices"] == [
            {"id": "device-light", "name": "Kitchen Light", "type": "device"}
        ]

    async def test_device_controlling_nothing_reports_an_empty_list(self, house):
        result = await house.find_device_controls("device-light")

        assert result.result["controlled_devices"] == []

    async def test_device_without_content_defaults_to_empty_lists(self, empty_graph):
        empty_graph.add_entity(make_entity("d", EntityType.DEVICE, "Bare Device", None))

        result = await empty_graph.find_device_controls("d")

        assert result.success is True
        assert result.result["capabilities"] == []
        assert result.result["services"] == []

    async def test_unknown_device_is_an_error(self, house):
        result = await house.find_device_controls("no-such-device")

        assert result.success is False
        assert result.error == "Device no-such-device not found"

    async def test_entity_that_is_not_a_device_is_an_error(self, house):
        result = await house.find_device_controls("room-kitchen")

        assert result.success is False
        assert result.error == "Device room-kitchen not found"


class TestGetRoomConnections:
    async def test_merges_incoming_and_outgoing_connections(self, house):
        result = await house.get_room_connections("room-hall")

        assert result.success is True
        assert result.result["room_id"] == "room-hall"
        assert result.result["room_name"] == "Hallway"
        assert result.result["connection_count"] == 2
        assert sorted(result.result["connections"], key=lambda c: c["id"]) == [
            {"id": "room-kitchen", "name": "Kitchen", "connection_type": "doorway"},
            {"id": "room-living", "name": "Living Room", "connection_type": "archway"},
        ]

    async def test_connection_type_defaults_to_direct(self, house):
        house.add_entity(make_entity("room-den", EntityType.ROOM, "Den"))
        house.connect("rel-hall-den", "room-hall", "room-den", RelationshipType.CONNECTS_TO)

        result = await house.get_room_connections("room-hall")

        by_id = {c["id"]: c for c in result.result["connections"]}
        assert by_id["room-den"]["connection_type"] == "direct"

    async def test_non_room_neighbours_are_excluded(self, house):
        house.add_entity(make_entity("door-1", EntityType.DOOR, "Front Door"))
        house.connect("rel-door-hall", "door-1", "room-hall", RelationshipType.CONNECTS_TO)

        result = await house.get_room_connections("room-hall")

        assert "door-1" not in [c["id"] for c in result.result["connections"]]
        assert result.result["connection_count"] == 2

    async def test_room_with_no_connections(self, house):
        result = await house.get_room_connections("room-living")

        assert result.result["connection_count"] == 1  # only the hallway

    async def test_unknown_room_is_an_error(self, house):
        result = await house.get_room_connections("no-such-room")

        assert result.success is False
        assert result.error == "Room no-such-room not found"

    async def test_entity_that_is_not_a_room_is_an_error(self, house):
        result = await house.get_room_connections("device-hub")

        assert result.success is False
        assert result.error == "Room device-hub not found"


class TestSearchEntitiesTool:
    async def test_returns_ranked_serialized_results(self, house):
        result = await house.search_entities_tool("kitchen")

        assert result.success is True
        assert result.result["query"] == "kitchen"
        assert result.result["count"] == 4
        assert [r["id"] for r in result.result["results"]] == [
            "room-kitchen",
            "device-light",
            "procedure-1",
            "manual-1",
        ]
        assert result.result["results"][0]["score"] > 0

    async def test_entity_type_strings_are_converted_to_enums(self, house):
        result = await house.search_entities_tool("kitchen", entity_types=["device"])

        assert [r["id"] for r in result.result["results"]] == ["device-light"]

    async def test_limit_is_forwarded(self, house):
        result = await house.search_entities_tool("kitchen", limit=1)

        assert result.result["count"] == 1

    async def test_no_matches_is_a_successful_empty_result(self, house):
        result = await house.search_entities_tool("helicopter")

        assert result.success is True
        assert result.result["results"] == []
        assert result.result["count"] == 0

    async def test_unknown_entity_type_is_a_reported_error(self, house):
        result = await house.search_entities_tool("kitchen", entity_types=["spaceship"])

        assert result.success is False
        assert result.result is None
        assert "not a valid EntityType" in result.error


class TestCreateEntityTool:
    async def test_creates_and_stores_the_entity(self, empty_graph):
        result = await empty_graph.create_entity_tool(
            "device", "New Light", {"watts": 9}, "alice"
        )

        assert result.success is True
        assert result.result["created"] is True
        created = result.result["entity"]
        assert created["entity_type"] == "device"
        assert created["name"] == "New Light"
        assert created["content"] == {"watts": 9}
        assert created["user_id"] == "alice"
        assert created["source_type"] == "manual"
        assert created["parent_versions"] == []

        stored = await empty_graph.get_entity(created["id"])
        assert stored is not None
        assert stored.name == "New Light"

    async def test_generates_a_parseable_version_string(self, empty_graph):
        result = await empty_graph.create_entity_tool("room", "Den", {}, "alice")

        version = result.result["entity"]["version"]
        assert version.endswith("-alice")
        assert Entity.version_timestamp(version) is not None

    async def test_unknown_entity_type_is_a_reported_error(self, empty_graph):
        result = await empty_graph.create_entity_tool("spaceship", "X", {}, "alice")

        assert result.success is False
        assert result.result is None
        assert "not a valid EntityType" in result.error
        assert await empty_graph.get_entities_by_type(EntityType.DEVICE) == []


class TestCreateRelationshipTool:
    async def test_creates_a_valid_relationship(self, house):
        house.add_entity(make_entity("device-fan", EntityType.DEVICE, "Fan"))

        result = await house.create_relationship_tool(
            "device-fan", "room-kitchen", "located_in", {"position": "ceiling"}, "alice"
        )

        assert result.success is True
        assert result.result["created"] is True
        payload = result.result["relationship"]
        assert payload["from_entity"] == {"id": "device-fan", "name": "Fan"}
        assert payload["to_entity"] == {"id": "room-kitchen", "name": "Kitchen"}
        assert payload["type"] == "located_in"
        assert payload["properties"] == {"position": "ceiling"}

        stored = await house.get_relationships(from_id="device-fan")
        assert [r.id for r in stored] == [payload["id"]]
        assert stored[0].relationship_type == RelationshipType.LOCATED_IN

    async def test_records_the_versions_of_both_endpoints(self, house):
        house.add_entity(make_entity("device-fan", EntityType.DEVICE, "Fan", version="v7"))

        await house.create_relationship_tool("device-fan", "room-kitchen", "located_in")

        stored = (await house.get_relationships(from_id="device-fan"))[0]
        assert stored.from_entity_version == "v7"
        assert stored.to_entity_version == "v1"
        assert stored.user_id == "system"  # default when no user is supplied

    async def test_missing_source_entity_is_an_error(self, house):
        result = await house.create_relationship_tool("ghost", "room-kitchen", "located_in")

        assert result.success is False
        assert result.error == "From entity ghost not found"

    async def test_missing_target_entity_is_an_error(self, house):
        result = await house.create_relationship_tool("device-light", "ghost", "located_in")

        assert result.success is False
        assert result.error == "To entity ghost not found"

    async def test_unknown_relationship_type_is_a_reported_error(self, house):
        result = await house.create_relationship_tool(
            "device-light", "room-kitchen", "teleports_to"
        )

        assert result.success is False
        assert "not a valid RelationshipType" in result.error

    async def test_invalid_entity_type_combination_is_rejected(self, house):
        # CONTROLS is only valid device->device, automation->device and
        # schedule->device/automation; room->home is not allowed.
        result = await house.create_relationship_tool("room-kitchen", "home-1", "controls")

        assert result.success is False
        assert result.error == (
            "Invalid relationship: room cannot have controls relationship to home"
        )

    async def test_rejected_relationship_is_not_stored(self, house):
        before = len(await house.get_relationships())

        await house.create_relationship_tool("room-kitchen", "home-1", "controls")

        assert len(await house.get_relationships()) == before

    async def test_properties_default_to_empty(self, house):
        house.add_entity(make_entity("device-fan", EntityType.DEVICE, "Fan"))

        result = await house.create_relationship_tool(
            "device-fan", "room-kitchen", "located_in"
        )

        assert result.result["relationship"]["properties"] is None
        stored = (await house.get_relationships(from_id="device-fan"))[0]
        assert stored.properties == {}


class TestFindPathTool:
    async def test_reports_the_path_and_its_hop_count(self, house):
        result = await house.find_path_tool("device-hub", "home-1")

        assert result.success is True
        assert result.result["from"] == "device-hub"
        assert result.result["to"] == "home-1"
        assert result.result["found"] is True
        assert result.result["path"] == [
            {"id": "device-hub", "name": "Smart Hub", "type": "device"},
            {"id": "room-living", "name": "Living Room", "type": "room"},
            {"id": "home-1", "name": "Test Home", "type": "home"},
        ]
        # length counts edges, not nodes.
        assert result.result["length"] == 2

    async def test_no_path_is_a_success_with_found_false(self, house):
        result = await house.find_path_tool("home-1", "device-hub")

        assert result.success is True
        assert result.error is None
        assert result.result == {
            "from": "home-1",
            "to": "device-hub",
            "path": [],
            "length": 0,
            "found": False,
        }

    async def test_max_depth_is_forwarded(self, house):
        assert (await house.find_path_tool("device-hub", "home-1", max_depth=1)).result[
            "found"
        ] is False
        assert (await house.find_path_tool("device-hub", "home-1", max_depth=2)).result[
            "found"
        ] is True

    async def test_unknown_entities_report_not_found_rather_than_failing(self, house):
        result = await house.find_path_tool("ghost-a", "ghost-b")

        assert result.success is True
        assert result.result["found"] is False


class TestGetEntityDetailsTool:
    async def test_returns_the_entity_with_both_edge_directions(self, house):
        result = await house.get_entity_details_tool("device-light")

        assert result.success is True
        assert result.result["entity"]["name"] == "Kitchen Light"
        assert result.result["current_version"] == "v1"
        assert result.result["relationships"]["outgoing"] == [
            {"to": "room-kitchen", "type": "located_in", "properties": {}},
            {"to": "manual-1", "type": "documented_by", "properties": {}},
        ]
        assert result.result["relationships"]["incoming"] == [
            {"from": "device-hub", "type": "controls", "properties": {}},
            {"from": "automation-1", "type": "automates", "properties": {}},
            {"from": "procedure-1", "type": "procedure_for", "properties": {}},
        ]

    async def test_relationship_properties_are_included(self, house):
        result = await house.get_entity_details_tool("room-kitchen")

        outgoing = {r["to"]: r for r in result.result["relationships"]["outgoing"]}
        assert outgoing["room-hall"]["properties"] == {"via": "doorway"}

    async def test_isolated_entity_has_no_relationships(self, house):
        result = await house.get_entity_details_tool("note-1")

        assert result.result["relationships"] == {"outgoing": [], "incoming": []}

    async def test_version_count_falls_back_to_one_without_history_support(self, house):
        # InMemoryGraph has no get_entity_versions, so the tool reports the
        # single current version.
        await house.update_entity("device-light", {"name": "Ceiling Light"}, "alice")

        result = await house.get_entity_details_tool("device-light")

        assert result.result["version_count"] == 1

    async def test_version_count_uses_the_backend_history_when_available(self):
        graph = VersionedInMemoryGraph()
        graph.add_entity(make_entity("d", EntityType.DEVICE, "Device"))
        await graph.update_entity("d", {"name": "Device v2"}, "alice")
        await graph.update_entity("d", {"name": "Device v3"}, "bob")

        result = await graph.get_entity_details_tool("d")

        assert result.result["version_count"] == 3
        assert result.result["entity"]["name"] == "Device v3"

    async def test_unknown_entity_is_an_error(self, house):
        result = await house.get_entity_details_tool("ghost")

        assert result.success is False
        assert result.error == "Entity ghost not found"


class TestFindSimilarEntitiesTool:
    async def test_returns_scored_similar_entities(self, house):
        result = await house.find_similar_entities_tool("device-light")

        assert result.success is True
        assert result.result["reference_entity_id"] == "device-light"
        assert [e["id"] for e in result.result["similar_entities"]] == ["device-hub"]
        assert result.result["count"] == 1
        assert result.result["similar_entities"][0]["score"] > 0

    async def test_limit_is_forwarded(self, empty_graph):
        for i in range(4):
            empty_graph.add_entity(
                make_entity(f"d{i}", EntityType.DEVICE, f"Light {i}", {"watts": 9})
            )

        result = await empty_graph.find_similar_entities_tool("d0", limit=2)

        assert result.result["count"] == 2

    async def test_unknown_entity_is_an_empty_result(self, house):
        result = await house.find_similar_entities_tool("ghost")

        assert result.success is True
        assert result.result["similar_entities"] == []
        assert result.result["count"] == 0


class TestGetProceduresForDeviceTool:
    async def test_collects_procedures_and_manuals(self, house):
        result = await house.get_procedures_for_device_tool("device-light")

        assert result.success is True
        assert result.result["device_id"] == "device-light"
        assert result.result["device_name"] == "Kitchen Light"
        assert result.result["procedures"] == [
            {
                "id": "procedure-1",
                "name": "Reset Kitchen Light",
                "content": {"steps": ["hold button", "release"]},
            }
        ]
        assert result.result["manuals"] == [
            {"id": "manual-1", "name": "Kitchen Light Manual", "content": {"pages": 12}}
        ]
        assert result.result["total_documentation"] == 2

    async def test_documentation_of_the_wrong_entity_type_is_ignored(self, house):
        # DOCUMENTED_BY may also point at a NOTE, which is not a manual.
        house.connect(
            "rel-light-note", "device-light", "note-1", RelationshipType.DOCUMENTED_BY
        )

        result = await house.get_procedures_for_device_tool("device-light")

        assert [m["id"] for m in result.result["manuals"]] == ["manual-1"]
        assert result.result["total_documentation"] == 2

    async def test_device_without_documentation(self, house):
        result = await house.get_procedures_for_device_tool("device-hub")

        assert result.result["procedures"] == []
        assert result.result["manuals"] == []
        assert result.result["total_documentation"] == 0

    async def test_unknown_device_is_an_error(self, house):
        result = await house.get_procedures_for_device_tool("ghost")

        assert result.success is False
        assert result.error == "Device ghost not found"

    async def test_entity_that_is_not_a_device_is_an_error(self, house):
        result = await house.get_procedures_for_device_tool("room-kitchen")

        assert result.success is False
        assert result.error == "Device room-kitchen not found"


class TestGetAutomationsInRoomTool:
    async def test_finds_automations_through_the_rooms_devices(self, house):
        result = await house.get_automations_in_room_tool("room-kitchen")

        assert result.success is True
        assert result.result["room_id"] == "room-kitchen"
        assert result.result["room_name"] == "Kitchen"
        assert result.result["automation_count"] == 1
        automation = result.result["automations"][0]
        assert automation["id"] == "automation-1"
        assert automation["name"] == "Evening Lights"
        assert automation["content"] == {"enabled": True}
        assert automation["affects_devices"] == [
            {"id": "device-light", "name": "Kitchen Light"}
        ]

    async def test_an_automation_covering_two_devices_is_reported_once(self, empty_graph):
        empty_graph.add_entity(make_entity("room", EntityType.ROOM, "Room"))
        empty_graph.add_entity(make_entity("d1", EntityType.DEVICE, "Device 1"))
        empty_graph.add_entity(make_entity("d2", EntityType.DEVICE, "Device 2"))
        empty_graph.add_entity(make_entity("auto", EntityType.AUTOMATION, "Automation"))
        empty_graph.connect("r1", "d1", "room", RelationshipType.LOCATED_IN)
        empty_graph.connect("r2", "d2", "room", RelationshipType.LOCATED_IN)
        empty_graph.connect("r3", "auto", "d1", RelationshipType.AUTOMATES)
        empty_graph.connect("r4", "auto", "d2", RelationshipType.AUTOMATES)

        result = await empty_graph.get_automations_in_room_tool("room")

        assert result.result["automation_count"] == 1
        affected = result.result["automations"][0]["affects_devices"]
        assert sorted(d["id"] for d in affected) == ["d1", "d2"]

    async def test_non_automation_sources_are_ignored(self, empty_graph):
        empty_graph.add_entity(make_entity("room", EntityType.ROOM, "Room"))
        empty_graph.add_entity(make_entity("d1", EntityType.DEVICE, "Device 1"))
        empty_graph.add_entity(make_entity("sched", EntityType.SCHEDULE, "Schedule"))
        empty_graph.connect("r1", "d1", "room", RelationshipType.LOCATED_IN)
        empty_graph.connect("r2", "sched", "d1", RelationshipType.AUTOMATES)

        result = await empty_graph.get_automations_in_room_tool("room")

        assert result.result["automations"] == []
        assert result.result["automation_count"] == 0

    async def test_room_without_automated_devices(self, house):
        result = await house.get_automations_in_room_tool("room-living")

        assert result.success is True
        assert result.result["automation_count"] == 0

    async def test_unknown_room_is_an_error(self, house):
        result = await house.get_automations_in_room_tool("ghost")

        assert result.success is False
        assert result.error == "Room ghost not found"

    async def test_entity_that_is_not_a_room_is_an_error(self, house):
        result = await house.get_automations_in_room_tool("device-light")

        assert result.success is False
        assert result.error == "Room device-light not found"


class TestUpdateEntityTool:
    async def test_reports_the_new_version_and_its_parent(self, house):
        result = await house.update_entity_tool("device-light", {"name": "Ceiling"}, "alice")

        assert result.success is True
        assert result.result["entity_id"] == "device-light"
        assert result.result["new_version"] != "v1"
        assert result.result["parent_versions"] == ["v1"]
        assert (await house.get_entity("device-light")).name == "Ceiling"

    async def test_echoes_the_requested_changes(self, house):
        result = await house.update_entity_tool("device-light", {"name": "Ceiling"}, "alice")

        assert result.result["changes_applied"] == {"name": "Ceiling"}

    async def test_unknown_entity_is_a_reported_error_not_an_exception(self, house):
        result = await house.update_entity_tool("ghost", {"name": "x"}, "alice")

        assert result.success is False
        assert result.result is None
        assert result.error == "Entity ghost not found"


class TestBackendFailuresBecomeToolErrors:
    """Every tool converts an unexpected backend exception into an error result."""

    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda g: g.get_devices_in_room("r"), id="get_devices_in_room"),
            pytest.param(lambda g: g.find_device_controls("d"), id="find_device_controls"),
            pytest.param(lambda g: g.get_room_connections("r"), id="get_room_connections"),
            pytest.param(
                lambda g: g.create_relationship_tool("a", "b", "located_in"),
                id="create_relationship_tool",
            ),
            pytest.param(lambda g: g.get_entity_details_tool("e"), id="get_entity_details_tool"),
            pytest.param(
                lambda g: g.get_procedures_for_device_tool("d"),
                id="get_procedures_for_device_tool",
            ),
            pytest.param(
                lambda g: g.get_automations_in_room_tool("r"),
                id="get_automations_in_room_tool",
            ),
            pytest.param(
                lambda g: g.update_entity_tool("e", {"name": "x"}, "alice"),
                id="update_entity_tool",
            ),
            pytest.param(
                lambda g: g.find_similar_entities_tool("e"), id="find_similar_entities_tool"
            ),
            pytest.param(lambda g: g.find_path_tool("a", "a"), id="find_path_tool"),
        ],
    )
    async def test_exception_is_reported_as_a_failed_tool_result(self, exploding, call):
        result = await call(exploding)

        assert result.success is False
        assert result.result is None
        assert result.error == ExplodingGraph.MESSAGE
