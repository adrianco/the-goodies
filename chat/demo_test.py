#!/usr/bin/env python3
"""
Demo script to capture example output for documentation
"""

import asyncio
import sys
sys.path.append('/workspaces/the-goodies')

from chat.tinyllama_mcp_chat import TinyLlamaMCPChat


async def demo():
    """Run demo queries"""
    print("=== TinyLlama MCP Chat Demo ===\n")

    chat = TinyLlamaMCPChat()

    try:
        await chat.initialize()
        print("\n" + "="*50)

        # Test queries
        queries = [
            "List all devices",
            "Search for lights",
            "What devices are in the living room?"
        ]

        for query in queries:
            print(f"\n🗣️ User: {query}")
            response = await chat.process_query(query)
            print(f"🤖 Assistant: {response}")
            print("-" * 40)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await chat.cleanup()


if __name__ == "__main__":
    asyncio.run(demo())