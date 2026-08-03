"""
Test disconnected mode functionality.

Verifies that the client can detect when the server is unavailable
and operate in offline mode.
"""

import pytest
import pytest_asyncio
import asyncio
import sys
import os
from unittest.mock import patch, AsyncMock

from blowingoff import BlowingOffClient
from inbetweenies.models import Entity, EntityType, SourceType


@pytest.mark.integration

async def _wait_for(condition, description, *, timeout=20.0, poll=0.05):
    """Wait until `condition()` holds, or fail with what was being waited for.

    Timing-based assertions in this file were `asyncio.sleep(n)` followed by an
    assert, which fails on a slow runner for reasons that have nothing to do
    with the behaviour under test. The timeout is deliberately generous: it is
    a failure bound, not an expected wait, and the poll returns as soon as the
    condition is true.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if condition():
            return
        await asyncio.sleep(poll)
    raise AssertionError(f"timed out after {timeout:.0f}s waiting for {description}")


class TestDisconnectedMode:
    """Test disconnected mode operations."""

    @pytest.mark.asyncio
    async def test_server_connectivity_check(self, server_url, auth_token, private_db_path):
        """Test that client can detect server availability."""
        db_path = private_db_path()

        client = BlowingOffClient(db_path)
        await client.connect(server_url, auth_token, "test-connectivity")

        # Check connectivity when server is up
        is_connected = await client.check_server_connectivity()
        assert is_connected is True

        # Test with invalid server URL
        client.sync_engine.base_url = "http://localhost:9999"  # Non-existent server
        is_connected = await client.check_server_connectivity()
        assert is_connected is False

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_offline_mode_detection(self, auth_token, private_db_path):
        """Test that client detects and reports offline mode."""
        db_path = private_db_path()

        client = BlowingOffClient(db_path)
        # Connect to non-existent server
        await client.connect("http://localhost:9999", auth_token, "test-offline")

        # Initially should not be offline (not checked yet)
        assert client.is_offline is False

        # Try to sync - should detect offline mode
        result = await client.sync()
        assert result.success is False
        assert len(result.errors) > 0
        assert "disconnected mode" in result.errors[0].lower()
        assert client.is_offline is True

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_offline_to_online_transition(self, server_url, auth_token, private_db_path):
        """Test transition from offline to online mode."""
        db_path = private_db_path()

        client = BlowingOffClient(db_path)
        await client.connect(server_url, auth_token, "test-transition")

        # Start with invalid server to simulate offline
        original_url = client.sync_engine.base_url
        client.sync_engine.base_url = "http://localhost:9999"

        # Should be offline
        result = await client.sync()
        assert client.is_offline is True
        assert result.success is False

        # Restore valid server URL
        client.sync_engine.base_url = original_url

        # Should come back online
        result = await client.sync()
        assert client.is_offline is False
        assert result.success is True

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_local_operations_while_offline(self, auth_token, private_db_path):
        """Test that local operations work while offline."""
        db_path = private_db_path()

        client = BlowingOffClient(db_path)
        # Connect to non-existent server
        await client.connect("http://localhost:9999", auth_token, "test-local-ops")

        # Verify offline mode
        result = await client.sync()
        assert client.is_offline is True

        # Create entity locally
        entity = Entity(
            entity_type=EntityType.DEVICE,
            name="Offline Device",
            content={"status": "created_offline"},
            source_type=SourceType.MANUAL,
            user_id="test-user"
        )

        # Store should work offline
        stored = await client.graph_operations.store_entity(entity)
        assert stored is not None
        assert stored.name == "Offline Device"

        # Retrieve should work offline
        retrieved = await client.graph_operations.get_entity(stored.id)
        assert retrieved is not None
        assert retrieved.name == "Offline Device"

        # MCP tools should work offline
        tools = client.get_available_mcp_tools()
        assert len(tools) > 0

        await client.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32" and os.environ.get('CI') == 'true',
                        reason="Windows CI has SQLite file locking issues - see issue #7")
    async def test_background_sync_with_offline_handling(self, server_url, auth_token, private_db_path):
        """Test background sync handles offline mode gracefully."""
        db_path = private_db_path()

        client = BlowingOffClient(db_path)
        await client.connect(server_url, auth_token, "test-background")

        # Track sync events
        sync_events = []
        async def observer(event, data):
            sync_events.append((event, data.success if hasattr(data, 'success') else None))

        client.add_observer(observer)

        # Start background sync with short interval
        await client.start_background_sync(interval=1)

        # Poll rather than sleep(2). The background task sleeps `interval`
        # BEFORE its first sync, so a fixed 2s wait leaves barely one interval
        # of slack -- and a loaded CI runner spends it. This failed on exactly
        # one of eight matrix legs, which is the signature of a wall-clock race
        # rather than a defect. Waiting on the CONDITION is both faster in the
        # normal case and immune to how busy the machine is.
        await _wait_for(
            lambda: any(event == "sync_complete" and success
                        for event, success in sync_events),
            "a successful background sync",
        )

        # Simulate offline by changing URL
        client.sync_engine.base_url = "http://localhost:9999"
        sync_events.clear()

        await _wait_for(
            lambda: any(event == "sync_disconnected" for event, _ in sync_events),
            "a sync_disconnected event after going offline",
        )

        await client.disconnect()
