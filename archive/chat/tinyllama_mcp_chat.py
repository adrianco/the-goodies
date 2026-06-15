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
        if result and hasattr(result, 'success'):
            if result.success:
                print(f"✅ Data synced successfully")
            else:
                print("⚠️ Sync failed, using local data only")
        else:
            print("✅ Data synced")

        # Get available MCP tools
        self.tools = self._get_available_tools()
        print(f"🛠️ {len(self.tools)} MCP tools available")

    def _get_available_tools(self) -> list:
        """Get list of available MCP tools"""
        # These are the actual MCP tools available from the server
        return [
            {"name": "search_entities", "description": "Search for entities by query"},
            {"name": "get_devices_in_room", "description": "Get devices in a specific room"},
            {"name": "find_device_controls", "description": "Find what controls a device"},
            {"name": "find_similar_entities", "description": "Find entities similar to a given one"},
            {"name": "get_automations_in_room", "description": "Get automations for a room"},
            {"name": "get_procedures_for_device", "description": "Get procedures for a device"},
            {"name": "get_room_connections", "description": "Get connections between rooms"},
            {"name": "find_path", "description": "Find path between locations"},
            {"name": "get_entity_details", "description": "Get details about a specific entity"},
            {"name": "create_entity", "description": "Create a new entity"},
            {"name": "update_entity", "description": "Update an existing entity"},
            {"name": "create_relationship", "description": "Create a relationship between entities"}
        ]

    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Execute an MCP tool"""
        print(f"  🔧 Executing: {tool_name}({params})")

        try:
            # Use execute_mcp_tool with kwargs
            result = await self.client.execute_mcp_tool(tool_name, **params)
            return result
        except Exception as e:
            print(f"  ❌ Error executing tool: {e}")
            return {"error": str(e)}

    async def get_room_by_name(self, room_name: str) -> Optional[str]:
        """Get room entity ID by searching for room name"""
        try:
            # Search for the room by name
            rooms = await self.client.execute_mcp_tool("search_entities", query=room_name)
            if isinstance(rooms, list) and len(rooms) > 0:
                for room in rooms:
                    if hasattr(room, 'entity_type') and room.entity_type == 'ROOM':
                        return room.entity_id if hasattr(room, 'entity_id') else room.get('entity_id')
                    elif isinstance(room, dict) and room.get('entity_type') == 'ROOM':
                        return room.get('entity_id')
        except:
            pass
        return None

    def parse_query_for_tool(self, query: str) -> Optional[Dict[str, Any]]:
        """Simple pattern matching to identify tool needs"""
        query_lower = query.lower()

        # Pattern matching for different query types
        if "list" in query_lower or "show" in query_lower:
            # Check for specific entity types mentioned
            if "thermostat" in query_lower:
                return {"tool": "search_entities", "params": {"query": "thermostat"}}
            elif "light" in query_lower:
                return {"tool": "search_entities", "params": {"query": "light"}}
            elif "sensor" in query_lower:
                return {"tool": "search_entities", "params": {"query": "sensor"}}
            elif "device" in query_lower:
                return {"tool": "search_entities", "params": {"query": "device"}}
            elif "room" in query_lower:
                return {"tool": "search_entities", "params": {"query": "room"}}
            elif "entit" in query_lower or "all" in query_lower:
                return {"tool": "search_entities", "params": {"query": "*"}}
            else:
                # Default to searching all entities
                return {"tool": "search_entities", "params": {"query": "*"}}

        elif "search" in query_lower or "find" in query_lower or "look for" in query_lower:
            # Extract search term
            for word in ["search for ", "find ", "look for "]:
                if word in query_lower:
                    search_term = query_lower.split(word)[-1].strip()
                    return {"tool": "search_entities", "params": {"query": search_term}}
            # If no specific word follows, check for common entities
            if "light" in query_lower:
                return {"tool": "search_entities", "params": {"query": "light"}}
            elif "sensor" in query_lower:
                return {"tool": "search_entities", "params": {"query": "sensor"}}

        elif ("what's in" in query_lower or "what is in" in query_lower or
              "devices in" in query_lower or "what devices are in" in query_lower):
            # Extract room name from query and search for it
            room_name = None
            if "kitchen" in query_lower:
                room_name = "kitchen"
            elif "living" in query_lower:
                room_name = "living"
            elif "bedroom" in query_lower or "master" in query_lower:
                room_name = "bedroom"
            elif "office" in query_lower:
                room_name = "office"
            elif "garage" in query_lower:
                room_name = "garage"
            elif "dining" in query_lower:
                room_name = "dining"

            if room_name:
                # We'll search for the room dynamically
                return {"tool": "search_and_get_devices", "params": {"room_name": room_name}}
            else:
                # Try to find any room mentioned
                return {"tool": "search_entities", "params": {"query": "room"}}

        elif "control" in query_lower or "climate" in query_lower or "temperature" in query_lower:
            # Search for control relationships
            if "thermostat" in query_lower or "climate" in query_lower or "temperature" in query_lower:
                return {"tool": "search_entities", "params": {"query": "thermostat"}}
            else:
                return {"tool": "search_entities", "params": {"query": "device"}}

        elif "similar" in query_lower or "like" in query_lower:
            # Similarity queries - search for something first
            return {"tool": "search_entities", "params": {"query": "light"}}

        return None

    async def process_query_with_room_search(self, query: str, room_name: str) -> str:
        """Process a query that needs room search first"""
        # First search for the room
        result = await self.client.execute_mcp_tool("search_entities", query=room_name)
        room_id = None

        # Extract rooms from result structure
        if isinstance(result, dict) and 'result' in result and 'results' in result['result']:
            rooms = result['result']['results']

            for item in rooms:
                entity = item.get('entity', {}) if isinstance(item, dict) else item
                if isinstance(entity, dict) and entity.get('entity_type', '').lower() == 'room':
                    room_id = entity.get('id')
                    break

        if room_id:
            # Get devices in the room
            devices = await self.client.execute_mcp_tool("get_devices_in_room", room_id=room_id)
            if isinstance(devices, list) and len(devices) > 0:
                context = f"Devices in the {room_name}:\n"
                for device in devices:
                    if hasattr(device, 'name'):
                        context += f"- {device.name}\n"
                    elif isinstance(device, dict):
                        context += f"- {device.get('name', 'Unknown')}\n"
                return context

        return f"No devices found in {room_name}."

    async def process_query(self, query: str) -> str:
        """Process a user query with potential tool execution"""
        print(f"\n💭 Processing: {query}")

        # Check if we need to use a tool
        tool_info = self.parse_query_for_tool(query)

        context = ""

        if tool_info:
            # Special handling for room search + device query
            if tool_info['tool'] == 'search_and_get_devices':
                context = await self.process_query_with_room_search(query, tool_info['params']['room_name'])
            else:
                # Execute the tool normally
                result = await self.execute_tool(tool_info['tool'], tool_info['params'])

                # Extract results from the response structure
                if isinstance(result, dict) and 'result' in result and 'results' in result['result']:
                    result = result['result']['results']

                # Format result for context based on tool type
                if isinstance(result, list) and len(result) > 0:
                    if tool_info['tool'] == 'search_entities':
                        query_term = tool_info['params'].get('query', '')
                        context = f"Found {len(result)} items matching '{query_term}':\n"
                        for item in result[:10]:  # Show up to 10
                            # Extract entity from search result
                            entity = None
                            if isinstance(item, dict) and 'entity' in item:
                                entity = item['entity']
                            elif hasattr(item, 'entity'):
                                entity = item.entity
                            else:
                                entity = item

                            # Extract name and type from entity
                            if isinstance(entity, dict):
                                name = entity.get('name', 'Unknown')
                                entity_type = entity.get('entity_type', 'Unknown')
                                context += f"- {name} ({entity_type})\n"
                            elif hasattr(entity, '__dict__'):
                                name = getattr(entity, 'name', 'Unknown')
                                entity_type = getattr(entity, 'entity_type', 'Unknown')
                                context += f"- {name} ({entity_type})\n"
                    elif tool_info['tool'] == 'get_devices_in_room':
                        context = f"Devices in this room:\n"
                        for item in result:
                            if hasattr(item, '__dict__'):
                                name = getattr(item, 'name', 'Unknown')
                                context += f"- {name}\n"
                            elif isinstance(item, dict):
                                name = item.get('name', 'Unknown')
                                context += f"- {name}\n"
                    else:
                        context = f"Found {len(result)} results.\n"
                elif isinstance(result, dict):
                    if 'error' in result:
                        context = f"No data available for this query.\n"
                    else:
                        # Format dict result
                        context = f"Result: {json.dumps(result, indent=2)[:300]}\n"
                else:
                    context = f"Query result: {str(result)[:300]}\n"

        # Generate response with TinyLlama
        if context:
            prompt = f"""Based on this smart home data:
{context}

User question: {query}
Please provide a helpful, concise answer about the smart home system.
Assistant:"""
        else:
            prompt = f"""User question about smart home: {query}
Please provide a helpful response about smart home systems.
Assistant:"""

        response = self.model(
            prompt,
            max_tokens=150,
            temperature=0.5,  # Lower temperature for more consistent responses
            top_p=0.9,
            stop=["User:", "\n\n", "Question:"]
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