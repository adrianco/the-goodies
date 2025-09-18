"""
Local LLM + MCP House Knowledge Graph Chat Application
=====================================================

This application combines a small, locally-runnable LLM with the blowing-off
MCP client library for conversational interactions with house knowledge graph data.

Location: the-goodies/chat/
Integrates with: ../blowing-off/ (MCP client library)
Tests against: funkygibbon server with sample house data

Dependencies:
- llama-cpp-python: For local LLM inference
- mcp: For Model Context Protocol client
- asyncio: For async operations
- python-dotenv: For environment variables
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import AsyncExitStack
from typing import Optional, Dict, Any, List

from llama_cpp import Llama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LocalLLMWithMCP:
    """
    A local application that combines a small LLM with MCP knowledge graph client
    for conversational interactions with house data.
    """
    
    def __init__(self, model_path: str, blowing_off_server_script: str):
        """
        Initialize the chat application with LLM model and blowing-off MCP server.
        
        Args:
            model_path: Path to the GGUF model file (relative to chat/ or absolute)
            blowing_off_server_script: Path to blowing-off server script (e.g., ../blowing-off/server.py)
        """
        self.model_path = model_path
        self.blowing_off_server_script = blowing_off_server_script
        
        # LLM configuration
        self.llm = None
        self.llm_config = {
            'n_ctx': 4096,          # Context window
            'n_threads': 8,         # CPU threads
            'n_gpu_layers': 0,      # GPU layers (set > 0 if you have GPU)
            'temperature': 0.7,     # Creativity level
            'max_tokens': 512,      # Max response length
            'top_p': 0.9,          # Nucleus sampling
            'repeat_penalty': 1.1   # Repetition penalty
        }
        
        # MCP client setup
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.mcp_tools = []
        
        # Conversation history
        self.conversation_history = []
        
    async def initialize(self):
        """Initialize both LLM and MCP client."""
        await self._initialize_llm()
        await self._initialize_mcp()
        
    async def _initialize_llm(self):
        """Initialize the local LLM."""
        try:
            logger.info(f"Loading LLM model from: {self.model_path}")
            self.llm = Llama(
                model_path=self.model_path,
                **self.llm_config
            )
            logger.info("LLM model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load LLM model: {e}")
            raise
            
    async def _initialize_mcp(self):
        """Initialize MCP client connection to the blowing-off server."""
        try:
            logger.info(f"Connecting to blowing-off MCP server: {self.blowing_off_server_script}")
            
            # Determine command based on file extension
            if self.blowing_off_server_script.endswith('.py'):
                command = "python"
            elif self.blowing_off_server_script.endswith('.js'):
                command = "node"
            else:
                raise ValueError("MCP server script must be .py or .js file")
                
            # Set up server parameters
            server_params = StdioServerParameters(
                command=command,
                args=[self.blowing_off_server_script],
                env=None
            )
            
            # Create stdio transport
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.stdio, self.write = stdio_transport
            
            # Create session
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.stdio, self.write)
            )
            
            # Initialize session
            await self.session.initialize()
            
            # Get available tools
            response = await self.session.list_tools()
            self.mcp_tools = response.tools
            
            logger.info(f"Connected to blowing-off server with tools: {[tool.name for tool in self.mcp_tools]}")
            
        except Exception as e:
            logger.error(f"Failed to initialize blowing-off MCP client: {e}")
            raise
    
    def _format_system_prompt(self) -> str:
        """Create system prompt that explains the available house knowledge graph tools."""
        tools_description = "\n".join([
            f"- {tool.name}: {tool.description}" 
            for tool in self.mcp_tools
        ])
        
        return f"""You are a helpful AI assistant with access to a house knowledge graph through the blowing-off MCP client. You have access to the following tools:

{tools_description}

You can use these tools to answer questions about houses, properties, neighborhoods, and related real estate data from the test dataset. The data comes from the funkygibbon server with sample house information.

When a user asks a question that might benefit from the knowledge graph, use the appropriate tool to fetch relevant information. Be conversational and helpful. If you use a tool, explain what you found in a natural, easy-to-understand way.

