"""
Main entry point for FunkyGibbon API server.
"""

import uvicorn

from .api.app import create_app
from .config import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "funkygibbon.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )