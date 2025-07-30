"""
Blowing-Off Client - Main Client Implementation

DEVELOPMENT CONTEXT:
Created as part of The Goodies smart home ecosystem development in July 2025.
This is the Python test client that implements the Inbetweenies protocol for
synchronizing smart home data between the cloud and local databases. This client
serves as the reference implementation that will guide the Swift/WildThing client
development for Apple platforms. Updated to use HomeKit-compatible models from
the shared Inbetweenies package.

FUNCTIONALITY:
- Manages local SQLite database for offline-first operation
- Implements bidirectional sync with cloud server using Inbetweenies protocol
- Provides async API for CRUD operations on homes, rooms, and accessories
- Handles conflict resolution and sync failure recovery
- Enables background sync with configurable intervals
- Works with shared HomeKit models and ClientSyncTracking for local changes

PURPOSE:
This client enables:
- Offline-first smart home control (works without internet)
- Seamless sync when connectivity is restored
- Multiple client synchronization (mobile, web, etc.)
- Testing and validation of the Inbetweenies protocol
- Reference for Swift/WildThing implementation

KNOWN ISSUES:
- Single home assumption (multi-home support planned)
- Basic conflict resolution (last-write-wins)
- No encryption for local database yet
- Background sync task needs better error recovery
- No automatic cleanup of old sync tracking records

REVISION HISTORY:
- 2025-07-28: Initial implementation (Python test client for Inbetweenies protocol)
- 2025-07-28: Added background sync support
- 2025-07-28: Implemented observer pattern for change notifications
- 2025-07-29: Migrated to shared Inbetweenies models
- 2025-07-29: Updated entity names (House→Home, Device→Accessory)
- 2025-07-29: Implemented ClientSyncTracking for local change detection
- 2025-07-29: Repository operations now automatically track sync status

DEPENDENCIES:
- SQLAlchemy with async support for database operations 
- aiosqlite for async SQLite operations
- Custom sync engine implementing Inbetweenies protocol
- Repository pattern for data access abstraction
- inbetweenies.models for shared HomeKit models
- ClientSyncTracking model for local change detection

USAGE:
    client = BlowingOffClient("local.db")
    await client.connect("https://api.thegoodies.app", auth_token)
    await client.start_background_sync(interval=30)
    
    # Get accessories in a room
    accessories = await client.get_accessories(room_id="living-room-1")
    
    # Update accessory state
    await client.update_accessory_state(
        accessory_id="light-1",
        state={"on": True, "brightness": 80}
    )
"""

import asyncio
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event, text
import json

