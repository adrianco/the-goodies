#!/usr/bin/env python3
"""
Improved Chat Interface for The Goodies
========================================

Standalone chat interface that uses only blowing-off and inbetweenies
for smart home queries with multi-model support and comparison capabilities.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from llama_cpp import Llama
from blowing_off import BlowingOffClient
from inbetweenies.models import EntityType

from query_processor import QueryProcessor, QueryIntent
from model_manager import ModelManager
from response_logger import ResponseLogger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImprovedChatInterface:
    """Enhanced standalone chat interface for smart home queries"""

    def __init__(self, model_name: str = 'mistral'):
        """
        Initialize improved chat interface

        Args:
            model_name: Name of model to use (mistral, phi3, tinyllama)
        """
        self.model_name = model_name
        self.model_manager = ModelManager()
        self.model = self.model_manager.load_model(model_name)
        self.query_processor = QueryProcessor()
        self.response_logger = ResponseLogger()
        self.client = None

    async def initialize(self):
        """Initialize the blowing-off client connection"""
        try:
            logger.info("Initializing blowing-off client...")
            self.client = BlowingOffClient()
            await self.client.connect()
            logger.info("Client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize client: {e}")
            raise

    async def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process a natural language query and return response with metadata

        Args:
            query: Natural language query from user

        Returns:
            Dictionary containing response and metadata
        """
        start_time = time.time()

        # Analyze query to determine intent and MCP tool
        intent = self.query_processor.analyze(query)

        # Build context for LLM
        context = self._build_context(query, intent)

        # Execute MCP tool if needed
        tool_result = None
        if intent.tool:
            try:
                tool_result = await self._execute_tool(intent)
                context = self._add_tool_result_to_context(context, tool_result)
            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                context += f"\n\nTool execution failed: {e}"

        # Generate response from model
        response_text = self._generate_response(context)

        # Calculate metrics
        elapsed_time = (time.time() - start_time) * 1000  # Convert to ms

        # Create response object
        response = {
            'query': query,
            'response': response_text,
            'model': self.model_name,
            'intent': {
                'tool': intent.tool,
                'params': intent.params
            },
            'tool_result': tool_result,
            'metrics': {
                'response_time_ms': elapsed_time,
                'timestamp': time.time()
            }
        }

        # Log response for comparison
        self.response_logger.log(response)

        return response

    def _build_context(self, query: str, intent: QueryIntent) -> str:
        """Build context for LLM including system prompt and query"""
        system_prompt = """You are a helpful assistant for a smart home system.
You have access to information about devices, rooms, and automations.
Answer questions clearly and concisely based on the available data.
If you receive data from the system, incorporate it naturally into your response."""

        context = f"{system_prompt}\n\nUser Query: {query}"

        if intent.tool:
            context += f"\n\nSystem will use tool: {intent.tool}"
            if intent.params:
                context += f" with parameters: {intent.params}"

        return context

    async def _execute_tool(self, intent: QueryIntent) -> Dict[str, Any]:
        """Execute the MCP tool based on intent"""
        if not self.client:
            raise Exception("Client not initialized")

        # Map our intent to blowing-off client methods
        tool_mapping = {
            'search_entities': self.client.search_entities,
            'get_devices_in_room': self.client.get_devices_in_room,
            'list_entities': self.client.list_entities,
            'get_entity': self.client.get_entity,
            'find_similar_entities': self.client.find_similar_entities
        }

        tool_func = tool_mapping.get(intent.tool)
        if not tool_func:
            raise ValueError(f"Unknown tool: {intent.tool}")

        # Execute tool with parameters
        result = await tool_func(**intent.params)
        return result

    def _add_tool_result_to_context(self, context: str, tool_result: Any) -> str:
        """Add tool execution results to context"""
        if tool_result:
            # Format result for context
            if isinstance(tool_result, list):
                result_str = f"\n\nSystem found {len(tool_result)} items:"
                for item in tool_result[:10]:  # Limit to first 10 items
                    if hasattr(item, 'name'):
                        result_str += f"\n- {item.name}"
                    else:
                        result_str += f"\n- {str(item)}"
                if len(tool_result) > 10:
                    result_str += f"\n... and {len(tool_result) - 10} more"
            else:
                result_str = f"\n\nSystem data: {json.dumps(tool_result, indent=2)}"

            context += result_str

        return context

    def _generate_response(self, context: str) -> str:
        """Generate response from LLM model"""
        try:
            response = self.model(
                context,
                max_tokens=256,
                temperature=0.7,
                top_p=0.9,
                stop=["User:", "System:", "\n\n"]
            )

            return response['choices'][0]['text'].strip()
        except Exception as e:
            logger.error(f"Model generation failed: {e}")
            return f"I encountered an error generating a response: {e}"

    async def compare_models(self, query: str) -> Dict[str, Any]:
        """
        Run the same query on all models for comparison

        Args:
            query: Query to test on all models

        Returns:
            Comparison results from all models
        """
        results = {}

        for model_name in ModelManager.MODELS.keys():
            # Load model
            self.model_name = model_name
            self.model = self.model_manager.load_model(model_name)

            # Process query
            response = await self.process_query(query)
            results[model_name] = response

            # Small delay between models to avoid resource conflicts
            await asyncio.sleep(1)

        return results

    async def interactive_session(self):
        """Run an interactive chat session"""
        print("🤖 Smart Home Chat Interface")
        print(f"Model: {self.model_name}")
        print("=" * 40)
        print("Ask questions about your smart home devices!")
        print("Type 'quit' to exit, 'compare' to test all models\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("Goodbye! 👋")
                    break

                if user_input.lower() == 'compare':
                    test_query = input("Enter query to compare: ").strip()
                    print("\n🔄 Comparing models...")
                    results = await self.compare_models(test_query)

                    print("\n📊 Comparison Results:")
                    for model, result in results.items():
                        print(f"\n{model}:")
                        print(f"  Response: {result['response'][:100]}...")
                        print(f"  Time: {result['metrics']['response_time_ms']:.1f}ms")
                    continue

                if not user_input:
                    continue

                # Process query
                print("Assistant: ", end="", flush=True)
                response = await self.process_query(user_input)
                print(response['response'])

                # Show metrics in debug mode
                if logger.level == logging.DEBUG:
                    print(f"  [Time: {response['metrics']['response_time_ms']:.1f}ms]")

                print()  # Empty line for readability

            except KeyboardInterrupt:
                print("\n\nGoodbye! 👋")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                print(f"Sorry, I encountered an error: {e}")

    async def cleanup(self):
        """Clean up resources"""
        if self.client:
            await self.client.disconnect()


async def main():
    """Main entry point for improved chat interface"""
    import argparse

    parser = argparse.ArgumentParser(description='Improved Smart Home Chat Interface')
    parser.add_argument('--model', choices=['mistral', 'phi3', 'tinyllama'],
                       default='mistral', help='Model to use')
    parser.add_argument('--compare', action='store_true',
                       help='Run comparison mode')
    parser.add_argument('--query', type=str,
                       help='Single query to process')
    args = parser.parse_args()

    # Create chat interface
    chat = ImprovedChatInterface(model_name=args.model)

    try:
        await chat.initialize()

        if args.query:
            # Process single query
            if args.compare:
                results = await chat.compare_models(args.query)
                print(json.dumps(results, indent=2))
            else:
                response = await chat.process_query(args.query)
                print(json.dumps(response, indent=2))
        else:
            # Interactive mode
            await chat.interactive_session()

    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        await chat.cleanup()


if __name__ == "__main__":
    asyncio.run(main())