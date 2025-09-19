#!/usr/bin/env python3
"""
TinyLlama Chat with Blowing-off MCP Integration
===============================================

Chat interface using TinyLlama model with MCP tools from blowing-off client.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import sys

# Add parent directory for imports
sys.path.append('/workspaces/the-goodies')

from llama_cpp import Llama
from blowingoff.client import BlowingOffClient


class TinyLlamaMCPChat:
    """Chat interface using TinyLlama with MCP tools"""

    def __init__(self, model_path: str = "chat/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"):
        """Initialize chat with TinyLlama and blowing-off client"""
        self.model_path = model_path
        self.model = None
        self.client = None
        self.tools = []

    async def initialize(self):
        """Initialize model and blowing-off client"""
        print("🚀 Initializing TinyLlama MCP Chat...")

        # Load TinyLlama model
        print("📦 Loading TinyLlama model...")
        if not Path(self.model_path).exists():
            raise FileNotFoundError(f"Model not found: {self.model_path}")

        self.model = Llama(
            model_path=self.model_path,
            n_ctx=512,  # Small context for speed
            n_threads=2,
            n_gpu_layers=0,
            verbose=False
        )
        print("✅ Model loaded")

        # Initialize blowing-off client
        print("🔌 Connecting to blowing-off client...")
        self.client = BlowingOffClient(
            db_path="/tmp/blowing-off-chat.db"
        )

        # Connect and sync with funkygibbon
        await self.client.connect(
            server_url="http://localhost:8000",
            password="admin"  # Using dev mode password
        )
        print("✅ Connected to server")

        # Sync data
        print("🔄 Syncing data from funkygibbon...")
        result = await self.client.sync()
        if result.success:
            print(f"✅ Synced {result.entities_synced} entities")
        else:
            print("⚠️ Sync failed, using local data only")

        # Get available MCP tools
        self.tools = self._get_available_tools()
        print(f"🛠️ {len(self.tools)} MCP tools available")

    def _get_available_tools(self) -> list:
        """Get list of available MCP tools"""
        return [
            {"name": "search_entities", "description": "Search for entities by query"},
            {"name": "list_entities", "description": "List all entities"},
            {"name": "get_devices_in_room", "description": "Get devices in a specific room"},
            {"name": "find_device_controls", "description": "Find what controls a device"},
            {"name": "find_similar_entities", "description": "Find entities similar to a given one"},
            {"name": "get_automations_in_room", "description": "Get automations for a room"},
            {"name": "get_procedures_for_device", "description": "Get procedures for a device"},
            {"name": "get_room_connections", "description": "Get connections between rooms"},
            {"name": "find_path", "description": "Find path between locations"}
        ]

    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Execute an MCP tool"""
        print(f"  🔧 Executing: {tool_name}({params})")

        try:
            # Map tool names to client methods
            if tool_name == "search_entities":
                query = params.get('query', '')
                result = await self.client.search_entities(query)
            elif tool_name == "list_entities":
                entity_type = params.get('entity_type')
                result = await self.client.list_entities(entity_type)
            elif tool_name == "get_devices_in_room":
                room_id = params.get('room_id', '')
                result = await self.client.get_devices_in_room(room_id)
            elif tool_name == "find_device_controls":
                device_id = params.get('device_id', '')
                result = await self.client.find_device_controls(device_id)
            elif tool_name == "find_similar_entities":
                entity_id = params.get('entity_id', '')
                result = await self.client.find_similar_entities(entity_id)
            else:
                result = {"error": f"Tool {tool_name} not implemented yet"}

            return result
        except Exception as e:
            return {"error": str(e)}

    def parse_query_for_tool(self, query: str) -> Optional[Dict[str, Any]]:
        """Simple pattern matching to identify tool needs"""
        query_lower = query.lower()

        # Pattern matching for different query types
        if "list" in query_lower or "show all" in query_lower:
            if "device" in query_lower:
                return {"tool": "list_entities", "params": {"entity_type": "DEVICE"}}
            elif "room" in query_lower:
                return {"tool": "list_entities", "params": {"entity_type": "ROOM"}}
            else:
                return {"tool": "list_entities", "params": {}}

        elif "search" in query_lower or "find" in query_lower:
            # Extract search term
            for word in ["search for ", "find ", "look for "]:
                if word in query_lower:
                    search_term = query_lower.split(word)[-1].strip()
                    return {"tool": "search_entities", "params": {"query": search_term}}

        elif "in the" in query_lower or "devices in" in query_lower:
            # Room-based queries
            words = query_lower.split()
            if "room" in words:
                # Try to extract room name
                room_idx = words.index("room")
                if room_idx > 0:
                    room_name = words[room_idx - 1]
                    return {"tool": "get_devices_in_room", "params": {"room_id": f"*{room_name}*"}}

        elif "control" in query_lower:
            # Control relationships
            return {"tool": "find_device_controls", "params": {"device_id": "garage_door"}}

        elif "similar" in query_lower or "like" in query_lower:
            # Similarity queries
            return {"tool": "find_similar_entities", "params": {"entity_id": "light"}}

        return None

    async def process_query(self, query: str) -> str:
        """Process a user query with potential tool execution"""
        print(f"\n💭 Processing: {query}")

        # Check if we need to use a tool
        tool_info = self.parse_query_for_tool(query)

        context = f"User Query: {query}\n"

        if tool_info:
            # Execute the tool
            result = await self.execute_tool(tool_info['tool'], tool_info['params'])

            # Format result for context
            if isinstance(result, list):
                context += f"\nFound {len(result)} items:\n"
                for item in result[:5]:  # Show first 5
                    if hasattr(item, 'name'):
                        context += f"- {item.name}\n"
                    elif isinstance(item, dict) and 'name' in item:
                        context += f"- {item['name']}\n"
                if len(result) > 5:
                    context += f"... and {len(result) - 5} more\n"
            else:
                context += f"\nData: {json.dumps(result, indent=2)[:200]}\n"

        # Generate response with TinyLlama
        prompt = f"""{context}

Please provide a helpful response about the smart home data.
Assistant:"""

        response = self.model(
            prompt,
            max_tokens=128,
            temperature=0.7,
            top_p=0.9,
            stop=["User:", "\n\n"]
        )

        response_text = response['choices'][0]['text'].strip()
        return response_text

    async def chat_loop(self):
        """Interactive chat loop"""
        print("\n" + "="*50)
        print("🏠 Smart Home Chat with MCP Tools")
        print("="*50)
        print("Using TinyLlama model with blowing-off MCP integration")
        print("Type 'quit' to exit, 'tools' to list available tools\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break

                if user_input.lower() == 'tools':
                    print("\n🛠️ Available MCP Tools:")
                    for tool in self.tools:
                        print(f"  - {tool['name']}: {tool['description']}")
                    print()
                    continue

                if user_input.lower() == 'help':
                    print("\n📖 Example queries:")
                    print("  - List all devices")
                    print("  - Search for lights")
                    print("  - What devices are in the living room?")
                    print("  - Find temperature sensors")
                    print("  - Show all rooms")
                    print()
                    continue

                if not user_input:
                    continue

                # Process query
                response = await self.process_query(user_input)
                print(f"Assistant: {response}\n")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}\n")

    async def cleanup(self):
        """Clean up resources"""
        if self.client:
            await self.client.disconnect()
        if self.model:
            del self.model


async def main():
    """Main entry point"""
    chat = TinyLlamaMCPChat()

    try:
        await chat.initialize()
        await chat.chat_loop()
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await chat.cleanup()


if __name__ == "__main__":
    asyncio.run(main())