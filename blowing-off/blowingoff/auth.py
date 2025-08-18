"""
Authentication module for Blowing-off client.

Handles password and QR code authentication with the FunkyGibbon server.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any

import aiohttp


class AuthManager:
    """Manage authentication for the Blowing-off client."""

    def __init__(self, server_url: str, token_file: Path = None):
        """
        Initialize authentication manager.

        Args:
            server_url: Base URL of the FunkyGibbon server
            token_file: Optional path to store tokens persistently
        """
        self.server_url = server_url.rstrip('/')
        self.token_file = token_file or Path.home() / ".blowing-off" / "token.json"
        self.token: Optional[str] = None
        self.token_expires: Optional[datetime] = None
        self.role: Optional[str] = None
        self.permissions: list = []

        # Create token directory if needed
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

        # Load saved token if available
        self._load_token()

    def _load_token(self):
        """Load saved token from file."""
        if self.token_file.exists():
            try:
                with open(self.token_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # Check if token is still valid
                    expires = datetime.fromisoformat(data['expires'])
                    if expires > datetime.now(timezone.utc):
                        self.token = data['token']
                        self.token_expires = expires
                        self.role = data.get('role', 'guest')
                        self.permissions = data.get('permissions', [])
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                # Invalid token file, will need to re-authenticate
                pass

    def _save_token(self):
        """Save token to file."""
        if self.token and self.token_expires:
            data = {
                'token': self.token,
                'expires': self.token_expires.isoformat(),
                'role': self.role,
                'permissions': self.permissions
            }
            with open(self.token_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)

    async def login_admin(self, password: str) -> bool:
        """
        Authenticate as admin with password.

        Args:
            password: Admin password

        Returns:
            True if authentication successful
        """
        url = f"{self.server_url}/api/v1/auth/admin/login"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json={'password': password}) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.token = data['access_token']
                        self.role = data['role']

                        # Calculate expiration
                        expires_in = data['expires_in']
                        self.token_expires = (
                            datetime.now(timezone.utc) +
                            timedelta(seconds=expires_in)
                        )

                        # Set permissions for admin
                        self.permissions = ['read', 'write', 'delete', 'configure']

                        # Save token
                        self._save_token()

                        return True
                    return False

            except (aiohttp.ClientError, json.JSONDecodeError) as e:
                print(f"Authentication error: {e}")
                return False

    async def login_guest(self, qr_data: str) -> bool:
        """
        Authenticate as guest with QR code data.

        Args:
            qr_data: JSON string from scanned QR code

        Returns:
            True if authentication successful
        """
        try:
            # Parse QR data
            qr_info = json.loads(qr_data)

            # Verify it's a guest access QR
            if qr_info.get('type') != 'guest_access':
                return False

            # Extract server info and token
            server = qr_info.get('server')
            port = qr_info.get('port')
            guest_token = qr_info.get('token')

            # Verify guest token with server
            url = f"http://{server}:{port}/api/v1/auth/guest/verify"

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={'token': guest_token}) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.token = data['access_token']
                        self.role = data['role']

                        # Calculate expiration
                        expires_in = data['expires_in']
                        self.token_expires = (
                            datetime.now(timezone.utc) +
                            timedelta(seconds=expires_in)
                        )

                        # Set guest permissions
                        self.permissions = ['read']

                        # Save token
                        self._save_token()

                        # Update server URL if different
                        self.server_url = f"http://{server}:{port}"

                        return True
                    return False

        except Exception as e:
            print(f"Guest authentication error: {e}")
            return False

    async def refresh_token(self) -> bool:
        """
        Refresh authentication token.

        Returns:
            True if refresh successful
        """
        if not self.token:
            return False

        # Only admin tokens can be refreshed
        if self.role != 'admin':
            return False

        url = f"{self.server_url}/api/v1/auth/refresh"

        async with aiohttp.ClientSession() as session:
            headers = {'Authorization': f'Bearer {self.token}'}

            try:
                async with session.post(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.token = data['access_token']

                        # Calculate new expiration
                        expires_in = data['expires_in']
                        self.token_expires = (
                            datetime.now(timezone.utc) +
                            timedelta(seconds=expires_in)
                        )

                        # Save updated token
                        self._save_token()

                        return True
                    return False

            except (aiohttp.ClientError, json.JSONDecodeError) as e:
                print(f"Token refresh error: {e}")
                return False

    def get_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for API requests.

        Returns:
            Dictionary with authorization header
        """
        if self.token:
            return {'Authorization': f'Bearer {self.token}'}
        return {}

    def is_authenticated(self) -> bool:
        """
        Check if currently authenticated.

        Returns:
            True if authenticated with valid token
        """
        if not self.token or not self.token_expires:
            return False

        # Check if token is expired
        if datetime.now(timezone.utc) >= self.token_expires:
            self.token = None
            self.token_expires = None
            return False

        return True

    def has_permission(self, permission: str) -> bool:
        """
        Check if user has specific permission.

        Args:
            permission: Permission to check (read, write, delete, configure)

        Returns:
            True if user has permission
        """
        return permission in self.permissions

    def logout(self):
        """Clear authentication state."""
        self.token = None
        self.token_expires = None
        self.role = None
        self.permissions = []

        # Remove saved token
        if self.token_file.exists():
            self.token_file.unlink()

    async def generate_guest_qr(self, duration_hours: int = 24) -> Optional[Dict[str, Any]]:
        """
        Generate a guest QR code (admin only).

        Args:
            duration_hours: Guest token validity in hours

        Returns:
            QR code data and image, or None if not admin
        """
        if self.role != 'admin':
            return None

        url = f"{self.server_url}/api/v1/auth/guest/generate-qr"

        async with aiohttp.ClientSession() as session:
            headers = self.get_headers()

            try:
                async with session.post(
                    url,
                    headers=headers,
                    json={'duration_hours': duration_hours}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            'qr_code': data['qr_code'],  # Base64 encoded image
                            'qr_data': data['qr_data'],
                            'expires_in': data['expires_in']
                        }
                    else:
                        return None

            except (aiohttp.ClientError, json.JSONDecodeError) as e:
                print(f"QR generation error: {e}")
                return None

    async def save_guest_qr(self, qr_data: Dict[str, Any], filename: str = "guest_qr.png"):
        """
        Save guest QR code image to file.

        Args:
            qr_data: QR data from generate_guest_qr
            filename: Output filename
        """
        if not qr_data or 'qr_code' not in qr_data:
            return

        # Decode base64 image
        img_data = base64.b64decode(qr_data['qr_code'])

        # Save to file
        with open(filename, 'wb') as f:
            f.write(img_data)

        print(f"QR code saved to {filename}")
