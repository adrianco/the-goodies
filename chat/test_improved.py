#!/usr/bin/env python3
"""Test improved chat interface"""

import asyncio
import sys
sys.path.append('/workspaces/the-goodies')

from chat.tinyllama_mcp_chat import TinyLlamaMCPChat


async def test():
    chat = TinyLlamaMCPChat()

    try:
        await chat.initialize()
        print("\n" + "="*50)

        # Test the problematic queries
        queries = [
            "what's in the kitchen?",
            "list rooms",
            "list entities"
        ]

        for query in queries:
            print(f"\n🗣️ User: {query}")
            response = await chat.process_query(query)
            print(f"🤖 Assistant: {response}")
            print("-" * 40)

    finally:
        await chat.cleanup()


if __name__ == "__main__":
    asyncio.run(test())