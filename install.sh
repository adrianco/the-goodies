#!/bin/bash
# install.sh - FunkyGibbon Smart Home Server Setup

echo "╔══════════════════════════════════════════════════╗"
echo "║     FunkyGibbon Smart Home Server Setup          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Check if running from project root
if [ ! -f "funkygibbon/populate_graph_db.py" ]; then
    echo "Error: Please run this script from the project root directory"
    echo "Usage: ./install.sh"
    exit 1
fi

# Function to generate secure random string
generate_secret() {
    if command -v openssl &> /dev/null; then
        openssl rand -hex 32
    else
        # Fallback to /dev/urandom if openssl not available
        head -c 32 /dev/urandom | base64 | tr -d "=+/" | cut -c1-32
    fi
}

# Check for development mode
if [ "$1" == "--dev" ] || [ "$1" == "-d" ]; then
    echo "🚧 Development Mode Setup"
    echo "========================"
    echo ""
    echo "Setting up with default 'admin' password for development..."
    
    export ADMIN_PASSWORD_HASH=""
    export JWT_SECRET="development-secret"
    
    echo "✅ Development environment configured"
    echo ""
    echo "Default credentials:"
    echo "  Username: admin"
    echo "  Password: admin"
    echo ""
else
    echo "🔒 Production Setup"
    echo "==================="
    echo ""
    
    # Prompt for admin password
    while true; do
        read -s -p "Enter admin password: " ADMIN_PASSWORD
        echo ""
        read -s -p "Confirm admin password: " ADMIN_PASSWORD_CONFIRM
        echo ""
        
        if [ "$ADMIN_PASSWORD" != "$ADMIN_PASSWORD_CONFIRM" ]; then
            echo "❌ Passwords do not match. Please try again."
            echo ""
        else
            # Check password strength
            if [ ${#ADMIN_PASSWORD} -lt 8 ]; then
                echo "❌ Password must be at least 8 characters long."
                echo ""
            else
                break
            fi
        fi
    done
    
    echo ""
    echo "Generating secure configuration..."
    
    # Generate password hash
    ADMIN_PASSWORD_HASH=$(python3 -c "
import sys
sys.path.insert(0, '.')
from funkygibbon.auth.password import PasswordManager
pm = PasswordManager()
print(pm.hash_password('$ADMIN_PASSWORD'))
" 2>/dev/null)
    
    if [ $? -ne 0 ]; then
        echo "❌ Error: Failed to hash password. Make sure dependencies are installed."
        echo "Run: pip install -r funkygibbon/requirements.txt"
        exit 1
    fi
    
    # Generate JWT secret
    JWT_SECRET=$(generate_secret)
    
    export ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD_HASH"
    export JWT_SECRET="$JWT_SECRET"
    
    echo "✅ Security configuration generated"
fi

# Set Python path
export PYTHONPATH="$(pwd):$PYTHONPATH"

# Create startup script
cat > start_funkygibbon.sh << 'EOF'
#!/bin/bash
# Auto-generated startup script for FunkyGibbon

# Set environment variables
EOF

if [ "$1" == "--dev" ] || [ "$1" == "-d" ]; then
    cat >> start_funkygibbon.sh << 'EOF'
export ADMIN_PASSWORD_HASH=""
export JWT_SECRET="development-secret"
EOF
else
    cat >> start_funkygibbon.sh << EOF
export ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD_HASH"
export JWT_SECRET="$JWT_SECRET"
EOF
fi

cat >> start_funkygibbon.sh << 'EOF'
export PYTHONPATH="$(dirname "$0"):$PYTHONPATH"

# Start the server
echo "Starting FunkyGibbon server..."
python -m funkygibbon
EOF

chmod +x start_funkygibbon.sh

echo ""
echo "📦 Installing Dependencies"
echo "========================="

# Install dependencies
cd funkygibbon
pip install -r requirements.txt > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ FunkyGibbon dependencies installed"
else
    echo "⚠️  Warning: Some dependencies may have failed to install"
fi
cd ..

cd oook
pip install -e . > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Oook CLI installed"
else
    echo "⚠️  Warning: Oook CLI installation may have failed"
fi
cd ..

echo ""
echo "🗃️  Populating Test Database"
echo "============================"

cd funkygibbon
python populate_graph_db.py > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Database populated with test data"
else
    echo "⚠️  Warning: Database population may have failed"
fi
cd ..

echo ""
echo "✨ Installation Complete!"
echo "========================"
echo ""
echo "To start the server:"
echo "  ./start_funkygibbon.sh"
echo ""
echo "To test the installation:"
echo "  1. Start the server in one terminal: ./start_funkygibbon.sh"
echo "  2. In another terminal: oook stats"
echo ""

if [ "$1" != "--dev" ] && [ "$1" != "-d" ]; then
    echo "🔐 Security Notes:"
    echo "  - Your admin password has been securely hashed"
    echo "  - JWT secret has been generated"
    echo "  - Configuration is stored in start_funkygibbon.sh"
    echo "  - Keep this file secure and do not commit it to git"
    echo ""
fi

echo "Server will be available at:"
echo "  Local: http://localhost:8000"
echo "  mDNS: http://funkygibbon.local:8000"
echo ""
echo "Happy automating! 🏠✨"