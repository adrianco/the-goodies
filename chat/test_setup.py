#!/usr/bin/env python3
"""
Setup Verification Script for House Knowledge Graph Chat
========================================================

This script helps verify that all components are properly configured
for the chat application in the-goodies/chat/ directory.

Usage: python test_setup.py <model_path> <blowing_off_server_path>
Example: python test_setup.py ./models/mistral-7b.gguf ../blowing-off/server.py
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path

def check_python_version():
    """Check Python version compatibility."""
    print("🐍 Checking Python version...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro} - OK")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro} - Need Python 3.8+")
        return False

def check_dependencies():
    """Check if required packages are installed."""
    print("\n📦 Checking Python dependencies...")
    
    required_packages = [
        ('mcp', 'Model Context Protocol'),
        ('llama_cpp', 'llama-cpp-python'),
        ('dotenv', 'python-dotenv'),
    ]
    
    all_good = True
    for package, description in required_packages:
        try:
            __import__(package)
            print(f"   ✅ {description} - OK")
        except ImportError:
            print(f"   ❌ {description} - Missing")
            all_good = False
    
    return all_good

def check_model_file(model_path):
    """Check if model file exists and is readable."""
    print(f"\n🤖 Checking model file: {model_path}")
    
    if not model_path:
        print("   ❌ No model path provided")
        return False
        
    path = Path(model_path)
    if not path.exists():
        print(f"   ❌ Model file not found: {model_path}")
        return False
        
    if not path.is_file():
        print(f"   ❌ Path is not a file: {model_path}")
        return False
        
    if not path.suffix.lower() == '.gguf':
        print(f"   ⚠️  File doesn't have .gguf extension: {path.suffix}")
        
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"   ✅ Model file found ({size_mb:.1f} MB) - OK")
    return True

def check_blowing_off_server(server_path):
    """Check if blowing-off server script exists and is executable."""
    print(f"\n🔧 Checking blowing-off server: {server_path}")
    
    if not server_path:
        print("   ❌ No server path provided")
        return False
        
    path = Path(server_path)
    if not path.exists():
        print(f"   ❌ Server file not found: {server_path}")
        print("   💡 Expected path like: ../blowing-off/server.py")
        return False
        
    if not path.is_file():
        print(f"   ❌ Path is not a file: {server_path}")
        return False
        
    if path.suffix.lower() not in ['.py', '.js']:
        print(f"   ❌ Server file must be .py or .js, got: {path.suffix}")
        return False
        
    print(f"   ✅ Blowing-off server found ({path.suffix} script) - OK")
    return True

async def test_llm_loading(model_path):
    """Test loading the LLM model."""
    print(f"\n🧠 Testing LLM model loading...")
    
    try:
        from llama_cpp import Llama
        
        print("   📋 Initializing model (this may take a moment)...")
        llm = Llama(
            model_path=model_path,
            n_ctx=512,      # Small context for testing
            n_threads=2,    # Limited threads for testing
            verbose=False   # Suppress verbose output
        )
        
        print("   🎯 Testing text generation...")
        response = llm(
            "Hello, this is a test. Please respond with 'Test successful'.",
            max_tokens=10,
            temperature=0.1,
            stop=[".", "\n"]
        )
        
        generated_text = response['choices'][0]['text'].strip()
        print(f"   💬 Generated: '{generated_text}'")
        print("   ✅ LLM model test - OK")
        return True
        
    except Exception as e:
        print(f"   ❌ LLM model test failed: {e}")
        return False

async def test_blowing_off_server(server_path):
    """Test blowing-off server connectivity and tool availability."""
    print(f"\n🌐 Testing blowing-off server connectivity...")
    
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from contextlib import AsyncExitStack
        
        # Determine command
        if server_path.endswith('.py'):
            command = "python"
        elif server_path.endswith('.js'):
            command = "node"
        else:
            print("   ❌ Unknown server type")
            return False
            
        print(f"   🔄 Starting blowing-off server: {command} {server_path}")
        
        # Test server startup
        async with AsyncExitStack() as stack:
            server_params = StdioServerParameters(
                command=command,
                args=[server_path],
                env=None
            )
            
            stdio_transport = await stack.enter_async_context(
                stdio_client(server_params)
            )
            stdio, write = stdio_transport
            
            session = await stack.enter_async_context(
                ClientSession(stdio, write)
            )
            
            await session.initialize()
            
            # List tools
            response = await session.list_tools()
            tools = response.tools
            
            print(f"   🛠️  Available tools: {[tool.name for tool in tools]}")
            print(f"   ✅ Blowing-off server test - OK ({len(tools)} tools)")
            
            if len(tools) == 0:
                print("   ⚠️  Warning: No tools found. Check if funkygibbon test data is loaded.")
            
            return True
            
    except Exception as e:
        print(f"   ❌ Blowing-off server test failed: {e}")
        print("   💡 Make sure the server connects to funkygibbon and loads test data")
        return False

def print_recommendations():
    """Print recommendations for common issues."""
    print("""
