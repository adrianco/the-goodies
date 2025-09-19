#!/usr/bin/env python3
"""Debug what search_entities returns"""

import asyncio
import sys
import json
sys.path.append('/workspaces/the-goodies')

from blowingoff.client import BlowingOffClient


async def test():
    client = BlowingOffClient(db_path="/tmp/blowing-off-debug2.db")

    # Connect and sync
    await client.connect(
        server_url="http://localhost:8000",
        password="admin"
    )
    await client.sync()

    # Test search_entities
    print("Testing search_entities with 'room':")
    result = await client.execute_mcp_tool("search_entities", query="room")
    print(f"Type: {type(result)}")
    print(f"Result: {result}")

    if isinstance(result, dict) and 'results' in result:
        items = result['results']
        print(f"Found {len(items)} items")
        if len(items) > 0:
            print(f"First item: {items[0]}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(test())