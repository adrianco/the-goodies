"""
Integration tests for BlowingOffClient.

Tests the complete client functionality including connection, sync, and MCP tools.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import json
from datetime import datetime, UTC
import uuid

from blowingoff.client import BlowingOffClient
from inbetweenies.models import Entity, EntityType


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def config_file(temp_dir):
    """Create a test config file."""
    config_path = Path(temp_dir) / "config.json"
    config = {
        "server_url": "http://localhost:8000",
        "client_id": "test-client",
        "auth_token": "test-token"
    }
    with open(config_path, 'w') as f:
        json.dump(config, f)
    return config_path


@pytest.fixture
async def client(temp_dir, config_file):
    """Create a BlowingOffClient instance."""
    client = BlowingOffClient(config_file=str(config_file))
    yield client
    await client.disconnect()


class TestBlowingOffClient:
    """Test BlowingOffClient functionality."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, client):
        """Test client initialization."""
        assert client.config_file is not None
        assert client.graph_storage is not None
        assert client.graph_ops is not None
        assert client.mcp_client is not None
    
    @pytest.mark.asyncio
    async def test_connect_disconnect(self, client):
        """Test connecting and disconnecting."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=AsyncMock(return_value={"status": "healthy"})
            )
            
            # Connect
            result = await client.connect(
                server_url="http://localhost:8000",
                auth_token="test-token",
                client_id="test-client"
            )
            assert result is True
            assert client.is_connected is True
            
            # Disconnect
            await client.disconnect()
            assert client.is_connected is False
    
    @pytest.mark.asyncio
    async def test_execute_mcp_tool(self, client):
        """Test executing MCP tools."""
        # Create test entity
        result = await client.execute_mcp_tool(
            "create_entity",
            entity_type="device",
            name="Test Device",
            content={"test": True},
            user_id="test"
        )
        
        assert result['success'] is True
        assert result['result']['entity']['name'] == "Test Device"
        
        # Search for entity
        result = await client.execute_mcp_tool(
            "search_entities",
            query="Test",
            limit=5
        )
        
        assert result['success'] is True
        assert result['result']['count'] >= 1
    
    @pytest.mark.asyncio
    async def test_get_sync_status(self, client):
        """Test getting sync status."""
        status = await client.get_sync_status()
        
        assert isinstance(status, dict)
        assert 'last_sync' in status
        assert 'total_syncs' in status
        assert 'sync_failures' in status
    
    @pytest.mark.asyncio
    async def test_demo_mcp_functionality(self, client):
        """Test demo MCP functionality."""
        # Run demo
        with patch('builtins.print'):  # Suppress print output
            await client.demo_mcp_functionality()
        
        # Verify entities were created
        result = await client.execute_mcp_tool(
            "search_entities",
            query="Smart",
            limit=10
        )
        
        assert result['success'] is True
        assert result['result']['count'] > 0
    
    @pytest.mark.asyncio
    async def test_clear_graph_data(self, client):
        """Test clearing graph data."""
        # Create an entity
        await client.execute_mcp_tool(
            "create_entity",
            entity_type="device",
            name="Test Device",
            content={},
            user_id="test"
        )
        
        # Clear data
        client.clear_graph_data()
        
        # Verify data is cleared
        result = await client.execute_mcp_tool(
            "search_entities",
            query="Test",
            limit=10
        )
        
        assert result['result']['count'] == 0
    
    @pytest.mark.asyncio
    async def test_permission_checks(self, client):
        """Test permission checking methods."""
        # Without auth manager
        assert client.check_write_permission() is False
        assert client.check_admin_permission() is False
        
        # With mock auth manager
        client.auth_manager = Mock()
        client.auth_manager.has_permission = Mock(return_value=True)
        client.auth_manager.role = 'admin'
        
        assert client.check_write_permission() is True
        assert client.check_admin_permission() is True


class TestClientSync:
    """Test client synchronization functionality."""
    
    @pytest.mark.asyncio
    async def test_sync_with_server(self, client):
        """Test syncing with server."""
        # Mock server response
        mock_entities = [
            {
                "id": str(uuid.uuid4()),
                "version": f"{datetime.now(UTC).isoformat()}Z-server",
                "entity_type": "device",
                "name": "Server Device",
                "content": {"from": "server"},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "created_by": "server",
                "updated_by": "server"
            }
        ]
        mock_relationships = []
        
        with patch.object(client.sync_engine, 'sync') as mock_sync:
            mock_sync.return_value = AsyncMock(
                success=True,
                entities_synced=len(mock_entities),
                relationships_synced=0,
                conflicts=[]
            )
            
            with patch.object(client.mcp_client, 'sync_with_server') as mock_mcp_sync:
                # Mock the sync
                await client.sync()
                
                # Verify sync was called
                mock_sync.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_sync_daemon(self, client):
        """Test sync daemon functionality."""
        with patch.object(client, 'sync') as mock_sync:
            mock_sync.return_value = AsyncMock()
            
            # Start daemon
            await client.start_sync_daemon(interval=0.1)
            assert client._sync_daemon_task is not None
            
            # Let it run briefly
            import asyncio
            await asyncio.sleep(0.2)
            
            # Stop daemon
            await client.stop_sync_daemon()
            assert client._sync_daemon_task is None
            
            # Verify sync was called at least once
            assert mock_sync.call_count >= 1


class TestMCPClientIntegration:
    """Test MCP client integration."""
    
    @pytest.mark.asyncio
    async def test_full_mcp_workflow(self, client):
        """Test a complete MCP workflow."""
        # Create a home
        home_result = await client.execute_mcp_tool(
            "create_entity",
            entity_type="home",
            name="Test Home",
            content={"address": "123 Test St"},
            user_id="test"
        )
        assert home_result['success'] is True
        home_id = home_result['result']['entity']['id']
        
        # Create a room
        room_result = await client.execute_mcp_tool(
            "create_entity",
            entity_type="room",
            name="Living Room",
            content={"area": 30},
            user_id="test"
        )
        assert room_result['success'] is True
        room_id = room_result['result']['entity']['id']
        
        # Create relationship (room part of home)
        rel_result = await client.execute_mcp_tool(
            "create_relationship",
            from_entity_id=room_id,
            to_entity_id=home_id,
            relationship_type="part_of",
            user_id="test"
        )
        assert rel_result['success'] is True
        
        # Create a device
        device_result = await client.execute_mcp_tool(
            "create_entity",
            entity_type="device",
            name="Smart TV",
            content={"manufacturer": "Samsung"},
            user_id="test"
        )
        assert device_result['success'] is True
        device_id = device_result['result']['entity']['id']
        
        # Place device in room
        loc_result = await client.execute_mcp_tool(
            "create_relationship",
            from_entity_id=device_id,
            to_entity_id=room_id,
            relationship_type="located_in",
            user_id="test"
        )
        assert loc_result['success'] is True
        
        # Get devices in room
        devices_result = await client.execute_mcp_tool(
            "get_devices_in_room",
            room_id=room_id
        )
        assert devices_result['success'] is True
        assert devices_result['result']['count'] == 1
        assert devices_result['result']['devices'][0]['id'] == device_id
        
        # Find path from device to home
        path_result = await client.execute_mcp_tool(
            "find_path",
            from_entity_id=device_id,
            to_entity_id=home_id
        )
        assert path_result['success'] is True
        assert path_result['result']['found'] is True
        assert len(path_result['result']['path']) == 3  # device -> room -> home
        
        # Update device
        update_result = await client.execute_mcp_tool(
            "update_entity",
            entity_id=device_id,
            changes={"name": "65 inch Smart TV"},
            user_id="test"
        )
        assert update_result['success'] is True
        assert update_result['result']['entity']['name'] == "65 inch Smart TV"
        
        # Get entity details
        details_result = await client.execute_mcp_tool(
            "get_entity_details",
            entity_id=device_id
        )
        assert details_result['success'] is True
        assert details_result['result']['entity']['name'] == "65 inch Smart TV"
        assert details_result['result']['outgoing_relationships'] == 1  # located_in
    
    @pytest.mark.asyncio
    async def test_error_handling(self, client):
        """Test error handling in MCP tools."""
        # Try to get non-existent entity
        result = await client.execute_mcp_tool(
            "get_entity_details",
            entity_id="non-existent-id"
        )
        assert result['success'] is False
        assert "not found" in result['error'].lower()
        
        # Try to get devices in non-existent room
        result = await client.execute_mcp_tool(
            "get_devices_in_room",
            room_id="non-existent-room"
        )
        assert result['success'] is False
        assert "not found" in result['error'].lower()
        
        # Try invalid entity type
        result = await client.execute_mcp_tool(
            "create_entity",
            entity_type="invalid_type",
            name="Test",
            user_id="test"
        )
        assert result['success'] is False