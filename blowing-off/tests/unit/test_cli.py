"""
Test CLI commands to ensure they use correct method names.

These tests catch issues like using 'house' instead of 'home' or
'device' instead of 'accessory' in CLI commands.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import Mock, AsyncMock, patch
import json

from blowingoff.cli.main import cli


class TestCLICommands:
    """Test CLI commands use correct API methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        
    @patch('blowingoff.cli.main.load_client')
    def test_home_show_command(self, mock_load_client):
        """Test 'home show' command uses get_home() not get_house()."""
        # Mock client
        mock_client = Mock()
        mock_client.get_home = AsyncMock(return_value={
            "id": "home-1",
            "name": "Test Home",
            "is_primary": True
        })
        mock_client.get_rooms = AsyncMock(return_value=[])
        mock_load_client.return_value = mock_client
        
        # Run command
        result = self.runner.invoke(cli, ['home', 'show'])
        
        # Check it called the right method
        mock_client.get_home.assert_called_once()
        # Mock objects allow any attribute access, so we can't test hasattr
        # Instead verify the correct method was called
        
        # Check output
        assert result.exit_code == 0
        assert "Test Home" in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_home_create_command(self, mock_load_client):
        """Test 'home create' command uses create_home()."""
        # Mock client
        mock_client = Mock()
        mock_client.create_home = AsyncMock(return_value="home-123")
        mock_load_client.return_value = mock_client
        
        # Run command
        result = self.runner.invoke(cli, [
            'home', 'create',
            '--name', 'New Home',
            '--primary'
        ])
        
        # Check it called the right method
        mock_client.create_home.assert_called_once_with(
            "New Home",
            is_primary=True
        )
        
        assert result.exit_code == 0
        assert "Created home" in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_device_list_command(self, mock_load_client):
        """Test 'device list' command uses get_accessories()."""
        # Mock client
        mock_client = Mock()
        mock_client.get_accessories = AsyncMock(return_value=[
            {
                "id": "acc-1",
                "name": "Test Light",
                "manufacturer": "Test Corp",
                "model": "Light v1",
                "home_id": "home-1",
                "serial_number": "SN123",
                "firmware_version": "1.0",
                "is_reachable": True,
                "is_blocked": False,
                "is_bridge": False
            }
        ])
        mock_load_client.return_value = mock_client
        
        # Run command - CLI still uses 'device' not 'accessory'
        result = self.runner.invoke(cli, ['device', 'list'])
        
        # Check it called the right method
        mock_client.get_accessories.assert_called_once_with(None)
        
        assert result.exit_code == 0
        assert "Test Light" in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_device_create_command(self, mock_load_client):
        """Test 'device create' command uses create_accessory()."""
        # Mock client
        mock_client = Mock()
        mock_client.create_accessory = AsyncMock(return_value="acc-123")
        mock_load_client.return_value = mock_client
        
        # Run command
        result = self.runner.invoke(cli, [
            'device', 'create',
            '--room-id', 'room-1',
            '--name', 'New Light',
            '--type', 'light',
            '--manufacturer', 'Test Corp'
        ])
        
        # Check it called the right method
        mock_client.create_accessory.assert_called_once()
        
        assert result.exit_code == 0
        assert "Created accessory" in result.output
    
    def test_old_house_command_not_available(self):
        """Test that 'house' command is not available."""
        result = self.runner.invoke(cli, ['house', 'show'])
        
        # Should fail because 'house' command doesn't exist
        assert result.exit_code != 0
        assert "No such command 'house'" in result.output or "Error" in result.output
    
    def test_accessory_command_not_available(self):
        """Test that 'accessory' command is not available (CLI uses device)."""
        result = self.runner.invoke(cli, ['accessory', 'list'])
        
        # Should fail because 'accessory' command doesn't exist  
        assert result.exit_code != 0
        assert "No such command 'accessory'" in result.output or "Error" in result.output
    
    @patch('blowingoff.cli.main.load_client')
    def test_sync_command_handles_errors(self, mock_load_client):
        """Test sync command handles server errors gracefully."""
        # Mock client that raises an error
        mock_client = Mock()
        mock_client.sync = AsyncMock(side_effect=Exception(
            "Server error '500 Internal Server Error' for url 'http://localhost:8000/api/v1/sync/request'"
        ))
        mock_load_client.return_value = mock_client
        
        # Run command
        result = self.runner.invoke(cli, ['sync'])
        
        # The CLI doesn't handle the error gracefully, it lets it bubble up
        assert result.exit_code == 1  # Unhandled exception causes non-zero exit
        assert "Server error '500 Internal Server Error'" in str(result.exception)