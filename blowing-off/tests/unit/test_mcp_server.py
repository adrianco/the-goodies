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
        schema = tool.inputSchema
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
    from mcp.types import CallToolRequest
    handler = server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params={"name": "search_entities", "arguments": {"query": "lamp"}},
    )
    result = asyncio.run(handler(req))

    assert client.calls == [("search_entities", {"query": "lamp"})]
    # The text content carries the tool's result payload.
    blocks = result.root.content
    assert blocks[0].type == "text"
    assert '"ok": true' in blocks[0].text
