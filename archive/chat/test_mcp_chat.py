#!/usr/bin/env python3
"""
Test script for TinyLlama MCP Chat
===================================

Quick test to verify the chat interface works with MCP tools.
"""

import asyncio
import sys
sys.path.append('/workspaces/the-goodies')

from chat.tinyllama_mcp_chat import TinyLlamaMCPChat


async def test_chat():
    """Test the chat interface with a few queries"""
    print("🧪 Testing TinyLlama MCP Chat\n")

    chat = TinyLlamaMCPChat()

    try:
        # Initialize
        await chat.initialize()
        print("\n✅ Initialization successful\n")

        # Test queries
        test_queries = [
            "List all devices",
            "Search for lights",
            "What devices are in the living room?"
        ]

        for query in test_queries:
            print(f"📝 Testing: {query}")
            response = await chat.process_query(query)
            print(f"💬 Response: {response}\n")
            print("-" * 40 + "\n")

        print("✅ All tests completed!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await chat.cleanup()


if __name__ == "__main__":
    # Wait a moment for server to start
    import time
    print("⏳ Waiting for funkygibbon server to start...")
    time.sleep(3)

    asyncio.run(test_chat())