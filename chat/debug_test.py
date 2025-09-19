#!/usr/bin/env python3
"""Debug what the MCP tools return"""

import asyncio
import sys
import json
sys.path.append('/workspaces/the-goodies')

from blowingoff.client import BlowingOffClient


async def test():
    client = BlowingOffClient(db_path="/tmp/blowing-off-debug.db")

    # Connect and sync
    await client.connect(
        server_url="http://localhost:8000",
        password="admin"
    )
    await client.sync()

    # Test MCP tool execution
    print("Testing list_entities with ROOM type:")
    result = await client.execute_mcp_tool("list_entities", entity_type="ROOM")
    print(f"Type: {type(result)}")
    print(f"Result: {result}")
    print()

    print("Testing list_entities with no params:")
    result = await client.execute_mcp_tool("list_entities")
    print(f"Type: {type(result)}")
    print(f"Length: {len(result) if isinstance(result, list) else 'N/A'}")
    if isinstance(result, list) and len(result) > 0:
        print(f"First item type: {type(result[0])}")
        print(f"First item: {result[0]}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(test())