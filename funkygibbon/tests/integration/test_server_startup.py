"""
Test that the FunkyGibbon server can start properly.

This test actually starts the server in a subprocess to ensure
all imports and configurations work correctly.

The server comes from the `running_server` fixture in the repo-root
conftest.py, which binds a freshly allocated ephemeral port and proves the
responder is its own subprocess. This module previously imported a local
fixture that hardcoded port 8000, so an unrelated server already listening
there would be tested instead of ours.
"""

import asyncio

import httpx
import pytest


class TestServerStartup:
    """Test server startup and basic functionality."""

    @pytest.mark.asyncio
    async def test_server_starts_and_responds(self, running_server, auth_token):
        """Test that the server can start and respond to health checks."""
        # Test that we can make API calls
        async with httpx.AsyncClient(base_url=running_server) as client:
            # Health endpoint is public
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}

            # Graph API sits behind require_auth, so this needs the session's
            # real admin token. Calling it unauthenticated (as this test used
            # to) just asserts on a 401 and proves nothing about the graph API.
            response = await client.get(
                "/api/v1/graph/entities",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
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
