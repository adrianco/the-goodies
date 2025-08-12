"""
Unit tests for CLI commands.

Tests the command-line interface functionality.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from click.testing import CliRunner
from datetime import datetime

from blowingoff.cli.main import cli


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_client():
    """Create a mock BlowingOffClient."""
    client = AsyncMock()
    client.is_connected = False
    client.graph_storage = Mock()
    client.graph_storage.get_statistics = Mock(return_value={
        'total_entities': 10,
        'total_relationships': 5,
        'average_degree': 2.5,
        'isolated_entities': 2,
        'entity_types': {'device': 5, 'room': 3, 'home': 2},
        'relationship_types': {'located_in': 3, 'part_of': 2}
    })
    client.get_available_mcp_tools = Mock(return_value=[
        'search_entities', 'create_entity', 'get_devices_in_room'
    ])
    client.execute_mcp_tool = AsyncMock(return_value={
        'success': True,
        'result': {'test': 'result'}
    })
    client.get_sync_status = AsyncMock(return_value={
        'last_sync': '2024-01-01T12:00:00',
        'total_syncs': 5,
        'sync_failures': 0,
        'sync_in_progress': False
    })
    return client


@pytest.fixture
def config_file():
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config = {
            'server_url': 'http://localhost:8000',
            'client_id': 'test-client',
            'auth_token': 'test-token'
        }
        json.dump(config, f)
        return Path(f.name)


class TestCLICommands:
    """Test CLI commands."""
    
    def test_cli_help(self, runner):
        """Test CLI help output."""
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'Blowing-off client CLI' in result.output
    
    @patch('blowingoff.cli.main.BlowingOffClient')
    def test_connect_command(self, mock_client_class, runner, config_file):
        """Test connect command."""
        mock_instance = mock_client_class.return_value
        mock_instance.connect = AsyncMock(return_value=True)
        
        result = runner.invoke(cli, [
            'connect',
            '--server-url', 'http://localhost:8000',
            '--auth-token', 'test-token',
            '--client-id', 'test-client'
        ])
        
        assert result.exit_code == 0
        assert 'Connected successfully' in result.output
    
    @patch('blowingoff.cli.main.BlowingOffClient')
    def test_disconnect_command(self, mock_client_class, runner, config_file):
        """Test disconnect command."""
        mock_instance = mock_client_class.return_value
        mock_instance.is_connected = True
        mock_instance.disconnect = AsyncMock()
        
        # Create config file
        config_path = Path.home() / '.blowing-off' / 'config.json'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump({'server_url': 'http://localhost:8000'}, f)
        
        result = runner.invoke(cli, ['disconnect'])
        
        assert result.exit_code == 0
        assert 'Disconnected' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_status_command(self, mock_load_client, runner, mock_client):
        """Test status command."""
        mock_load_client.return_value = mock_client
        mock_client.is_connected = True
        
        result = runner.invoke(cli, ['status'])
        
        assert result.exit_code == 0
        assert 'Connection Status' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_sync_command(self, mock_load_client, runner, mock_client):
        """Test sync command."""
        mock_load_client.return_value = mock_client
        mock_client.sync = AsyncMock(return_value={
            'success': True,
            'entities_synced': 10,
            'relationships_synced': 5,
            'conflicts': []
        })
        
        result = runner.invoke(cli, ['sync'])
        
        assert result.exit_code == 0
        assert 'Sync completed' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_tools_command(self, mock_load_client, runner, mock_client):
        """Test tools command."""
        mock_load_client.return_value = mock_client
        
        result = runner.invoke(cli, ['tools'])
        
        assert result.exit_code == 0
        # Check for tool names in output
        assert 'search_entities' in result.output or 'MCP' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_execute_command(self, mock_load_client, runner, mock_client):
        """Test execute command."""
        mock_load_client.return_value = mock_client
        
        result = runner.invoke(cli, [
            'execute',
            'search_entities',
            '-a', 'query=test',
            '-a', 'limit=5'
        ])
        
        assert result.exit_code == 0
        assert 'Result:' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_execute_with_json_args(self, mock_load_client, runner, mock_client):
        """Test execute command with JSON arguments."""
        mock_load_client.return_value = mock_client
        
        result = runner.invoke(cli, [
            'execute',
            'search_entities',
            '--json-args', '{"query": "test", "limit": 5}'
        ])
        
        assert result.exit_code == 0
        assert 'Result:' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_search_command(self, mock_load_client, runner, mock_client):
        """Test search command."""
        mock_load_client.return_value = mock_client
        mock_client.execute_mcp_tool = AsyncMock(return_value={
            'success': True,
            'result': {
                'results': [
                    {
                        'entity': {
                            'id': 'test-id',
                            'name': 'Test Device',
                            'entity_type': 'device'
                        },
                        'score': 1.5
                    }
                ],
                'count': 1
            }
        })
        
        result = runner.invoke(cli, ['search', 'test'])
        
        assert result.exit_code == 0
        assert 'Search Results' in result.output or 'Test Device' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_create_command(self, mock_load_client, runner, mock_client):
        """Test create command."""
        mock_load_client.return_value = mock_client
        mock_client.execute_mcp_tool = AsyncMock(return_value={
            'success': True,
            'result': {
                'entity': {
                    'id': 'new-id',
                    'name': 'New Device',
                    'entity_type': 'device'
                }
            }
        })
        
        result = runner.invoke(cli, [
            'create',
            'device',
            'New Device',
            '-c', '{"test": true}'
        ])
        
        assert result.exit_code == 0
        assert 'Created' in result.output or 'new-id' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_stats_command(self, mock_load_client, runner, mock_client):
        """Test stats command."""
        mock_load_client.return_value = mock_client
        
        result = runner.invoke(cli, ['stats'])
        
        assert result.exit_code == 0
        assert 'Local Graph Statistics' in result.output
        assert 'Total Entities: 10' in result.output
        assert 'Total Relationships: 5' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_demo_command(self, mock_load_client, runner, mock_client):
        """Test demo command."""
        mock_load_client.return_value = mock_client
        mock_client.demo_mcp_functionality = AsyncMock()
        
        result = runner.invoke(cli, ['demo'])
        
        assert result.exit_code == 0
        assert 'MCP Demo' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_list_entities_command(self, mock_load_client, runner, mock_client):
        """Test list-entities command."""
        mock_load_client.return_value = mock_client
        mock_client.execute_mcp_tool = AsyncMock(return_value={
            'success': True,
            'result': {
                'results': [
                    {
                        'entity': {
                            'id': 'test-id',
                            'name': 'Test Device',
                            'entity_type': 'device'
                        },
                        'score': 1.0
                    }
                ],
                'count': 1
            }
        })
        
        result = runner.invoke(cli, ['list-entities'])
        
        assert result.exit_code == 0
        # Should show entities or indicate they exist
        assert 'Entities' in result.output or 'Test Device' in result.output


class TestCLIErrorHandling:
    """Test CLI error handling."""
    
    @patch('blowingoff.cli.main.BlowingOffClient')
    def test_connect_failure(self, mock_client_class, runner):
        """Test handling connection failure."""
        mock_instance = mock_client_class.return_value
        mock_instance.connect = AsyncMock(side_effect=Exception("Connection failed"))
        
        result = runner.invoke(cli, [
            'connect',
            '--server-url', 'http://localhost:8000',
            '--auth-token', 'test-token',
            '--client-id', 'test-client'
        ])
        
        assert result.exit_code != 0
        assert 'Error' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_execute_invalid_args(self, mock_load_client, runner, mock_client):
        """Test execute with invalid arguments."""
        mock_load_client.return_value = mock_client
        
        result = runner.invoke(cli, [
            'execute',
            'search_entities',
            '-a', 'invalid_format'  # Missing = sign
        ])
        
        assert result.exit_code != 0
        assert 'Invalid argument format' in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_execute_invalid_json(self, mock_load_client, runner, mock_client):
        """Test execute with invalid JSON."""
        mock_load_client.return_value = mock_client
        
        result = runner.invoke(cli, [
            'execute',
            'search_entities',
            '--json-args', 'not valid json'
        ])
        
        assert result.exit_code != 0
        assert 'Invalid JSON' in result.output
    
    def test_no_config_file(self, runner):
        """Test commands when no config file exists."""
        # Remove any existing config
        config_path = Path.home() / '.blowing-off' / 'config.json'
        if config_path.exists():
            config_path.unlink()
        
        result = runner.invoke(cli, ['status'])
        
        assert 'Not connected' in result.output or 'Error' in result.output


class TestCLIIntegration:
    """Test CLI integration scenarios."""
    
    @patch('blowingoff.cli.main.BlowingOffClient')
    def test_full_workflow(self, mock_client_class, runner):
        """Test a complete CLI workflow."""
        mock_instance = mock_client_class.return_value
        mock_instance.connect = AsyncMock(return_value=True)
        mock_instance.is_connected = True
        mock_instance.sync = AsyncMock(return_value={
            'success': True,
            'entities_synced': 5,
            'relationships_synced': 3,
            'conflicts': []
        })
        mock_instance.execute_mcp_tool = AsyncMock(return_value={
            'success': True,
            'result': {'test': 'data'}
        })
        mock_instance.disconnect = AsyncMock()
        
        # Connect
        result = runner.invoke(cli, [
            'connect',
            '--server-url', 'http://localhost:8000',
            '--auth-token', 'test-token',
            '--client-id', 'test-client'
        ])
        assert result.exit_code == 0
        
        # Sync
        result = runner.invoke(cli, ['sync'])
        assert result.exit_code == 0
        
        # Execute tool
        result = runner.invoke(cli, [
            'execute',
            'search_entities',
            '-a', 'query=test'
        ])
        assert result.exit_code == 0
        
        # Disconnect
        result = runner.invoke(cli, ['disconnect'])
        assert result.exit_code == 0