#!/usr/bin/env python3
"""Simple server runner for testing."""

import sys
import os
from pathlib import Path

# Add parent directory to path so imports work
parent_dir = Path(__file__).parent
sys.path.insert(0, str(parent_dir))
os.chdir(parent_dir)

# Direct imports to avoid the relative import issue
from database import engine, Base, get_db
from config import settings

# Import and create the app directly
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create app
app = FastAPI(title="FunkyGibbon API", version="0.1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

# Import and add routers
from api.routers import house, room, device, user, sync

app.include_router(house.router, prefix="/api/v1", tags=["houses"])
app.include_router(room.router, prefix="/api/v1", tags=["rooms"])
app.include_router(device.router, prefix="/api/v1", tags=["devices"])
app.include_router(user.router, prefix="/api/v1", tags=["users"])
app.include_router(sync.router, prefix="/api/v1", tags=["sync"])

# Ensure database is created
import asyncio

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Run the initialization
asyncio.run(init_db())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="error"  # Quiet for testing
    )