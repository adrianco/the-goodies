"""Synchronous unit tests for the Blowing-Off MCP server.

These don't need a live FunkyGibbon server: they check the exposed tool surface
matches the KittenKong reference, the schemas are well-formed, and the
result-formatting maps client results to the right MCP payload.
"""

import asyncio

from blowingoff.mcp.server import TOOLS, result_payload, build_server

# The 12 knowledge-graph tools the KittenKong MCP server exposes.
EXPECTED_TOOLS = {
    "search_entities", "get_entity_details", "create_entity", "update_entity",
    "create_relationship", "get_devices_in_room", "find_device_controls",
    "get_room_connections", "find_path", "find_similar_entities",
    "get_procedures_for_device", "get_automations_in_room",
}


def test_tool_surface_matches_kittenkong():
    names = {t.name for t in TOOLS}
    assert names == EXPECTED_TOOLS
    assert len(TOOLS) == 12


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