💡 Recommendations for the-goodies/chat/:

1. **Directory Structure:**
   ```
   the-goodies/
   ├── blowing-off/      # Your existing MCP client
   ├── chat/            # This application
   │   ├── models/      # Download GGUF models here
   │   └── venv/        # Virtual environment
   └── funkygibbon/     # Test data server
   ```

2. **Model Selection:**
   - For laptops: Use Mistral 7B Q4_K_M (~4GB) or Phi-3 Mini (~2GB)
   - For mobile/low-memory: Use TinyLlama (~600MB)
   - Download from Hugging Face GGUF repositories to ./models/

3. **Blowing-off Integration:**
   - Ensure your blowing-off server connects to funkygibbon
   - Verify test data is loaded and accessible via MCP tools
   - Check server script path is correct (e.g., ../blowing-off/server.py)

4. **GPU Acceleration:**
   - NVIDIA: Reinstall with `CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python --force-reinstall`
   - Apple Silicon: Use `CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python --force-reinstall`

5. **Memory Issues:**
   - Reduce context size (n_ctx) to 2048 or lower
   - Use smaller quantized models (Q4_K_M instead of Q8_0)
   - Close other applications

6. **Testing:**
   - Run from the-goodies/chat/ directory
   - Test blowing-off server independently first
   - Use test_setup.py to verify everything works
""")

def main():
    """Main verification function."""
    print("🔍 House Knowledge Graph Chat Setup Verification")
    print("=" * 50)
    
    # Get paths from command line or environment
    model_path = sys.argv[1] if len(sys.argv) > 1 else os.getenv('MODEL_PATH')
    blowing_off_server = sys.argv[2] if len(sys.argv) > 2 else os.getenv('BLOWING_OFF_SERVER')
    
    if not model_path or not blowing_off_server:
        print("Usage: python test_setup.py <model_path> <blowing_off_server_path>")
        print("\nExample: python test_setup.py ./models/mistral-7b.gguf ../blowing-off/server.py")
        print("Or set MODEL_PATH and BLOWING_OFF_SERVER environment variables")
        sys.exit(1)
    
    print(f"Model Path: {model_path}")
    print(f"Blowing-off Server: {blowing_off_server}")
    print(f"Current Directory: {os.getcwd()}")
    
    # Run checks
    checks = [
        check_python_version(),
        check_dependencies(),
        check_model_file(model_path),
        check_blowing_off_server(blowing_off_server)
    ]
    
    if all(checks):
        print("\n🧪 Running integration tests...")
        
        # Run async tests
        async def run_tests():
            test_results = []
            
            # Test LLM loading
            if check_model_file(model_path):
                test_results.append(await test_llm_loading(model_path))
            
            # Test blowing-off server
            if check_blowing_off_server(blowing_off_server):
                test_results.append(await test_blowing_off_server(blowing_off_server))
            
            return test_results
        
        test_results = asyncio.run(run_tests())
        
        if all(test_results):
            print("\n🎉 All tests passed! You're ready to run the chat application.")
            print(f"\nRun: python chat_app.py {model_path} {blowing_off_server}")
        else:
            print("\n⚠️  Some tests failed. Please check the issues above.")
            print_recommendations()
    else:
        print("\n❌ Setup verification failed. Please fix the issues above.")
        print_recommendations()

if __name__ == "__main__":
    main()
