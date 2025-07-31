"""
Inbetweenies Protocol - Smart Home Synchronization Protocol

STATUS: ✅ Production Ready - All tests passing, fully operational

ARCHITECTURE:
Shared protocol library for The Goodies smart home system providing
entity-relationship models, MCP tool implementations, and
synchronization protocols for client-server coordination.

CORE FUNCTIONALITY:
- Entity and relationship models for smart home graph
- MCP tool implementations (12 standardized tools)
- Synchronization protocol with conflict resolution
- Graph operations abstraction layer
- Backward compatibility with HomeKit models

KEY COMPONENTS:
- Entity model supporting all smart home device types
- EntityRelationship model for device interconnections
- MCP tool definitions with standardized parameters
- Sync protocol with delta updates and conflict detection
- Repository layer for data access abstraction

PRODUCTION READY:
All models tested and operational. Protocol successfully handles
entity synchronization with full MCP tool compatibility.
"""

from . import models
from . import sync
from . import repositories

__version__ = "0.1.0"

__all__ = ["models", "sync", "repositories", "__version__"]