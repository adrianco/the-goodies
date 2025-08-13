"""
Test that the FunkyGibbon server can start properly.

This test actually starts the server in a subprocess to ensure
all imports and configurations work correctly.
"""

import pytest
import asyncio
import httpx
import sys
from pathlib import Path

# Import the server fixture
sys.path.append(str(Path(__file__).parent.parent))
from conftest_server import running_server


class TestServerStartup:
    """Test server startup and basic functionality."""
    
    @pytest.mark.asyncio
    async def test_server_starts_and_responds(self, running_server):
        """Test that the server can start and respond to health checks."""
        # Test that we can make API calls
        async with httpx.AsyncClient(base_url=running_server) as client:
            # Test health endpoint
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}
            
            # Test graph API endpoint
            response = await client.get("/api/v1/graph/entities")
            assert response.status_code == 200
            data = response.json()
            assert "entities" in data
            assert isinstance(data["entities"], list)
    
    @pytest.mark.asyncio
    async def test_server_handles_multiple_requests(self, running_server):
        """Test that the server can handle multiple concurrent requests."""
        # Make multiple concurrent requests
        async with httpx.AsyncClient(base_url=running_server) as client:
            tasks = []
            for i in range(10):
                tasks.append(client.get("/health"))
            
            responses = await asyncio.gather(*tasks)
            
            # All requests should succeed
            for response in responses:
                assert response.status_code == 200