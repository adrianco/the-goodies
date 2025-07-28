# The Goodies

## Smart Home Knowledge Graph System

A simplified smart home system designed for single-house deployments with SQLite storage and last-write-wins conflict resolution. Built with Python (FunkyGibbon backend) and Swift (WildThing iOS/macOS) components.

### 🚀 Quick Start

```bash
# Install and run the Python backend
cd funkygibbon
pip install -r requirements.txt
python -m funkygibbon.main

# API will be available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### 📋 Features

- **Simple Scale**: Designed for 1 house, ~300 entities, 3-5 users
- **SQLite Storage**: Single file database with optimizations
- **Last-Write-Wins**: Simple timestamp-based conflict resolution
- **REST API**: FastAPI-based endpoints for all entities
- **Type Safety**: Full Python 3.11+ type hints
- **Performance**: <1s for 300 entity operations

### 🏗️ Architecture

The system consists of two main components:

1. **FunkyGibbon** (Python Backend) - REST API server with SQLite storage
2. **WildThing** (Swift Package) - iOS/macOS client library (in development)

### 📚 Documentation

- **[Architecture Overview](architecture/SYSTEM_ARCHITECTURE.md)** - System design and components
- **[API Documentation](architecture/api/MCP_TOOLS_API.md)** - REST API endpoints
- **[Database Schema](architecture/database/SCHEMA_DESIGN_DECISIONS.md)** - SQLite schema design
- **[Claude Configuration](docs/CLAUDE_CONFIGURATION.md)** - Claude Code setup and commands

#### Component Documentation

- **[FunkyGibbon Backend](funkygibbon/README.md)** - Python backend implementation
- **[FunkyGibbon Tests](funkygibbon/TEST_SUMMARY.md)** - Test suite documentation
- **[Implementation Summary](funkygibbon/IMPLEMENTATION_SUMMARY.md)** - Development progress

#### Planning & Development

- **[Plans Directory](plans/README.md)** - Development plans and milestones
- **[Simplified Requirements](plans/simplified-requirements.md)** - Current scope and constraints
- **[Deployment Guide](plans/deployment-plan.md)** - Installation and deployment

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
