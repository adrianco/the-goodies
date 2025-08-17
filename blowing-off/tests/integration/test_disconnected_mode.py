"""
Test disconnected mode functionality.

Verifies that the client can detect when the server is unavailable
and operate in offline mode.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock

from blowingoff import BlowingOffClient
from inbetweenies.models import Entity, EntityType, SourceType


@pytest.mark.integration
class TestDisconnectedMode:
    """Test disconnected mode operations."""
    
    @pytest.mark.asyncio
    async def test_server_connectivity_check(self, server_url, auth_token):
        """Test that client can detect server availability."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
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
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_offline_mode_detection(self, auth_token):
        """Test that client detects and reports offline mode."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
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
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_offline_to_online_transition(self, server_url, auth_token):
        """Test transition from offline to online mode."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
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
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_local_operations_while_offline(self, auth_token):
        """Test that local operations work while offline."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
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
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_background_sync_with_offline_handling(self, server_url, auth_token):
        """Test background sync handles offline mode gracefully."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            client = BlowingOffClient(db_path)
            await client.connect(server_url, auth_token, "test-background")
            
            # Track sync events
            sync_events = []
            async def observer(event, data):
                sync_events.append((event, data.success if hasattr(data, 'success') else None))
            
            client.add_observer(observer)
            
            # Start background sync with short interval
            await client.start_background_sync(interval=1)
            
            # Wait for initial sync (background sync sleeps first, then syncs)
            await asyncio.sleep(2)
            
            # Should have successful sync
            assert len(sync_events) > 0
            assert any(event == "sync_complete" and success for event, success in sync_events)
            
            # Simulate offline by changing URL
            client.sync_engine.base_url = "http://localhost:9999"
            sync_events.clear()
            
            # Wait for offline sync attempt
            await asyncio.sleep(2)
            
            # Should have disconnected event
            assert any(event == "sync_disconnected" for event, _ in sync_events)
            
            await client.disconnect()
        finally:
            Path(db_path).unlink(missing_ok=True)