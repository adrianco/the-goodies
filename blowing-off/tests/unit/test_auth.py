"""Test authentication functionality."""

import pytest
import json
import aiohttp
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock, mock_open
import tempfile

from blowingoff.auth import AuthManager


class TestAuthManager:
    """Test AuthManager functionality."""
    
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
    
    @pytest.mark.asyncio
    async def test_login_admin_success(self, auth_manager):
        """Test successful admin login."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "access_token": "admin-token-789",
            "role": "admin",
            "expires_in": 3600
        })
        
        mock_post = MagicMock()
        mock_post.__aenter__.return_value = mock_response
        
        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value = mock_post
        mock_session_instance.__aenter__.return_value = mock_session_instance
        
        with patch('aiohttp.ClientSession', return_value=mock_session_instance):
            result = await auth_manager.login_admin("admin_password")
            
            assert result == True
            assert auth_manager.token == "admin-token-789"
            assert auth_manager.role == "admin"
            assert auth_manager.permissions == ['read', 'write', 'delete', 'configure']
            assert auth_manager.token_expires is not None
    
    @pytest.mark.asyncio
    async def test_login_admin_failure(self, auth_manager):
        """Test failed admin login."""
        mock_response = AsyncMock()
        mock_response.status = 401
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await auth_manager.login_admin("wrong_password")
            
            assert result == False
            assert auth_manager.token is None
    
    @pytest.mark.asyncio
    async def test_login_admin_network_error(self, auth_manager):
        """Test admin login with network error."""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.post.side_effect = aiohttp.ClientError()
            
            result = await auth_manager.login_admin("admin_password")
            
            assert result == False
            assert auth_manager.token is None
    
    @pytest.mark.asyncio
    async def test_login_guest_success(self, auth_manager):
        """Test successful guest login with QR code."""
        qr_data = json.dumps({
            "type": "guest_access",
            "server": "localhost",
            "port": 8000,
            "token": "guest-qr-token"
        })
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "access_token": "guest-token-123",
            "role": "guest",
            "expires_in": 3600
        })
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await auth_manager.login_guest(qr_data)
            
            assert result == True
            assert auth_manager.token == "guest-token-123"
            assert auth_manager.role == "guest"
            assert auth_manager.permissions == ["read"]
            assert auth_manager.server_url == "http://localhost:8000"
    
    @pytest.mark.asyncio
    async def test_login_guest_invalid_type(self, auth_manager):
        """Test guest login with invalid QR type."""
        qr_data = json.dumps({
            "type": "admin_access",  # Wrong type
            "server": "localhost",
            "port": 8000,
            "token": "token"
        })
        
        result = await auth_manager.login_guest(qr_data)
        
        assert result == False
        assert auth_manager.token is None
    
    @pytest.mark.asyncio
    async def test_login_guest_invalid_json(self, auth_manager):
        """Test guest login with invalid JSON."""
        qr_data = "not valid json"
        
        result = await auth_manager.login_guest(qr_data)
        
        assert result == False
        assert auth_manager.token is None
    
    @pytest.mark.asyncio
    async def test_login_guest_network_error(self, auth_manager):
        """Test guest login with network error."""
        qr_data = json.dumps({
            "type": "guest_access",
            "server": "localhost",
            "port": 8000,
            "token": "guest-qr-token"
        })
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.post.side_effect = aiohttp.ClientError()
            
            result = await auth_manager.login_guest(qr_data)
            
            assert result == False
    
    def test_is_authenticated_valid(self, auth_manager):
        """Test is_authenticated with valid token."""
        auth_manager.token = "valid-token"
        auth_manager.token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        
        assert auth_manager.is_authenticated() == True
    
    def test_is_authenticated_expired(self, auth_manager):
        """Test is_authenticated with expired token."""
        auth_manager.token = "expired-token"
        auth_manager.token_expires = datetime.now(timezone.utc) - timedelta(hours=1)
        
        assert auth_manager.is_authenticated() == False
    
    def test_is_authenticated_no_token(self, auth_manager):
        """Test is_authenticated with no token."""
        assert auth_manager.is_authenticated() == False
    
    def test_has_permission_admin(self, auth_manager):
        """Test permission check for admin."""
        auth_manager.role = "admin"
        auth_manager.permissions = ["read", "write", "delete", "configure"]
        
        assert auth_manager.has_permission("read") == True
        assert auth_manager.has_permission("write") == True
        assert auth_manager.has_permission("delete") == True
        assert auth_manager.has_permission("configure") == True
    
    def test_has_permission_user(self, auth_manager):
        """Test permission check for regular user."""
        auth_manager.role = "user"
        auth_manager.permissions = ["read"]
        
        assert auth_manager.has_permission("read") == True
        assert auth_manager.has_permission("write") == False
        assert auth_manager.has_permission("delete") == False
    
    def test_has_permission_no_permissions(self, auth_manager):
        """Test permission check with no permissions set."""
        auth_manager.permissions = []
        
        assert auth_manager.has_permission("read") == False
    
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
        
        # Logout (not async)
        auth_manager.logout()
        
        # Check state is cleared
        assert auth_manager.token is None
        assert auth_manager.token_expires is None
        assert auth_manager.role is None
        assert auth_manager.permissions == []
        
        # Check token file is removed
        assert not temp_token_file.exists()
    
    @pytest.mark.asyncio
    async def test_refresh_token_admin_success(self, auth_manager):
        """Test successful token refresh for admin."""
        auth_manager.token = "old-token"
        auth_manager.role = "admin"  # Only admin can refresh
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "access_token": "refreshed-token",
            "expires_in": 3600
        })
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await auth_manager.refresh_token()
            
            assert result == True
            assert auth_manager.token == "refreshed-token"
    
    @pytest.mark.asyncio
    async def test_refresh_token_non_admin(self, auth_manager):
        """Test token refresh for non-admin (should fail)."""
        auth_manager.token = "user-token"
        auth_manager.role = "user"  # Non-admin cannot refresh
        
        result = await auth_manager.refresh_token()
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_refresh_token_no_token(self, auth_manager):
        """Test token refresh with no token."""
        auth_manager.token = None
        
        result = await auth_manager.refresh_token()
        
        assert result == False
    
    def test_get_headers(self, auth_manager):
        """Test getting authorization headers."""
        auth_manager.token = "bearer-token"
        
        headers = auth_manager.get_headers()
        
        assert headers["Authorization"] == "Bearer bearer-token"
    
    def test_get_headers_no_token(self, auth_manager):
        """Test getting headers with no token."""
        headers = auth_manager.get_headers()
        
        assert headers == {}
    
    @pytest.mark.asyncio
    async def test_generate_guest_qr_admin(self, auth_manager):
        """Test generating guest QR code as admin."""
        auth_manager.role = "admin"
        auth_manager.token = "admin-token"
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "qr_code": "base64encodedimage",
            "qr_data": "qr_data_json",
            "expires_in": 86400
        })
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await auth_manager.generate_guest_qr(duration_hours=24)
            
            assert result is not None
            assert result["qr_code"] == "base64encodedimage"
            assert result["qr_data"] == "qr_data_json"
            assert result["expires_in"] == 86400
    
    @pytest.mark.asyncio
    async def test_generate_guest_qr_non_admin(self, auth_manager):
        """Test generating guest QR code as non-admin (should fail)."""
        auth_manager.role = "user"
        
        result = await auth_manager.generate_guest_qr()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_save_guest_qr(self, auth_manager, tmp_path):
        """Test saving guest QR code to file."""
        qr_data = {
            "qr_code": base64.b64encode(b"fake_image_data").decode(),
            "qr_data": "data",
            "expires_in": 3600
        }
        
        output_file = tmp_path / "test_qr.png"
        
        await auth_manager.save_guest_qr(qr_data, str(output_file))
        
        assert output_file.exists()
        
        with open(output_file, 'rb') as f:
            content = f.read()
        
        assert content == b"fake_image_data"
    
    @pytest.mark.asyncio
    async def test_save_guest_qr_no_data(self, auth_manager):
        """Test saving guest QR with no data."""
        # Should not raise error
        await auth_manager.save_guest_qr(None, "test.png")
        
        # Also test with missing qr_code key
        await auth_manager.save_guest_qr({"other": "data"}, "test.png")