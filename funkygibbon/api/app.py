"""
FastAPI application factory.
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