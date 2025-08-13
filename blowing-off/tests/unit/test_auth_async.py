"""Test async authentication methods."""

import pytest
import json
import aiohttp
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
import tempfile

from blowingoff.auth import AuthManager


def create_mock_response(status, json_data=None):
    """Helper to create mock response."""
    mock_response = MagicMock()
    mock_response.status = status
    if json_data:
        mock_response.json = AsyncMock(return_value=json_data)
    return mock_response


def create_mock_session(response):
    """Helper to create mock session."""
    mock_post = MagicMock()
    mock_post.__aenter__.return_value = response
    
    mock_session = MagicMock()
    mock_session.post.return_value = mock_post
    mock_session.__aenter__.return_value = mock_session
    
    return mock_session


class TestAuthManagerAsync:
    """Test async methods of AuthManager."""
    
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
    
    @pytest.mark.asyncio
    async def test_login_admin_success(self, auth_manager):
        """Test successful admin login."""
        response = create_mock_response(200, {
            "access_token": "admin-token-789",
            "role": "admin",
            "expires_in": 3600
        })
        session = create_mock_session(response)
        
        with patch('aiohttp.ClientSession', return_value=session):
            result = await auth_manager.login_admin("admin_password")
            
            assert result is True
            assert auth_manager.token == "admin-token-789"
            assert auth_manager.role == "admin"
            assert auth_manager.permissions == ['read', 'write', 'delete', 'configure']
            assert auth_manager.token_expires is not None
    
    @pytest.mark.asyncio
    async def test_login_admin_failure(self, auth_manager):
        """Test failed admin login."""
        response = create_mock_response(401)
        session = create_mock_session(response)
        
        with patch('aiohttp.ClientSession', return_value=session):
            result = await auth_manager.login_admin("wrong_password")
            
            assert result is False
            assert auth_manager.token is None
    
    @pytest.mark.asyncio
    async def test_login_admin_network_error(self, auth_manager):
        """Test admin login with network error."""
        mock_session = MagicMock()
        mock_session.__aenter__.return_value.post.side_effect = aiohttp.ClientError()
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await auth_manager.login_admin("admin_password")
            
            assert result is False
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
        
        response = create_mock_response(200, {
            "access_token": "guest-token-123",
            "role": "guest",
            "expires_in": 3600
        })
        session = create_mock_session(response)
        
        with patch('aiohttp.ClientSession', return_value=session):
            result = await auth_manager.login_guest(qr_data)
            
            assert result is True
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
        
        assert result is False
        assert auth_manager.token is None
    
    @pytest.mark.asyncio
    async def test_login_guest_invalid_json(self, auth_manager):
        """Test guest login with invalid JSON."""
        qr_data = "not valid json"
        
        result = await auth_manager.login_guest(qr_data)
        
        assert result is False
        assert auth_manager.token is None
    
    @pytest.mark.asyncio
    async def test_login_guest_failure(self, auth_manager):
        """Test failed guest login."""
        qr_data = json.dumps({
            "type": "guest_access",
            "server": "localhost",
            "port": 8000,
            "token": "invalid-token"
        })
        
        response = create_mock_response(401)
        session = create_mock_session(response)
        
        with patch('aiohttp.ClientSession', return_value=session):
            result = await auth_manager.login_guest(qr_data)
            
            assert result is False
            assert auth_manager.token is None
    
    @pytest.mark.asyncio
    async def test_refresh_token_admin_success(self, auth_manager):
        """Test successful token refresh for admin."""
        auth_manager.token = "old-token"
        auth_manager.role = "admin"  # Only admin can refresh
        
        response = create_mock_response(200, {
            "access_token": "refreshed-token",
            "expires_in": 3600
        })
        session = create_mock_session(response)
        
        with patch('aiohttp.ClientSession', return_value=session):
            result = await auth_manager.refresh_token()
            
            assert result is True
            assert auth_manager.token == "refreshed-token"
            assert auth_manager.token_expires is not None
    
    @pytest.mark.asyncio
    async def test_refresh_token_non_admin(self, auth_manager):
        """Test token refresh for non-admin (should fail)."""
        auth_manager.token = "user-token"
        auth_manager.role = "user"  # Non-admin cannot refresh
        
        result = await auth_manager.refresh_token()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_refresh_token_no_token(self, auth_manager):
        """Test token refresh with no token."""
        auth_manager.token = None
        
        result = await auth_manager.refresh_token()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_refresh_token_failure(self, auth_manager):
        """Test failed token refresh."""
        auth_manager.token = "old-token"
        auth_manager.role = "admin"
        
        response = create_mock_response(401)
        session = create_mock_session(response)
        
        with patch('aiohttp.ClientSession', return_value=session):
            result = await auth_manager.refresh_token()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_refresh_token_network_error(self, auth_manager):
        """Test token refresh with network error."""
        auth_manager.token = "old-token"
        auth_manager.role = "admin"
        
        mock_session = MagicMock()
        mock_session.__aenter__.return_value.post.side_effect = aiohttp.ClientError()
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await auth_manager.refresh_token()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_generate_guest_qr_admin(self, auth_manager):
        """Test generating guest QR code as admin."""
        auth_manager.role = "admin"
        auth_manager.token = "admin-token"
        
        response = create_mock_response(200, {
            "qr_code": "base64encodedimage",
            "qr_data": "qr_data_json",
            "expires_in": 86400
        })
        session = create_mock_session(response)
        
        with patch('aiohttp.ClientSession', return_value=session):
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
    async def test_generate_guest_qr_failure(self, auth_manager):
        """Test failed guest QR generation."""
        auth_manager.role = "admin"
        auth_manager.token = "admin-token"
        
        response = create_mock_response(403)
        session = create_mock_session(response)
        
        with patch('aiohttp.ClientSession', return_value=session):
            result = await auth_manager.generate_guest_qr()
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_generate_guest_qr_network_error(self, auth_manager):
        """Test guest QR generation with network error."""
        auth_manager.role = "admin"
        auth_manager.token = "admin-token"
        
        mock_session = MagicMock()
        mock_session.__aenter__.return_value.post.side_effect = aiohttp.ClientError()
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
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