from .models import Base
from .sync.engine import SyncEngine
from .sync.state import SyncResult
from ..mcp import LocalMCPClient
from ..graph import LocalGraphStorage
from .repositories import (
    ClientHomeRepository,
    ClientRoomRepository,
    ClientAccessoryRepository,
    ClientUserRepository,
    # ClientEntityStateRepository,  # Removed for HomeKit focus
    # ClientEventRepository         # Removed for HomeKit focus
)


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
            # Force garbage collection to ensure all connections are closed
            import gc
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
        
    async def get_home(self, home_id: str = None) -> Optional[Dict[str, Any]]:
        """Get home data by ID, or the first home if no ID specified."""
        async with self.session_factory() as session:
            repo = ClientHomeRepository(session)
            
            if home_id:
                home = await repo.get(home_id)
                if home:
                    return {
                        "id": home.id,
                        "name": home.name,
                        "is_primary": home.is_primary
                    }
            else:
                homes = await repo.get_all()
                if homes:
                    home = homes[0]  # Assume single home
                    return {
                        "id": home.id,
                        "name": home.name,
                        "is_primary": home.is_primary
                    }
        return None
    
    async def get_homes(self) -> List[Dict[str, Any]]:
        """Get all homes."""
        async with self.session_factory() as session:
            repo = ClientHomeRepository(session)
            homes = await repo.get_all()
            return [
                {
                    "id": home.id,
                    "name": home.name,
                    "is_primary": home.is_primary
                }
                for home in homes
            ]
        
    async def get_rooms(self, home_id: str = None) -> List[Dict[str, Any]]:
        """Get all rooms."""
        async with self.session_factory() as session:
            repo = ClientRoomRepository(session)
            if home_id:
                rooms = await repo.get_by_home(home_id)
            else:
                rooms = await repo.get_all()
                
            return [
                {
                    "id": room.id,
                    "home_id": room.home_id,
                    "name": room.name
                }
                for room in rooms
            ]
            
    async def get_accessories(self, room_id: str = None) -> List[Dict[str, Any]]:
        """Get accessories, optionally filtered by room."""
        async with self.session_factory() as session:
            repo = ClientAccessoryRepository(session)
            if room_id:
                accessories = await repo.get_by_room(room_id)
            else:
                accessories = await repo.get_all()
                
            return [
                {
                    "id": accessory.id,
                    "home_id": accessory.home_id,
                    "name": accessory.name,
                    "manufacturer": accessory.manufacturer,
                    "model": accessory.model,
                    "serial_number": accessory.serial_number,
                    "firmware_version": accessory.firmware_version,
                    "is_reachable": accessory.is_reachable,
                    "is_blocked": accessory.is_blocked,
                    "is_bridge": accessory.is_bridge
                }
                for accessory in accessories
            ]
            
    async def get_accessory_state(self, accessory_id: str) -> Optional[Dict[str, Any]]:
        """Get current state of an accessory."""
        # TODO: Implement with HomeKit characteristic tracking
        return None
        
    async def update_accessory_state(self, accessory_id: str, state: Dict[str, Any], attributes: Dict[str, Any] = None):
        """Update accessory state."""
        # TODO: Implement with HomeKit characteristic updates
        # For now, just notify observers
        await self._notify_observers("state_change", {
            "accessory_id": accessory_id,
            "state": state,
            "attributes": attributes
        })
        
    async def create_home(self, name: str, **kwargs) -> str:
        """Create a new home."""
        async with self.session_factory() as session:
            repo = ClientHomeRepository(session)
            home = await repo.create(
                id=f"home-{datetime.now().timestamp()}",
                name=name,
                is_primary=kwargs.get("is_primary", False)
            )
            await session.commit()
            
        # Notify observers
        await self._notify_observers("home_created", {"home_id": home.id})
        
        return home.id
        
    async def create_room(self, home_id: str, name: str, **kwargs) -> str:
        """Create a new room."""
        async with self.session_factory() as session:
            repo = ClientRoomRepository(session)
            room = await repo.create(
                id=f"room-{datetime.now().timestamp()}",
                home_id=home_id,
                name=name
            )
            await session.commit()
            
        # Notify observers
        await self._notify_observers("room_created", {"room_id": room.id})
        
        return room.id
        
    async def create_accessory(self, room_id: str, name: str, accessory_type: str, **kwargs) -> str:
        """Create a new accessory."""
        async with self.session_factory() as session:
            repo = ClientAccessoryRepository(session)
            room_repo = ClientRoomRepository(session)
            home_repo = ClientHomeRepository(session)
            
            # Get room to find home_id
            room = await room_repo.get(room_id)
            if not room:
                raise ValueError(f"Room {room_id} not found")
            
            # Get home
            home = await home_repo.get(room.home_id)
            if not home:
                raise ValueError(f"Home {room.home_id} not found")
            
            accessory = await repo.create(
                id=f"accessory-{datetime.now().timestamp()}",
                home_id=room.home_id,
                name=name,
                manufacturer=kwargs.get("manufacturer"),
                model=kwargs.get("model"),
                serial_number=kwargs.get("serial_number", f"SN-{datetime.now().timestamp()}"),
                firmware_version=kwargs.get("firmware_version", "1.0.0"),
                is_reachable=kwargs.get("is_reachable", True),
                is_blocked=kwargs.get("is_blocked", False),
                is_bridge=kwargs.get("is_bridge", False)
            )
            await session.commit()
            
        # Notify observers
        await self._notify_observers("accessory_created", {"accessory_id": accessory.id})
        
        return accessory.id
        
    async def observe_changes(self, callback: Callable):
        """Register observer for changes."""
        self._observers.append(callback)
        
    async def _notify_observers(self, event_type: str, data: Any):
        """Notify all observers of changes."""
        for observer in self._observers:
            try:
                await observer(event_type, data)
            except Exception as e:
                print(f"Observer error: {e}")
                
    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status."""
        async with self.session_factory() as session:
            from .repositories.sync_metadata import SyncMetadataRepository
            repo = SyncMetadataRepository(session)
            
            metadata = await repo.get_by_client(self.sync_engine.client_id if self.sync_engine else "")
            if metadata:
                return {
                    "last_sync": metadata.last_sync_time.isoformat() if metadata.last_sync_time else None,
                    "last_success": metadata.last_sync_success.isoformat() if metadata.last_sync_success else None,
                    "sync_failures": metadata.sync_failures,
                    "total_syncs": metadata.total_syncs,
                    "total_conflicts": metadata.total_conflicts,
                    "sync_in_progress": bool(metadata.sync_in_progress),
                    "last_error": metadata.last_sync_error
                }
                
        return {
            "last_sync": None,
            "last_success": None,
            "sync_failures": 0,
            "total_syncs": 0,
            "total_conflicts": 0,
            "sync_in_progress": False,
            "last_error": None
        }
    
    # MCP and Graph Operations
    
    async def execute_mcp_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute an MCP tool locally using graph data.
        
        Args:
            tool_name: Name of the MCP tool to execute
            **kwargs: Tool arguments
            
        Returns:
            Tool execution result
        """
        return await self.mcp_client.execute_tool(tool_name, **kwargs)
    
    def get_available_mcp_tools(self) -> List[str]:
        """Get list of available MCP tools"""
        return self.mcp_client.get_available_tools()
    
    async def sync_graph_from_homekit(self):
        """
        Sync graph data from HomeKit data.
        
        This converts HomeKit entities (homes, rooms, accessories) to
        graph entities and relationships for use with MCP tools.
        """
        from inbetweenies.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType
        
        async with self.session_factory() as session:
            # Get all homes
            home_repo = ClientHomeRepository(session)
            homes = await home_repo.get_all()
            
            entities = []
            relationships = []
            
            for home in homes:
                # Create home entity
                home_entity = Entity(
                    id=home.id,
                    version=Entity.create_version("homekit-sync"),
                    entity_type=EntityType.BUILDING,
                    name=home.name,
                    content={"homekit_id": home.id},
                    source_type=SourceType.HOMEKIT,
                    user_id="homekit-sync",
                    parent_versions=[]
                )
                entities.append(home_entity)
                
                # Get rooms
                room_repo = ClientRoomRepository(session)
                rooms = await room_repo.get_by_home(home.id)
                
                for room in rooms:
                    # Create room entity
                    room_entity = Entity(
                        id=room.id,
                        version=Entity.create_version("homekit-sync"),
                        entity_type=EntityType.ROOM,
                        name=room.name,
                        content={"homekit_id": room.id},
                        source_type=SourceType.HOMEKIT,
                        user_id="homekit-sync",
                        parent_versions=[]
                    )
                    entities.append(room_entity)
                    
                    # Create relationship: room -> home
                    rel = EntityRelationship(
                        id=f"{room.id}-in-{home.id}",
                        from_entity_id=room.id,
                        from_entity_version=room_entity.version,
                        to_entity_id=home.id,
                        to_entity_version=home_entity.version,
                        relationship_type=RelationshipType.LOCATED_IN,
                        properties={},
                        user_id="homekit-sync"
                    )
                    relationships.append(rel)
                
                # Get accessories
                accessory_repo = ClientAccessoryRepository(session)
                accessories = await accessory_repo.get_by_home(home.id)
                
                for accessory in accessories:
                    # Create device entity
                    device_entity = Entity(
                        id=accessory.id,
                        version=Entity.create_version("homekit-sync"),
                        entity_type=EntityType.DEVICE,
                        name=accessory.name,
                        content={
                            "homekit_id": accessory.id,
                            "model": accessory.model,
                            "manufacturer": accessory.manufacturer,
                            "firmware_version": accessory.firmware_version,
                            "capabilities": ["homekit"]
                        },
                        source_type=SourceType.HOMEKIT,
                        user_id="homekit-sync",
                        parent_versions=[]
                    )
                    entities.append(device_entity)
                    
                    # Create relationship: device -> room (if assigned)
                    if accessory.room_id:
                        rel = EntityRelationship(
                            id=f"{accessory.id}-in-{accessory.room_id}",
                            from_entity_id=accessory.id,
                            from_entity_version=device_entity.version,
                            to_entity_id=accessory.room_id,
                            to_entity_version=Entity.create_version("homekit-sync"),
                            relationship_type=RelationshipType.LOCATED_IN,
                            properties={},
                            user_id="homekit-sync"
                        )
                        relationships.append(rel)
        
        # Sync to local graph storage
        await self.mcp_client.sync_with_server({
            "entities": entities,
            "relationships": relationships
        })
        
        return len(entities), len(relationships)
    
    async def demo_mcp_functionality(self):
        """Demonstrate MCP functionality with local data"""
        await self.mcp_client.demo_local_functionality()
    
    def clear_graph_data(self):
        """Clear all local graph data"""
        self.mcp_client.clear_local_data()