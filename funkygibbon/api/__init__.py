"""
FunkyGibbon API Layer

FastAPI endpoints for entity management.
"""

from .app import create_app
from .routers import auth, mcp, sync_metadata

__all__ = [
    "create_app",
    "auth",
    "mcp",
    "sync_metadata",
]
