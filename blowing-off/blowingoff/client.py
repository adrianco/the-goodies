"""
Blowing-Off Client - Main Client Implementation

DEVELOPMENT CONTEXT:
Updated to use the Entity model and graph operations exclusively.
No longer maintains HomeKit-specific models - everything is an Entity.

FUNCTIONALITY:
- Client-server connection management
- Local SQLite database for offline operation
- Sync engine integration with Entity model
- MCP tool execution
- Graph operations for entity management
- Conflict resolution and retry logic
- Progress callbacks and observer pattern

PURPOSE:
Primary client interface for The Goodies smart home system. Provides
a clean API for sync operations, entity management, and MCP tool execution.

REVISION HISTORY:
- 2025-07-30: Updated to use Entity model exclusively
- 2025-07-28: Added MCP functionality and graph operations
- 2025-07-28: Improved database concurrency handling
"""

import os
import asyncio
import gc
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event, text
import json

from .models import Base
from .sync.engine import SyncEngine
from inbetweenies.sync import SyncResult
from .mcp import LocalMCPClient
from .graph import LocalGraphStorage, LocalGraphOperations
from .repositories import SyncMetadataRepository


class BlowingOffClient:
    """Python test client for The Goodies smart home system."""
    
    def __init__(self, db_path: str = "blowingoff.db"):
        """Initialize client with local SQLite database."""
        self.db_path = db_path
        self.engine = None
        self.session_factory = None
        self.sync_engine = None
        self._observers = []
        self._background_task = None
        
        # Initialize MCP and graph functionality
        self.graph_storage = LocalGraphStorage()
        self.graph_operations = LocalGraphOperations(self.graph_storage)
        self.mcp_client = LocalMCPClient(self.graph_storage)
        
    async def connect(self, server_url: str, auth_token: str, client_id: str = None):
        """Connect to server and initialize local database."""
        # Initialize database
        db_url = f"sqlite+aiosqlite:///{self.db_path}"
        self.engine = create_async_engine(
            db_url, 
            echo=False,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
            pool_pre_ping=True,  # Verify connections before use
            poolclass=None  # Disable pooling for SQLite
        )
        
        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
            # Enable SQLite optimizations for better concurrency
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))
            await conn.execute(text("PRAGMA cache_size=10000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            
        # Create session factory
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Initialize sync engine
        async with self.session_factory() as session:
            self.sync_engine = SyncEngine(session, server_url, auth_token, client_id)
            self.sync_engine.set_graph_operations(self.graph_operations)
            
    async def disconnect(self):
        """Disconnect and cleanup resources."""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
                
        if self.engine:
            await self.engine.dispose()
            gc.collect()
            
    async def sync(self) -> SyncResult:
        """Perform manual sync with server."""
        if not self.sync_engine:
            raise RuntimeError("Client not connected")
            
        async with self.session_factory() as session:
            self.sync_engine.session = session
            result = await self.sync_engine.sync()
            
        # Notify observers
        await self._notify_observers("sync_complete", result)
        
        return result
        
    async def start_background_sync(self, interval: int = 30):
        """Start background sync task."""
        async def sync_loop():
            while True:
                try:
                    await asyncio.sleep(interval)
                    await self.sync()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"Background sync error: {e}")
                    
        self._background_task = asyncio.create_task(sync_loop())
        
    def add_observer(self, callback: Callable):
        """Add observer for sync events."""
        self._observers.append(callback)
        
    def remove_observer(self, callback: Callable):
        """Remove observer."""
        if callback in self._observers:
            self._observers.remove(callback)
            
    async def _notify_observers(self, event: str, data: Any):
        """Notify all observers of an event."""
        for observer in self._observers:
            try:
                if asyncio.iscoroutinefunction(observer):
                    await observer(event, data)
                else:
                    observer(event, data)
            except Exception as e:
                print(f"Observer error: {e}")
                
    # MCP and Graph Operations
    
    async def execute_mcp_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute an MCP tool by name."""
        return await self.mcp_client.execute_tool(tool_name, **kwargs)
    
    def get_available_mcp_tools(self) -> List[str]:
        """Get list of available MCP tools."""
        return self.mcp_client.get_available_tools()
    
    def clear_graph_data(self):
        """Clear all graph data from storage."""
        if hasattr(self, 'graph_storage'):
            self.graph_storage.clear()
            
    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and statistics."""
        async with self.session_factory() as session:
            repo = SyncMetadataRepository(session)
            metadata = await repo.get_metadata(
                self.sync_engine.client_id if self.sync_engine else "default"
            )
            
            if not metadata:
                # Return default values if no metadata exists yet
                return {
                    "last_sync": None,
                    "last_success": None,
                    "total_syncs": 0,
                    "sync_failures": 0,
                    "total_conflicts": 0,
                    "sync_in_progress": False,
                    "last_error": None
                }
            
            return {
                "last_sync": metadata.last_sync_time.isoformat() if metadata.last_sync_time else None,
                "last_success": metadata.last_sync_success.isoformat() if metadata.last_sync_success else None,
                "total_syncs": metadata.total_syncs or 0,
                "sync_failures": metadata.sync_failures or 0,
                "total_conflicts": metadata.total_conflicts or 0,
                "sync_in_progress": bool(metadata.sync_in_progress),
                "last_error": metadata.last_sync_error
            }
    
    async def demo_mcp_functionality(self):
        """Demonstrate MCP functionality with sample data."""
        from inbetweenies.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType
        
        # Create sample entities
        print("\n📝 Creating sample entities...")
        
        # Create a home
        home = Entity(
            entity_type=EntityType.HOME,
            name="Demo Smart Home",
            content={
                "address": "456 Demo Street",
                "city": "Demo City"
            },
            source_type=SourceType.MANUAL
        )
        stored_home = await self.graph_operations.store_entity(home)
        
        # Create rooms
        living_room = Entity(
            entity_type=EntityType.ROOM,
            name="Living Room",
            content={"floor": "1st"},
            source_type=SourceType.MANUAL
        )
        kitchen = Entity(
            entity_type=EntityType.ROOM,
            name="Kitchen",
            content={"floor": "1st"},
            source_type=SourceType.MANUAL
        )
        
        stored_living = await self.graph_operations.store_entity(living_room)
        stored_kitchen = await self.graph_operations.store_entity(kitchen)
        
        # Create devices
        tv = Entity(
            entity_type=EntityType.DEVICE,
            name="Smart TV",
            content={
                "manufacturer": "Samsung",
                "model": "Q90",
                "capabilities": ["power", "volume", "input"]
            },
            source_type=SourceType.MANUAL
        )
        fridge = Entity(
            entity_type=EntityType.DEVICE,
            name="Smart Fridge",
            content={
                "manufacturer": "LG",
                "model": "InstaView",
                "capabilities": ["temperature", "door_status"]
            },
            source_type=SourceType.MANUAL
        )
        
        stored_tv = await self.graph_operations.store_entity(tv)
        stored_fridge = await self.graph_operations.store_entity(fridge)
        
        # Create relationships
        # Rooms in home
        await self.graph_operations.store_relationship(
            EntityRelationship(
                source_id=stored_living.id,
                target_id=stored_home.id,
                relationship_type=RelationshipType.LOCATED_IN,
                source_type=SourceType.MANUAL
            )
        )
        await self.graph_operations.store_relationship(
            EntityRelationship(
                source_id=stored_kitchen.id,
                target_id=stored_home.id,
                relationship_type=RelationshipType.LOCATED_IN,
                source_type=SourceType.MANUAL
            )
        )
        
        # Devices in rooms
        await self.graph_operations.store_relationship(
            EntityRelationship(
                source_id=stored_tv.id,
                target_id=stored_living.id,
                relationship_type=RelationshipType.LOCATED_IN,
                source_type=SourceType.MANUAL
            )
        )
        await self.graph_operations.store_relationship(
            EntityRelationship(
                source_id=stored_fridge.id,
                target_id=stored_kitchen.id,
                relationship_type=RelationshipType.LOCATED_IN,
                source_type=SourceType.MANUAL
            )
        )
        
        print("✅ Created demo entities and relationships")
        
        # Test MCP tools
        print("\n🔍 Testing MCP tools...")
        
        # Get devices in living room
        result = await self.execute_mcp_tool(
            "get_devices_in_room",
            room_id=stored_living.id
        )
        print(f"\nDevices in Living Room: {result['result']['count']}")
        
        # Search for devices
        result = await self.execute_mcp_tool(
            "search_entities",
            query="Smart",
            entity_types=[EntityType.DEVICE.value],
            limit=10
        )
        print(f"Found {result['result']['count']} smart devices")
        
        print("\n✅ MCP demo complete!")