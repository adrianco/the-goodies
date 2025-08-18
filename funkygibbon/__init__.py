"""
FunkyGibbon - Smart Home Knowledge Graph Backend

DEVELOPMENT CONTEXT:
Created in July 2025 as the Python backend for "The Goodies" smart home
system. FunkyGibbon is a simplified, single-house smart home server designed
to replace complex multi-tenant systems with a focused solution for individual
families. Named after the British comedy series "The Goodies" along with its
companion projects WildThing (Swift client) and Blowing-Off (Python CLI).

FUNCTIONALITY:
- FastAPI-based REST API server for smart home entities
- SQLite database with async SQLAlchemy ORM
- Bidirectional sync with last-write-wins conflict resolution
- Support for houses, rooms, devices, users, and entity states
- Inbetweenies protocol compatibility for third-party integration
- Optimized for ~300 entities with <1s response times
- JSON-based flexible schema for device states and settings

PURPOSE:
Provides a lightweight, fast, and reliable backend for smart home systems
that prioritizes simplicity and single-family use cases over complex
multi-tenancy features. Perfect for homeowners who want local control
of their smart home without cloud dependencies.

KNOWN ISSUES:
- No built-in authentication system (relies on reverse proxy)
- Limited to single-house deployments by design
- No real-time WebSocket support (polling required)
- SQLite limitations for concurrent writes
- No built-in backup/restore functionality

REVISION HISTORY:
- 2025-07-28: Initial package structure and core models
- 2025-07-28: Added repository pattern and sync protocol
- 2025-07-28: Implemented FastAPI application and routers
- 2025-07-28: Added Inbetweenies protocol support
- 2025-07-28: Performance optimizations and denormalization

DEPENDENCIES:
- Python 3.11+ for modern async support
- FastAPI for web framework
- SQLAlchemy 2.0+ for async ORM
- Pydantic for data validation
- uvicorn for ASGI server

USAGE:
# Run the server:
python -m funkygibbon.main

# Or programmatically:
from funkygibbon.api.app import create_app
from funkygibbon.config import settings
app = create_app()

# Access at http://localhost:8000
# API docs at http://localhost:8000/docs
"""

__version__ = "0.1.0"
__author__ = "The Goodies Team"
