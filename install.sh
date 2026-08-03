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

# Detect Python command
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Error: Python 3 is not installed or not in PATH"
    echo "Please install Python 3.11 or higher"
    exit 1
fi

echo "✓ Using Python: $PYTHON_CMD"
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
echo "  Python version: $PYTHON_VERSION"

# Create virtual environment
echo ""
echo "🔧 Setting up virtual environment..."
if [ -d "venv" ]; then
    echo "  Virtual environment already exists"
else
    $PYTHON_CMD -m venv venv
    if [ $? -eq 0 ]; then
        echo "✅ Virtual environment created"
    else
        echo "❌ Error: Failed to create virtual environment"
        echo "Make sure python3-venv is installed"
        exit 1
    fi
fi

# Activate virtual environment
source venv/bin/activate
if [ $? -eq 0 ]; then
    echo "✅ Virtual environment activated"
    # Update Python command to use venv
    PYTHON_CMD="python"
else
    echo "❌ Error: Failed to activate virtual environment"
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
    ADMIN_PASSWORD_HASH=$($PYTHON_CMD -c "
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

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✓ Virtual environment activated"
else
    echo "❌ Error: Virtual environment not found"
    echo "Please run ./install.sh first"
    exit 1
fi

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Start the server
echo "Starting FunkyGibbon server..."
python -m funkygibbon
EOF

chmod +x start_funkygibbon.sh

echo ""
echo "📦 Installing Dependencies"
echo "========================="

# Upgrade pip and install wheel first
echo "Upgrading pip and installing wheel..."
$PYTHON_CMD -m pip install --upgrade pip setuptools wheel > /dev/null 2>&1

# One workspace, one install step (ADR-010 §6). The root pyproject.toml maps
# funkygibbon, inbetweenies, blowingoff and oook into a single editable install
# and pulls the whole dependency set with them -- replacing the old
# `cd <component> && pip install -e .` loop, which silently skipped components
# and had to be kept in step with funkygibbon/requirements.txt by hand.
echo "Installing the workspace (funkygibbon, inbetweenies, blowing-off, oook)..."
pip install -e .
if [ $? -eq 0 ]; then
    echo "✅ Workspace installed"
else
    echo "❌ Error: Workspace installation failed"
    echo "   Re-run 'pip install -e .' from the project root to see the failure."
    exit 1
fi

echo ""
echo "🗃️  Populating Test Database"
echo "============================"

# Run from project root so database is created in the right place
$PYTHON_CMD funkygibbon/populate_graph_db.py
if [ $? -eq 0 ]; then
    echo "✅ Database populated with test data"
    if [ -f "funkygibbon.db" ]; then
        echo "   Database created at: ./funkygibbon.db"
    fi
else
    echo "⚠️  Warning: Database population may have failed"
    echo "   (This is normal if dependencies aren't installed yet)"
fi

echo ""
echo "✨ Installation Complete!"
echo "========================"
echo ""
echo "Virtual environment created in: ./venv/"
echo ""
echo "To start the server:"
echo "  ./start_funkygibbon.sh"
echo ""
echo "To test the installation:"
echo "  1. Start the server in one terminal: ./start_funkygibbon.sh"
echo "  2. In another terminal:"
echo "     source venv/bin/activate"
echo "     oook stats"
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