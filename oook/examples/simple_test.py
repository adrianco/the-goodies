#!/usr/bin/env python3
"""
Smoke test for oook against a running FunkyGibbon -- through the MCP tools.

Every read and write here is a tool call (the-goodies ADR-015). The earlier
version of this script mixed tool calls with the graph REST routes; those
routes are gone.

Needs a bearer token: FUNKYGIBBON_TOKEN, or FUNKYGIBBON_URL + the admin
password in FUNKYGIBBON_PASSWORD.
"""

import json
import os

import httpx

URL = os.environ.get("FUNKYGIBBON_URL", "http://localhost:8000")


def token(client: httpx.Client) -> str:
    if os.environ.get("FUNKYGIBBON_TOKEN"):
        return os.environ["FUNKYGIBBON_TOKEN"]
    resp = client.post("/api/v1/auth/admin/login",
                       json={"password": os.environ.get("FUNKYGIBBON_PASSWORD", "admin")})
    resp.raise_for_status()
    return resp.json()["access_token"]


def tool(client: httpx.Client, name: str, **arguments):
    resp = client.post(f"/api/v1/mcp/tools/{name}", json={"arguments": arguments})
    resp.raise_for_status()
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(f"{name}: {body['error']}")
    return body["result"]


def main():
    print("=== oook smoke test (MCP tools) ===\n")
    with httpx.Client(base_url=URL, timeout=10.0) as client:
        print("1. health:", client.get("/health").json())
        client.headers["Authorization"] = f"Bearer {token(client)}"

        tools = client.get("/api/v1/mcp/tools").json()["tools"]
        print(f"2. {len(tools)} tools available")

        home = tool(client, "create_entity", entity_type="home", name="Demo Home",
                    content={"address": "123 Test Street"}, user_id="oook-smoke")["entity"]
        room = tool(client, "create_entity", entity_type="room", name="Kitchen",
                    content={"area": 25}, user_id="oook-smoke")["entity"]
        oven = tool(client, "create_entity", entity_type="device", name="Smart Oven",
                    content={"manufacturer": "Samsung"}, user_id="oook-smoke")["entity"]
        print(f"3. created {home['name']}, {room['name']}, {oven['name']}")

        found = tool(client, "search_entities", query="smart", limit=10)
        print(f"4. search 'smart': {found['count']} result(s)")

        tool(client, "create_relationship", from_entity_id=oven["id"], to_entity_id=room["id"],
             relationship_type="located_in", properties={"wall": "north"})
        tool(client, "create_relationship", from_entity_id=room["id"], to_entity_id=home["id"],
             relationship_type="located_in")
        print("5. relationships created")

        connected = tool(client, "get_connected", entity_id=room["id"])
        print(f"6. kitchen has {connected['count']} connection(s)")

        stats = tool(client, "get_statistics")
        print(f"7. graph: {stats['total_entities']} entities, {stats['total_relationships']} edges")
        print("   by type:", json.dumps(stats["entity_types"]))

    print("\nok")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - a smoke script
        print(f"\nfailed: {exc}\nIs FunkyGibbon running at {URL}?")
