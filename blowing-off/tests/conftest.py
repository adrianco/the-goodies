"""
Test configuration for Blowing-Off integration tests.

Provides fixtures for running FunkyGibbon server during tests.

REVISION HISTORY:
- 2025-07-28: Fixed server startup to use module approach (python -m funkygibbon)
"""

import pytest
import pytest_asyncio
import asyncio
import subprocess
import time
import httpx
import sys
from pathlib import Path

# Add FunkyGibbon to path
funkygibbon_path = Path(__file__).parent.parent.parent / "funkygibbon"
sys.path.insert(0, str(funkygibbon_path))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def funkygibbon_server():
    """Start FunkyGibbon server for testing."""
    # Start the server process using the module approach
    import os
    env = os.environ.copy()
    parent_path = funkygibbon_path.parent
    env["PYTHONPATH"] = f"{parent_path}:{env.get('PYTHONPATH', '')}"
    
    process = subprocess.Popen(
        [sys.executable, "-m", "funkygibbon"],
        cwd=str(parent_path),  # Run from parent directory
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    
    # Wait for server to start
    max_retries = 30
    for i in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8000/health")
                if response.status_code == 200:
                    print("\n✅ FunkyGibbon server started successfully")
                    break
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if i == max_retries - 1:
                # Get server output for debugging
                stdout, stderr = process.communicate(timeout=1)
                print(f"\n❌ Server failed to start. Stdout: {stdout}")
                print(f"Stderr: {stderr}")
                process.terminate()
                pytest.fail("FunkyGibbon server failed to start")
            await asyncio.sleep(0.5)
    
    yield "http://localhost:8000"
    
    # Stop the server
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    print("\n✅ FunkyGibbon server stopped")


@pytest.fixture(scope="session")
def server_url(funkygibbon_server):
    """Get the server URL."""
    return funkygibbon_server


@pytest.fixture(scope="session")
def auth_token():
    """Get test auth token."""
    return "test-token-12345"