"""
Test CLI commands to ensure they use correct method names.

These tests catch issues like using 'house' instead of 'home' or
'device' instead of 'accessory' in CLI commands.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import Mock, AsyncMock, patch
import json
from pathlib import Path

from blowingoff.cli.main import cli


class TestCLICommands:
    """Test CLI commands use correct API methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch('blowingoff.cli.main.load_client')
    @patch('pathlib.Path.read_text')
    def test_status_command(self, mock_read_text, mock_load_client):
        """Test 'status' command works correctly."""
        # Mock config file
        mock_read_text.return_value = json.dumps({
            "server_url": "http://localhost:8000",
            "client_id": "test-client",
            "db_path": "test.db"
        })

        # Mock client
        mock_client = Mock()
        mock_client.get_sync_status = AsyncMock(return_value={
            "last_sync": "2025-07-31T10:00:00Z",
            "last_success": "2025-07-31T10:00:00Z",
            "total_syncs": 5,
            "sync_failures": 0,
            "total_conflicts": 2,
            "sync_in_progress": False,
            "last_error": None
        })
        mock_client.disconnect = AsyncMock()
        mock_client.is_connected = True

        # Mock load_client to directly return the mock_client
        mock_load_client.return_value = mock_client

        # Run command with temporary directory
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['status'])

        # Check it called the right method
        mock_client.get_sync_status.assert_called_once()

        # Check output
        assert result.exit_code == 0

    @patch('blowingoff.cli.main.load_client')
    def test_tools_command(self, mock_load_client):
        """Test 'tools' command lists MCP tools."""
        # Mock client
        mock_client = Mock()
        mock_client.get_available_mcp_tools = Mock(return_value=['create_entity', 'search_graph', 'sync_metadata'])
        mock_client.disconnect = AsyncMock()
        mock_load_client.return_value = mock_client

        # Run command
        result = self.runner.invoke(cli, ['tools'])

        # Check it called the right method
        mock_client.get_available_mcp_tools.assert_called_once()

        assert result.exit_code == 0
        assert "Available MCP Tools" in result.output or "create_entity" in result.output

    @patch('blowingoff.cli.main.load_client')
    def test_search_command(self, mock_load_client):
        """Test 'search' command searches entities."""
        # Mock client
        mock_client = Mock()
        mock_client.execute_mcp_tool = AsyncMock(return_value={
            "success": True,
            "result": {
                "results": [{
                    "entity": {
                        "id": "ent-1",
                        "name": "Test Light",
                        "entity_type": "device",
                        "content": {"manufacturer": "Test Corp"}
                    },
                    "score": 0.95
                }],
                "count": 1
            }
        })
        mock_client.disconnect = AsyncMock()
        mock_load_client.return_value = mock_client

        # Run command
        result = self.runner.invoke(cli, ['search', 'light'])

        # Check it called the right method (via execute_mcp_tool)
        mock_client.execute_mcp_tool.assert_called_once()

        assert result.exit_code == 0
        assert "Test Light" in result.output or "ent-1" in result.output

    @patch('blowingoff.cli.main.load_client')
    def test_create_command(self, mock_load_client):
        """Test 'create' command creates entities."""
        # Mock client
        mock_client = Mock()
        mock_client.execute_mcp_tool = AsyncMock(return_value={
            "success": True,
            "result": {"entity_id": "ent-123"}
        })
        mock_client.disconnect = AsyncMock()
        mock_load_client.return_value = mock_client

        # Run command
        result = self.runner.invoke(cli, ['create', 'device', 'New Light'])

        # Check it called the right method
        mock_client.execute_mcp_tool.assert_called_once_with(
            'create_entity',
            entity_type='device',
            name='New Light',
            content={},
            user_id='blowing-off-cli'
        )

        assert result.exit_code == 0
        assert "ent-123" in result.output or "Created" in result.output

    def test_invalid_command_not_available(self):
        """Test that invalid commands are rejected."""
        result = self.runner.invoke(cli, ['nonexistent', 'command'])

        # Should fail because command doesn't exist
        assert result.exit_code != 0
        assert "No such command 'nonexistent'" in result.output or "Error" in result.output

    def test_help_command_works(self):
        """Test that help shows available commands."""
        result = self.runner.invoke(cli, ['--help'])

        # Should show help
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "Commands:" in result.output

    @patch('blowingoff.cli.main.load_client')
    def test_sync_command_handles_errors(self, mock_load_client):
        """Test sync command handles server errors gracefully."""
        # Mock client that raises an error
        mock_client = Mock()
        mock_client.sync = AsyncMock(side_effect=Exception(
            "Server error '500 Internal Server Error' for url 'http://localhost:8000/api/v1/sync/request'"
        ))
        mock_client.disconnect = AsyncMock()
        mock_load_client.return_value = mock_client

        # Run command
        result = self.runner.invoke(cli, ['sync'])

        # The CLI handles the error gracefully now
        assert result.exit_code == 0  # Error handled gracefully
        assert "❌ Sync failed:" in result.output
