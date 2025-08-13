#!/bin/bash

# FunkyGibbon Smart Home Server Installation Script
# Sets up the server with admin authentication

set -e  # Exit on error

echo "==========================================="
echo "FunkyGibbon Smart Home Server Setup"
echo "==========================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -Po '(?<=Python )\d+\.\d+')
REQUIRED_VERSION="3.9"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "Error: Python $REQUIRED_VERSION or higher is required (found $PYTHON_VERSION)"
    exit 1
fi

# Check if running as root (not recommended)
if [ "$EUID" -eq 0 ]; then 
   echo "Warning: Running as root is not recommended for security reasons."
   read -p "Continue anyway? (y/N): " -n 1 -r
   echo
   if [[ ! $REPLY =~ ^[Yy]$ ]]; then
       exit 1
   fi
fi

# Create config directory
CONFIG_DIR="/etc/funkygibbon"
if [ ! -d "$CONFIG_DIR" ]; then
    echo "Creating configuration directory..."
    sudo mkdir -p "$CONFIG_DIR"
    sudo chown $USER:$USER "$CONFIG_DIR"
fi

# Prompt for admin password
echo ""
echo "Admin Password Setup"
echo "--------------------"
echo "The admin password is required to access and configure the server."
echo "Password requirements:"
echo "  - Minimum 12 characters"
echo "  - At least one uppercase letter"
echo "  - At least one lowercase letter"
echo "  - At least one digit"
echo "  - At least one special character"
echo ""

while true; do
    read -s -p "Enter admin password: " ADMIN_PASSWORD
    echo
    read -s -p "Confirm admin password: " ADMIN_PASSWORD_CONFIRM
    echo
    
    if [ "$ADMIN_PASSWORD" != "$ADMIN_PASSWORD_CONFIRM" ]; then
        echo "Passwords do not match. Please try again."
        continue
    fi
    
    # Check password strength
    if [ ${#ADMIN_PASSWORD} -lt 12 ]; then
        echo "Password must be at least 12 characters long."
        continue
    fi
    
    # Check for required character types
    if ! echo "$ADMIN_PASSWORD" | grep -q '[A-Z]'; then
        echo "Password must contain at least one uppercase letter."
        continue
    fi
    
    if ! echo "$ADMIN_PASSWORD" | grep -q '[a-z]'; then
        echo "Password must contain at least one lowercase letter."
        continue
    fi
    
    if ! echo "$ADMIN_PASSWORD" | grep -q '[0-9]'; then
        echo "Password must contain at least one digit."
        continue
    fi
    
    if ! echo "$ADMIN_PASSWORD" | grep -qE '[^A-Za-z0-9]'; then
        echo "Password must contain at least one special character."
        continue
    fi
    
    break
done

echo ""
echo "Password accepted."

# Generate JWT secret key
echo "Generating security keys..."
JWT_SECRET=$(openssl rand -hex 32)

# Hash the password using Python
echo "Hashing password..."
PASSWORD_HASH=$(python3 -c "
import sys
sys.path.insert(0, '.')
from funkygibbon.auth.password import PasswordManager
pm = PasswordManager()
print(pm.hash_password('$ADMIN_PASSWORD'))
" 2>/dev/null || echo "")

if [ -z "$PASSWORD_HASH" ]; then
    echo "Error: Failed to hash password. Installing required dependencies..."
    pip3 install --user argon2-cffi
    
    PASSWORD_HASH=$(python3 -c "
import sys
sys.path.insert(0, '.')
from funkygibbon.auth.password import PasswordManager
pm = PasswordManager()
print(pm.hash_password('$ADMIN_PASSWORD'))
")
fi

# Optional: Configure network settings
echo ""
echo "Network Configuration"
echo "---------------------"
read -p "Enter server hostname (default: funkygibbon): " SERVER_NAME
SERVER_NAME=${SERVER_NAME:-funkygibbon}

read -p "Enter server port (default: 8000): " SERVER_PORT
SERVER_PORT=${SERVER_PORT:-8000}

read -p "Enable mDNS/Bonjour discovery? (Y/n): " -n 1 -r
echo
MDNS_ENABLED=true
if [[ $REPLY =~ ^[Nn]$ ]]; then
    MDNS_ENABLED=false
fi

# Create configuration file
echo "Creating configuration file..."
cat > "$CONFIG_DIR/config.json" <<EOF
{
    "auth": {
        "admin_password_hash": "$PASSWORD_HASH",
        "jwt_secret": "$JWT_SECRET",
        "guest_token_duration_hours": 24,
        "admin_token_duration_days": 7
    },
    "server": {
        "host": "0.0.0.0",
        "port": $SERVER_PORT,
        "hostname": "$SERVER_NAME",
        "mdns_enabled": $MDNS_ENABLED,
        "mdns_name": "$SERVER_NAME",
        "mdns_service": "_funkygibbon._tcp"
    },
    "database": {
        "url": "sqlite+aiosqlite:///funkygibbon.db"
    },
    "logging": {
        "level": "INFO",
        "file": "/var/log/funkygibbon/server.log"
    }
}
EOF

# Secure the configuration file
chmod 600 "$CONFIG_DIR/config.json"

# Create systemd service file
echo "Creating systemd service..."
sudo tee /etc/systemd/system/funkygibbon.service > /dev/null <<EOF
[Unit]
Description=FunkyGibbon Smart Home Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment="CONFIG_PATH=$CONFIG_DIR/config.json"
Environment="JWT_SECRET=$JWT_SECRET"
Environment="ADMIN_PASSWORD_HASH=$PASSWORD_HASH"
ExecStart=/usr/bin/python3 -m uvicorn funkygibbon.api.app:create_app --host 0.0.0.0 --port $SERVER_PORT
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create log directory
sudo mkdir -p /var/log/funkygibbon
sudo chown $USER:$USER /var/log/funkygibbon

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip3 install --user -r requirements.txt

# Install additional security dependencies
pip3 install --user argon2-cffi qrcode[pil] PyJWT

# Enable and start service
echo ""
echo "Enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable funkygibbon.service

echo ""
echo "==========================================="
echo "Installation Complete!"
echo "==========================================="
echo ""
echo "Server Details:"
echo "  - Address: $SERVER_NAME.local:$SERVER_PORT"
echo "  - Admin login: Use the password you set"
echo "  - Config file: $CONFIG_DIR/config.json"
echo "  - Service name: funkygibbon"
echo ""
echo "To start the server:"
echo "  sudo systemctl start funkygibbon"
echo ""
echo "To check server status:"
echo "  sudo systemctl status funkygibbon"
echo ""
echo "To view logs:"
echo "  journalctl -u funkygibbon -f"
echo ""
echo "iOS App Setup:"
echo "  1. The server will be discoverable as '$SERVER_NAME.local' on your network"
echo "  2. Use the admin password to log in from the iOS app"
echo "  3. Generate guest QR codes from the admin interface"
echo ""

read -p "Start the server now? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    sudo systemctl start funkygibbon
    echo "Server started successfully!"
    echo "Access the API at: http://$SERVER_NAME.local:$SERVER_PORT/docs"
fi