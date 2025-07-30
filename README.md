<!--
The Goodies - Project Root Documentation

DEVELOPMENT CONTEXT:
Created as the main entry point for The Goodies smart home knowledge graph
system. Originally envisioned as an enterprise-scale distributed system,
later simplified to a practical single-house deployment.

DOCUMENT PURPOSE:
Provides project overview, quick start guide, and navigation to all other
documentation. First point of contact for new developers and users.

REVISION HISTORY:
- 2024-01-10: Initial creation with ambitious multi-house vision
- 2024-01-15: Simplified to single-house, added FunkyGibbon details
- 2024-01-15: Added Blowing-Off client documentation
- 2024-01-15: Updated with comprehensive documentation links

NAMING:
Named after the BBC TV comedy show "The Goodies" who had some hit singles
in the 1970s, continuing the Python (Monty Python) naming tradition.
-->

# The Goodies

## Smart Home Knowledge Graph System

A simplified smart home system designed for single-house deployments with SQLite storage and last-write-wins conflict resolution. Built with Python (FunkyGibbon backend) and Swift (WildThing iOS/macOS) components.

### 🚀 Quick Start

#### 1. Start the Backend Server

```bash
# Navigate to project root
cd /workspaces/the-goodies

# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
cd funkygibbon
pip install -r requirements.txt
cd ..

# Add inbetweenies to Python path
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH

# Populate the database with test data
python funkygibbon/populate_db.py

# Start the server (from project root)
python -m funkygibbon

# API will be available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

#### 2. Install and Use the Client

```bash
# Make sure virtual environment is activated
# If not: source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install the Python test client
cd blowing-off
pip install -e .
cd ..

# Connect to server
blowing-off connect --server-url http://localhost:8000 --auth-token test-token

# Sync to get existing data from server
blowing-off sync

# View synchronized data
blowing-off home show
blowing-off device list
```

For detailed testing instructions, see [Human Testing Guide](plans/HUMAN_TESTING.md).

### 📋 Features

- **Simple Scale**: Designed for 1 house, ~300 entities, 3-5 users
- **SQLite Storage**: Single file database with optimizations
- **Last-Write-Wins**: Simple timestamp-based conflict resolution
- **REST API**: FastAPI-based endpoints for all entities
- **Sync Protocol**: Inbetweenies bidirectional synchronization
- **Offline Support**: Client works offline with automatic sync
- **Type Safety**: Full Python 3.11+ type hints
- **Performance**: <1s for 300 entity operations

### 🏗️ Architecture

The system consists of four main components:

1. **FunkyGibbon** (Python Backend) - REST API server with SQLite storage
2. **Inbetweenies** (Shared Models) - HomeKit-compatible data models shared between server and client
3. **Blowing-Off** (Python Client) - Test client with Inbetweenies sync protocol
4. **WildThing** (Swift Package) - iOS/macOS client library (in development)

### 📚 Documentation

- **[Architecture Overview](architecture/SYSTEM_ARCHITECTURE.md)** - System design and components
- **[API Documentation](architecture/api/MCP_TOOLS_API.md)** - REST API endpoints
- **[Database Schema](architecture/database/SCHEMA_DESIGN_DECISIONS.md)** - SQLite schema design

#### Component Documentation

- **[FunkyGibbon Backend](funkygibbon/README.md)** - Python backend implementation
- **[FunkyGibbon Tests](funkygibbon/TEST_SUMMARY.md)** - Test suite documentation
- **[Blowing-Off Client](blowing-off/README.md)** - Python test client implementation
- **[Inbetweenies Protocol](plans/inbetweenies-protocol.md)** - Synchronization protocol
- **[Implementation Summary](funkygibbon/IMPLEMENTATION_SUMMARY.md)** - Development progress

#### Planning & Development

- **[Plans Directory](plans/README.md)** - Development plans and milestones
- **[Simplified Requirements](plans/simplified-requirements.md)** - Current scope and constraints
- **[Deployment Guide](plans/deployment-plan.md)** - Installation and deployment
- **[Human Testing Guide](plans/HUMAN_TESTING.md)** - Step-by-step testing instructions

### 🧪 Testing

The project includes comprehensive tests:

```bash
cd funkygibbon
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=funkygibbon --cov-report=html
```

### 🔗 Related Projects

- iOS Frontend: [c11s-house-ios](https://github.com/adrianco/c11s-house-ios)
- Original Prototype: [consciousness](https://github.com/adrianco/consciousness) (deprecated)

### 📝 Notes

Based on initial discussions with Claude, the system has been simplified from an enterprise-scale distributed system to a practical single-house solution. The [archived plans](plans/archive/) contain the original ambitious scope.

Naming scheme based on BBC TV comedy show The Goodies who had some "hit singles" in the 1970s, since Python is a reference to Monty Python.