Always respond in a friendly, conversational manner and provide useful insights based on the house data available."""

    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call an MCP tool with given arguments."""
        try:
            response = await self.session.call_tool(tool_name, arguments)
            return response.content[0].text if response.content else {}
        except Exception as e:
            logger.error(f"Error calling MCP tool {tool_name}: {e}")
            return {"error": str(e)}
    
    def _parse_tool_calls(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response.
        This is a simple implementation - you might want to use a more sophisticated
        approach like function calling or structured output.
        """
        tool_calls = []
        
        # Look for tool call patterns in the response
        # Format: TOOL: tool_name(arg1=value1, arg2=value2)
        import re
        
        pattern = r'TOOL:\s*(\w+)\s*\((.*?)\)'
        matches = re.findall(pattern, response_text, re.IGNORECASE)
        
        for tool_name, args_str in matches:
            if tool_name in [tool.name for tool in self.mcp_tools]:
                # Parse arguments (simplified - assumes key=value format)
                arguments = {}
                if args_str.strip():
                    for arg_pair in args_str.split(','):
                        if '=' in arg_pair:
                            key, value = arg_pair.split('=', 1)
                            arguments[key.strip()] = value.strip().strip('"\'')
                
                tool_calls.append({
                    'name': tool_name,
                    'arguments': arguments
                })
        
        return tool_calls
    
    async def _generate_response(self, user_input: str) -> str:
        """Generate a response using the LLM, potentially calling MCP tools."""
        
        # Build conversation context
        system_prompt = self._format_system_prompt()
        
        # Format conversation history
        context = f"System: {system_prompt}\n\n"
        for msg in self.conversation_history[-5:]:  # Keep last 5 messages
            context += f"{msg['role']}: {msg['content']}\n"
        context += f"Human: {user_input}\nAssistant:"
        
        # Generate initial response
        response = self.llm(
            context,
            max_tokens=self.llm_config['max_tokens'],
            temperature=self.llm_config['temperature'],
            top_p=self.llm_config['top_p'],
            repeat_penalty=self.llm_config['repeat_penalty'],
            stop=["Human:", "System:"]
        )
        
        response_text = response['choices'][0]['text'].strip()
        
        # Check for tool calls
        tool_calls = self._parse_tool_calls(response_text)
        
        if tool_calls:
            # Execute tool calls and incorporate results
            for tool_call in tool_calls:
                tool_result = await self._call_mcp_tool(
                    tool_call['name'], 
                    tool_call['arguments']
                )
                
                # Generate follow-up response with tool results
                tool_context = f"{context}\n{response_text}\n\nTool Result: {json.dumps(tool_result, indent=2)}\nAssistant:"
                
                follow_up_response = self.llm(
                    tool_context,
                    max_tokens=self.llm_config['max_tokens'],
                    temperature=self.llm_config['temperature'],
                    stop=["Human:", "System:"]
                )
                
                response_text = follow_up_response['choices'][0]['text'].strip()
        
        return response_text
    
    async def chat_loop(self):
        """Main chat loop for interacting with the user about house data."""
        print("🏠 House Knowledge Graph Chat")
        print("=" * 35)
        print("Connected to blowing-off MCP client with funkygibbon test data")
        print("Ask questions about houses, properties, and neighborhoods!")
        print("Type 'quit', 'exit', or 'bye' to end the conversation.\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                    print("Goodbye! Thanks for exploring the house data! 👋")
                    break
                    
                if not user_input:
                    continue
                
                print("Assistant: ", end="", flush=True)
                
                # Generate response
                response = await self._generate_response(user_input)
                print(response)
                
                # Update conversation history
                self.conversation_history.extend([
                    {"role": "Human", "content": user_input},
                    {"role": "Assistant", "content": response}
                ])
                
                print()  # Empty line for readability
                
            except KeyboardInterrupt:
                print("\n\nGoodbye! Thanks for exploring the house data! 👋")
                break
            except Exception as e:
                logger.error(f"Error during chat: {e}")
                print(f"Sorry, I encountered an error: {e}")
    
    async def cleanup(self):
        """Clean up resources."""
        if self.exit_stack:
            await self.exit_stack.aclose()


async def main():
    """Main function to run the house chat application."""
    if len(sys.argv) < 3:
        print("Usage: python chat_app.py <path_to_gguf_model> <path_to_blowing_off_server>")
        print("\nExample:")
        print("python chat_app.py ./models/mistral-7b-instruct.Q4_K_M.gguf ../blowing-off/server.py")
        print("\nThis assumes you're running from the-goodies/chat/ directory")
        sys.exit(1)
    
    model_path = sys.argv[1]
    blowing_off_server = sys.argv[2]
    
    # Validate paths
    if not os.path.exists(model_path):
        print(f"Error: Model file not found: {model_path}")
        print("Make sure you've downloaded a GGUF model file to the models/ directory")
        sys.exit(1)
        
    if not os.path.exists(blowing_off_server):
        print(f"Error: Blowing-off server file not found: {blowing_off_server}")
        print("Expected path like: ../blowing-off/server.py")
        sys.exit(1)
    
    # Create and run the application
    app = LocalLLMWithMCP(model_path, blowing_off_server)
    
    try:
        print("🚀 Initializing House Knowledge Graph Chat...")
        await app.initialize()
        await app.chat_loop()
    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        await app.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
