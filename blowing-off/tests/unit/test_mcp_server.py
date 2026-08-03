"""Synchronous unit tests for the Blowing-Off MCP server.

These don't need a live FunkyGibbon server: they check the exposed tool surface
matches the KittenKong reference, the schemas are well-formed, and the
result-formatting maps client results to the right MCP payload.
"""

import asyncio

from blowingoff.mcp.server import TOOLS, result_payload, build_server

# The 12 knowledge-graph tools the KittenKong (TypeScript) MCP server exposes.
# This is a COMPATIBILITY FLOOR, not the whole surface: every one of these must
# keep existing under the same name, because KittenKong clients call them.
KITTENKONG_TOOLS = {
    "search_entities", "get_entity_details", "create_entity", "update_entity",
    "create_relationship", "get_devices_in_room", "find_device_controls",
    "get_room_connections", "find_path", "find_similar_entities",
    "get_procedures_for_device", "get_automations_in_room",
}

# Tools the Python surface adds beyond KittenKong. Listed explicitly rather than
# left implicit so that adding one is a deliberate edit here, and so the gap
# with the TypeScript server is visible rather than discovered later.
#
# NOTE: KittenKong does not have these yet. A skill that needs to attach a photo
# must run against this server until the TypeScript side gains parity.
PYTHON_ONLY_TOOLS = {
    "attach_photo", "attach_document", "get_blob",
    "get_entity_versions", "tombstone_entity", "get_statistics",
}

EXPECTED_TOOLS = KITTENKONG_TOOLS | PYTHON_ONLY_TOOLS


def test_kittenkong_compatibility_floor_is_intact():
    """Every KittenKong tool still exists. Removing one breaks real clients."""
    names = {t.name for t in TOOLS}
    missing = KITTENKONG_TOOLS - names
    assert not missing, f"KittenKong tools dropped from the surface: {sorted(missing)}"


def test_tool_surface_is_exactly_the_declared_set():
    """No tool appears without being declared above -- including by accident."""
    assert {t.name for t in TOOLS} == EXPECTED_TOOLS
    assert len(TOOLS) == len(EXPECTED_TOOLS)


def test_the_two_transports_serve_the_same_tools():
    """The stdio server and the REST wrapper are one catalog, not two lists.

    They were two hand-maintained lists that happened to agree. This is the
    check that makes them agree by construction.
    """
    from funkygibbon.mcp.tools import MCP_TOOLS

    assert {t.name for t in TOOLS} == {t["name"] for t in MCP_TOOLS}


def test_every_tool_has_a_valid_object_schema_with_required():
    for tool in TOOLS:
        schema = tool.input_schema  # renamed from inputSchema in MCP 2.0
        assert schema["type"] == "object"
        assert "properties" in schema and isinstance(schema["properties"], dict)
        assert isinstance(schema.get("required", []), list)
        # Every required field is actually described in properties.
        for field in schema.get("required", []):
            assert field in schema["properties"], f"{tool.name}: {field} missing from properties"
        assert tool.description


def test_result_payload_success_returns_result():
    assert result_payload({"success": True, "result": {"x": 1}}) == {"x": 1}


def test_result_payload_failure_returns_error_object():
    assert result_payload({"success": False, "error": "boom"}) == {"error": "boom"}
    # Missing error string still yields an error object.
    assert "error" in result_payload({"success": False})


class _FakeClient:
    """Stand-in for BlowingOffClient that records calls and returns canned results."""
    def __init__(self, result):
        self._result = result
        self.calls = []

    async def execute_mcp_tool(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return self._result


def test_build_server_dispatches_calls_to_the_client():
    client = _FakeClient({"success": True, "result": {"ok": True}})
    server = build_server(client)
    assert server.name == "blowingoff"

    # The call-tool handler is registered; invoke it through the SDK's registry.
    # MCP 2.x keys the registry by method name and hands the handler an
    # already-validated params model plus a request context (unused here).
    entry = server.get_request_handler("tools/call")
    assert entry is not None, "tools/call handler was not registered"
    params = entry.params_type.model_validate(
        {"name": "search_entities", "arguments": {"query": "lamp"}}
    )
    result = asyncio.run(entry.handler(None, params))

    assert client.calls == [("search_entities", {"query": "lamp"})]
    # The text content carries the tool's result payload.
    blocks = result.content
    assert blocks[0].type == "text"
    assert '"ok": true' in blocks[0].text


def test_build_server_lists_the_full_tool_surface():
    """The registered tools/list handler serves exactly the TOOLS list."""
    server = build_server(_FakeClient(None))
    entry = server.get_request_handler("tools/list")
    assert entry is not None, "tools/list handler was not registered"
    result = asyncio.run(entry.handler(None, None))
    assert {t.name for t in result.tools} == EXPECTED_TOOLS


def test_build_server_reports_client_errors_as_error_payloads():
    """A failed client call still yields a text block carrying the error."""
    client = _FakeClient({"success": False, "error": "boom"})
    server = build_server(client)
    entry = server.get_request_handler("tools/call")
    params = entry.params_type.model_validate(
        {"name": "get_entity_details", "arguments": {"entity_id": "e1"}}
    )
    result = asyncio.run(entry.handler(None, params))
    assert client.calls == [("get_entity_details", {"entity_id": "e1"})]
    assert '"error": "boom"' in result.content[0].text
