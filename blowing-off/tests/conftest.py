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

# Register pytest markers
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )

# Add FunkyGibbon to path
funkygibbon_path = Path(__file__).parent.parent.parent / "funkygibbon"
sys.path.insert(0, str(funkygibbon_path))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    # Fix for Windows Python 3.8+ to avoid "Event loop is closed" errors
    if sys.platform.startswith("win") and sys.version_info[:2] >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def funkygibbon_server():
    """Start FunkyGibbon server for testing."""
    import tempfile
    import os
    
    # Create a temporary database for testing
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db_path = f.name
    
    print(f"DEBUG: Test database path: {test_db_path}")
    
    # Start the server process using the module approach
    env = os.environ.copy()
    parent_path = funkygibbon_path.parent
    # Use the correct path separator for the platform
    path_sep = os.pathsep  # ; on Windows, : on Unix
    env["PYTHONPATH"] = f"{parent_path}{path_sep}{env.get('PYTHONPATH', '')}"
    # Ensure proper path format for Windows
    db_url_path = test_db_path.replace('\\', '/')
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_url_path}"
    
    print(f"DEBUG: Setting DATABASE_URL={env['DATABASE_URL']}")
    
    process = subprocess.Popen(
        [sys.executable, "-m", "funkygibbon"],
        cwd=str(parent_path),  # Run from parent directory
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,  # Keep separate to see errors
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
    
    # Run populate_graph_db.py to add test data
    populate_result = subprocess.run(
        [sys.executable, str(funkygibbon_path / "populate_graph_db.py")],
        cwd=str(parent_path),
        env=env,
        capture_output=True,
        text=True
    )
    if populate_result.returncode == 0:
        print("✅ Test database populated")
    else:
        print(f"⚠️ Failed to populate database: {populate_result.stderr}")
    
    yield "http://localhost:8000"
    
    # Stop the server and capture output
    process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=5)
        # Always print server output for debugging
        print("\n📋 Server stdout:")
        if stdout:
            print(stdout[-2000:])  # Last 2000 chars
        print("\n📋 Server stderr:")
        if stderr:
            print(stderr[-2000:])  # Last 2000 chars
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    print("\n✅ FunkyGibbon server stopped")
    
    # Cleanup test database
    try:
        os.unlink(test_db_path)
        # Also remove WAL and SHM files if they exist
        for suffix in ["-wal", "-shm"]:
            wal_path = test_db_path + suffix
            if os.path.exists(wal_path):
                os.unlink(wal_path)
    except Exception as e:
        print(f"Warning: Could not cleanup test database: {e}")


@pytest.fixture(scope="session")
def server_url(funkygibbon_server):
    """Get the server URL."""
    return funkygibbon_server


@pytest.fixture(scope="session")
def auth_token():
    """Get test auth token."""
    return "test-token-12345"