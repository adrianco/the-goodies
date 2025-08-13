"""Test synchronous authentication methods."""

import pytest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open, patch
import tempfile

from blowingoff.auth import AuthManager


class TestAuthManagerSync:
    """Test synchronous methods of AuthManager."""
    
    @pytest.fixture
    def temp_token_file(self, tmp_path):
        """Create a temporary token file."""
        return tmp_path / "token.json"
    
    @pytest.fixture
    def auth_manager(self, temp_token_file):
        """Create an AuthManager instance."""
        return AuthManager(
            server_url="http://localhost:8000",
            token_file=temp_token_file
        )
    
    @pytest.fixture
    def valid_token_data(self):
        """Create valid token data."""
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        return {
            "token": "test-token-123",
            "expires": expires.isoformat(),
            "role": "admin",
            "permissions": ["read", "write", "delete", "configure"]
        }
    
    @pytest.fixture
    def expired_token_data(self):
        """Create expired token data."""
        expires = datetime.now(timezone.utc) - timedelta(hours=1)
        return {
            "token": "expired-token-123",
            "expires": expires.isoformat(),
            "role": "user",
            "permissions": ["read"]
        }
    
    def test_init(self, temp_token_file):
        """Test AuthManager initialization."""
        auth = AuthManager(
            server_url="http://localhost:8000/",
            token_file=temp_token_file
        )
        
        assert auth.server_url == "http://localhost:8000"
        assert auth.token_file == temp_token_file
        assert auth.token is None
        assert auth.token_expires is None
        assert auth.role is None
        assert auth.permissions == []
        assert temp_token_file.parent.exists()
    
    def test_init_default_token_file(self):
        """Test AuthManager with default token file."""
        auth = AuthManager(server_url="http://localhost:8000")
        
        expected_path = Path.home() / ".blowing-off" / "token.json"
        assert auth.token_file == expected_path
        assert auth.token_file.parent.exists()
    
    def test_load_valid_token(self, temp_token_file, valid_token_data):
        """Test loading a valid saved token."""
        # Write valid token to file
        with open(temp_token_file, 'w') as f:
            json.dump(valid_token_data, f)
        
        # Create auth manager - should load token
        auth = AuthManager(
            server_url="http://localhost:8000",
            token_file=temp_token_file
        )
        
        assert auth.token == "test-token-123"
        assert auth.token_expires is not None
        assert auth.role == "admin"
        assert auth.permissions == ["read", "write", "delete", "configure"]
    
    def test_load_expired_token(self, temp_token_file, expired_token_data):
        """Test loading an expired token (should not load)."""
        # Write expired token to file
        with open(temp_token_file, 'w') as f:
            json.dump(expired_token_data, f)
        
        # Create auth manager - should not load expired token
        auth = AuthManager(
            server_url="http://localhost:8000",
            token_file=temp_token_file
        )
        
        assert auth.token is None
        assert auth.token_expires is None
        assert auth.role is None
        assert auth.permissions == []
    
    def test_load_invalid_token_file(self, temp_token_file):
        """Test loading an invalid token file."""
        # Write invalid JSON to file
        with open(temp_token_file, 'w') as f:
            f.write("invalid json")
        
        # Create auth manager - should handle error gracefully
        auth = AuthManager(
            server_url="http://localhost:8000",
            token_file=temp_token_file
        )
        
        assert auth.token is None
        assert auth.token_expires is None
    
    def test_load_missing_token_file(self, temp_token_file):
        """Test loading when token file doesn't exist."""
        # Ensure file doesn't exist
        if temp_token_file.exists():
            temp_token_file.unlink()
        
        # Create auth manager
        auth = AuthManager(
            server_url="http://localhost:8000",
            token_file=temp_token_file
        )
        
        assert auth.token is None
        assert auth.token_expires is None
    
    def test_save_token(self, auth_manager, temp_token_file):
        """Test saving token to file."""
        # Set token data
        auth_manager.token = "saved-token-456"
        auth_manager.token_expires = datetime.now(timezone.utc) + timedelta(hours=2)
        auth_manager.role = "user"
        auth_manager.permissions = ["read", "write"]
        
        # Save token
        auth_manager._save_token()
        
        # Verify file was written
        assert temp_token_file.exists()
        
        # Load and verify content
        with open(temp_token_file, 'r') as f:
            data = json.load(f)
        
        assert data["token"] == "saved-token-456"
        assert data["role"] == "user"
        assert data["permissions"] == ["read", "write"]
        assert "expires" in data
    
    def test_save_token_no_token(self, auth_manager, temp_token_file):
        """Test saving when no token is set."""
        # No token set
        auth_manager._save_token()
        
        # File should not be created
        assert not temp_token_file.exists()
    
    def test_save_token_no_expires(self, auth_manager, temp_token_file):
        """Test saving when token expires is not set."""
        auth_manager.token = "token-without-expires"
        # No token_expires set
        
        auth_manager._save_token()
        
        # File should not be created
        assert not temp_token_file.exists()
    
    def test_is_authenticated_valid(self, auth_manager):
        """Test is_authenticated with valid token."""
        auth_manager.token = "valid-token"
        auth_manager.token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        
        assert auth_manager.is_authenticated() is True
    
    def test_is_authenticated_expired(self, auth_manager):
        """Test is_authenticated with expired token."""
        auth_manager.token = "expired-token"
        auth_manager.token_expires = datetime.now(timezone.utc) - timedelta(hours=1)
        
        assert auth_manager.is_authenticated() is False
        
        # Token should be cleared
        assert auth_manager.token is None
        assert auth_manager.token_expires is None
    
    def test_is_authenticated_no_token(self, auth_manager):
        """Test is_authenticated with no token."""
        assert auth_manager.is_authenticated() is False
    
    def test_is_authenticated_no_expires(self, auth_manager):
        """Test is_authenticated with token but no expires."""
        auth_manager.token = "token-no-expires"
        auth_manager.token_expires = None
        
        assert auth_manager.is_authenticated() is False
    
    def test_has_permission_admin(self, auth_manager):
        """Test permission check for admin."""
        auth_manager.role = "admin"
        auth_manager.permissions = ["read", "write", "delete", "configure"]
        
        assert auth_manager.has_permission("read") is True
        assert auth_manager.has_permission("write") is True
        assert auth_manager.has_permission("delete") is True
        assert auth_manager.has_permission("configure") is True
    
    def test_has_permission_user(self, auth_manager):
        """Test permission check for regular user."""
        auth_manager.role = "user"
        auth_manager.permissions = ["read"]
        
        assert auth_manager.has_permission("read") is True
        assert auth_manager.has_permission("write") is False
        assert auth_manager.has_permission("delete") is False
        assert auth_manager.has_permission("configure") is False
    
    def test_has_permission_guest(self, auth_manager):
        """Test permission check for guest."""
        auth_manager.role = "guest"
        auth_manager.permissions = ["read"]
        
        assert auth_manager.has_permission("read") is True
        assert auth_manager.has_permission("write") is False
    
    def test_has_permission_no_permissions(self, auth_manager):
        """Test permission check with no permissions set."""
        auth_manager.permissions = []
        
        assert auth_manager.has_permission("read") is False
        assert auth_manager.has_permission("write") is False
    
    def test_has_permission_unknown(self, auth_manager):
        """Test permission check for unknown permission."""
        auth_manager.permissions = ["read", "write"]
        
        assert auth_manager.has_permission("unknown_permission") is False
    
    def test_get_headers(self, auth_manager):
        """Test getting authorization headers."""
        auth_manager.token = "bearer-token"
        
        headers = auth_manager.get_headers()
        
        assert headers["Authorization"] == "Bearer bearer-token"
    
    def test_get_headers_no_token(self, auth_manager):
        """Test getting headers with no token."""
        headers = auth_manager.get_headers()
        
        assert headers == {}
    
    def test_logout(self, auth_manager, temp_token_file):
        """Test logout functionality."""
        # Set up authenticated state
        auth_manager.token = "active-token"
        auth_manager.token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        auth_manager.role = "user"
        auth_manager.permissions = ["read"]
        
        # Save token to file
        auth_manager._save_token()
        assert temp_token_file.exists()
        
        # Logout
        auth_manager.logout()
        
        # Check state is cleared
        assert auth_manager.token is None
        assert auth_manager.token_expires is None
        assert auth_manager.role is None
        assert auth_manager.permissions == []
        
        # Check token file is removed
        assert not temp_token_file.exists()
    
    def test_logout_no_token_file(self, auth_manager, temp_token_file):
        """Test logout when token file doesn't exist."""
        # Set up authenticated state
        auth_manager.token = "active-token"
        auth_manager.token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        auth_manager.role = "user"
        auth_manager.permissions = ["read"]
        
        # Ensure file doesn't exist
        if temp_token_file.exists():
            temp_token_file.unlink()
        
        # Logout should not raise error
        auth_manager.logout()
        
        # Check state is cleared
        assert auth_manager.token is None
        assert auth_manager.token_expires is None
        assert auth_manager.role is None
        assert auth_manager.permissions == []
    
    def test_server_url_normalization(self):
        """Test server URL normalization (removing trailing slash)."""
        auth1 = AuthManager(server_url="http://localhost:8000/")
        assert auth1.server_url == "http://localhost:8000"
        
        auth2 = AuthManager(server_url="http://localhost:8000")
        assert auth2.server_url == "http://localhost:8000"
        
        auth3 = AuthManager(server_url="http://localhost:8000//")
        assert auth3.server_url == "http://localhost:8000"