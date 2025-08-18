"""
Shared test fixture for starting a real FunkyGibbon server.

This fixture can be used by both FunkyGibbon and Blowing-Off tests.
"""

import pytest
import pytest_asyncio
import asyncio
import subprocess
import sys
import os
import httpx
from pathlib import Path


@pytest_asyncio.fixture(scope="session")
async def running_server():
    """Start a real FunkyGibbon server for testing."""
    # Get the path to the funkygibbon directory
    funkygibbon_path = Path(__file__).parent.parent

    # Set up environment - add parent to PYTHONPATH so the module can be found
    env = os.environ.copy()
    parent_path = funkygibbon_path.parent
    env["PYTHONPATH"] = f"{parent_path}:{env.get('PYTHONPATH', '')}"

    # Start the server using the module approach
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
    server_url = "http://localhost:8000"

    for i in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{server_url}/health")
                if response.status_code == 200:
                    print(f"\n✅ FunkyGibbon server started successfully on {server_url}")
                    break
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if i == max_retries - 1:
                # Get server output for debugging
                try:
                    stdout, stderr = process.communicate(timeout=1)
                    print(f"\n❌ Server failed to start. Stdout: {stdout}")
                    print(f"Stderr: {stderr}")
                except subprocess.TimeoutExpired:
                    pass
                process.terminate()
                pytest.fail("FunkyGibbon server failed to start")
            await asyncio.sleep(0.5)

    yield server_url

    # Stop the server
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    print("\n✅ FunkyGibbon server stopped")
