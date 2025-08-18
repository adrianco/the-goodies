"""
QR code generation for guest access.

Creates QR codes containing server information and guest tokens.
"""

import qrcode
import json
import base64
from io import BytesIO
from datetime import datetime, timedelta, timezone
from typing import Tuple, Dict, Any


class QRCodeManager:
    """Generate and manage QR codes for guest access."""

    def __init__(self, server_address: str = "funkygibbon.local", port: int = 8000):
        """
        Initialize QR code manager.

        Args:
            server_address: Server hostname or IP address
            port: Server port number
        """
        self.server_address = server_address
        self.port = port

    def generate_guest_qr(self,
                         guest_token: str,
                         duration_hours: int = 24,
                         custom_server: str = None) -> Tuple[Dict[str, Any], str]:
        """
        Generate QR code for guest access.

        Args:
            guest_token: Pre-generated guest access token
            duration_hours: Token validity duration
            custom_server: Override default server address

        Returns:
            Tuple of (qr_data_dict, base64_encoded_image)
        """
        server = custom_server or self.server_address
        expires = datetime.now(timezone.utc) + timedelta(hours=duration_hours)

        # Data to encode in QR code
        qr_data = {
            "version": "1.0",
            "type": "guest_access",
            "server": server,
            "port": self.port,
            "token": guest_token,
            "expires": expires.isoformat(),
            "permissions": ["read"]
        }

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,  # Controls size (1 is smallest)
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )

        qr.add_data(json.dumps(qr_data))
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        return qr_data, img_base64

    def generate_setup_qr(self, admin_token: str = None) -> Tuple[Dict[str, Any], str]:
        """
        Generate QR code for initial setup.

        Args:
            admin_token: Optional admin setup token

        Returns:
            Tuple of (qr_data_dict, base64_encoded_image)
        """
        # Data for initial setup
        qr_data = {
            "version": "1.0",
            "type": "server_setup",
            "server": self.server_address,
            "port": self.port,
            "mdns_name": "funkygibbon.local",
            "setup_token": admin_token,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,  # Higher error correction for setup
            box_size=10,
            border=4,
        )

        qr.add_data(json.dumps(qr_data))
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        return qr_data, img_base64

    def parse_qr_data(self, qr_string: str) -> Dict[str, Any]:
        """
        Parse QR code data from scanned string.

        Args:
            qr_string: JSON string from QR code

        Returns:
            Parsed QR data dictionary

        Raises:
            ValueError: If QR data is invalid
        """
        try:
            data = json.loads(qr_string)

            # Validate required fields based on type
            if data.get("type") == "guest_access":
                required = ["version", "type", "server", "port", "token", "expires"]
                if not all(field in data for field in required):
                    raise ValueError("Missing required fields in guest access QR")

                # Parse expiration date
                data["expires"] = datetime.fromisoformat(data["expires"].replace("Z", "+00:00"))

            elif data.get("type") == "server_setup":
                required = ["version", "type", "server", "port"]
                if not all(field in data for field in required):
                    raise ValueError("Missing required fields in setup QR")
            else:
                raise ValueError(f"Unknown QR type: {data.get('type')}")

            return data

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid QR data: {e}")

    def create_connection_url(self, token: str = None) -> str:
        """
        Create a connection URL for the iOS app.

        Args:
            token: Optional authentication token

        Returns:
            Connection URL string
        """
        base_url = f"funkygibbon://{self.server_address}:{self.port}"

        if token:
            return f"{base_url}?token={token}"

        return base_url
