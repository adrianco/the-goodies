"""
FunkyGibbon - FastAPI Application Factory

DEVELOPMENT CONTEXT:
Created in January 2024 as the main API application factory following
FastAPI best practices. This module bootstraps the REST API server that
provides endpoints for the smart home knowledge graph system.

FUNCTIONALITY:
- Application factory pattern for testability and configuration
- Lifespan context manager for startup/shutdown events
- Database initialization on startup
- CORS middleware configuration for cross-origin requests
- Router registration for all entity endpoints
- Health and status endpoints for monitoring
- API versioning through URL prefix

PURPOSE:
Central configuration point for the FastAPI application. This factory
pattern allows easy testing with different configurations and ensures
consistent setup across development, testing, and production environments.

KNOWN ISSUES:
- CORS allows all origins (*) which is insecure for production
- No authentication middleware configured yet
- No rate limiting or request throttling
- Missing OpenAPI customization for better docs
- No structured logging configuration
- Shutdown doesn't close database connections explicitly

REVISION HISTORY:
- 2024-01-15: Initial FastAPI setup with basic routers
- 2024-01-16: Added lifespan events for database initialization
- 2024-01-17: Added CORS middleware for frontend development
- 2024-01-18: Added health check endpoint
- 2024-01-19: Moved to factory pattern for better testing

DEPENDENCIES:
- fastapi: Modern web framework for building APIs
- ..config: Application settings
- ..database: Database initialization
- .routers: All API endpoint routers

USAGE:
# Create application instance:
app = create_app()

# Run with uvicorn:
uvicorn.run(app, host="0.0.0.0", port=8000)

# For testing:
from fastapi.testclient import TestClient
client = TestClient(create_app())
response = client.get("/health")
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import settings
from ..database import init_db
from .routers import device, house, room, sync, user


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan events."""
    # Startup
    await init_db()
    print("Database initialized")
    yield
    # Shutdown
    print("Shutting down")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="FunkyGibbon",
        description="Simplified smart home knowledge graph API",
        version="0.1.0",
        lifespan=lifespan
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure properly for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(house.router, prefix=f"{settings.api_prefix}/houses", tags=["houses"])
    app.include_router(room.router, prefix=f"{settings.api_prefix}/rooms", tags=["rooms"])
    app.include_router(device.router, prefix=f"{settings.api_prefix}/devices", tags=["devices"])
    app.include_router(user.router, prefix=f"{settings.api_prefix}/users", tags=["users"])
    app.include_router(sync.router, prefix=f"{settings.api_prefix}/sync", tags=["sync"])
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "FunkyGibbon",
            "version": "0.1.0",
            "status": "ready"
        }
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy"}
    
    return app