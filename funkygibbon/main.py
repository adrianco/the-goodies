"""
FunkyGibbon - Main Entry Point

DEVELOPMENT CONTEXT:
Created in January 2024 as part of "The Goodies" smart home system initiative.
This represents a pivot from complex multi-tenancy to a simplified single-house
design after realizing most use cases only need single-family support.

FUNCTIONALITY:
- Bootstraps the FastAPI application server
- Configures uvicorn ASGI server with hot-reload for development
- Provides the main entry point for running the API server
- Loads configuration from environment/settings

PURPOSE:
Central entry point that developers use to start the FunkyGibbon backend.
This keeps server initialization logic separate from the API application
factory, following separation of concerns principles.

KNOWN ISSUES:
- Hot-reload can sometimes fail to detect changes in imported modules
- No graceful shutdown handling for background tasks yet
- Development server settings (reload=True) are hardcoded

REVISION HISTORY:
- 2024-01-15: Initial implementation (part of simplified single-house design)
- 2024-01-16: Added configuration loading from settings module
- 2024-01-17: Switched to factory pattern with create_app()

DEPENDENCIES:
- uvicorn: ASGI server for FastAPI
- .api.app: Application factory
- .config: Settings management

USAGE:
python -m funkygibbon.main
or
uvicorn funkygibbon.main:app --reload
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