"""
Blowing-Off Client - Main Client Implementation

DEVELOPMENT CONTEXT:
Created as part of The Goodies smart home ecosystem development in January 2024.
This is the Python test client that implements the Inbetweenies protocol for
synchronizing smart home data between the cloud and local databases. This client
serves as the reference implementation that will guide the Swift/WildThing client
development for Apple platforms.

FUNCTIONALITY:
- Manages local SQLite database for offline-first operation
- Implements bidirectional sync with cloud server using Inbetweenies protocol
- Provides async API for CRUD operations on houses, rooms, and devices
- Supports real-time state updates and change notifications
- Handles conflict resolution and sync failure recovery
- Enables background sync with configurable intervals

PURPOSE:
This client enables:
- Offline-first smart home control (works without internet)
- Seamless sync when connectivity is restored
- Multiple client synchronization (mobile, web, etc.)
- Testing and validation of the Inbetweenies protocol
- Reference for Swift/WildThing implementation

KNOWN ISSUES:
- Single house assumption (multi-house support planned)
- Basic conflict resolution (last-write-wins)
- No encryption for local database yet
- Background sync task needs better error recovery

REVISION HISTORY:
- 2024-01-15: Initial implementation (Python test client for Inbetweenies protocol)
- 2024-01-20: Added background sync support
- 2024-01-22: Implemented observer pattern for change notifications

DEPENDENCIES:
- SQLAlchemy with async support for database operations
- aiosqlite for async SQLite operations
- Custom sync engine implementing Inbetweenies protocol
- Repository pattern for data access abstraction

USAGE:
    client = BlowingOffClient("local.db")
    await client.connect("https://api.thegoodies.app", auth_token)
    await client.start_background_sync(interval=30)
    
    # Get devices in a room
    devices = await client.get_devices(room_id="living-room-1")
    
    # Update device state
    await client.update_device_state(
        device_id="light-1",
        state={"on": True, "brightness": 80}
    )
"""

import asyncio
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event
import json

from .models.base import Base
from .sync.engine import SyncEngine
from .sync.state import SyncResult
from .repositories import (
    ClientHouseRepository,
    ClientRoomRepository,
    ClientDeviceRepository,
    ClientUserRepository,
    ClientEntityStateRepository,
    ClientEventRepository
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
        
    async def connect(self, server_url: str, auth_token: str, client_id: str = None):
        """Connect to server and initialize local database."""
        # Initialize database
        db_url = f"sqlite+aiosqlite:///{self.db_path}"
        self.engine = create_async_engine(db_url, echo=False)
        
        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
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
            
        if self.engine:
            await self.engine.dispose()
            
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
        
    async def get_house(self) -> Optional[Dict[str, Any]]:
        """Get the house data."""
        async with self.session_factory() as session:
            repo = ClientHouseRepository(session)
            houses = await repo.get_all()
            if houses:
                house = houses[0]  # Assume single house
                return {
                    "id": house.id,
                    "name": house.name,
                    "address": house.address,
                    "timezone": house.timezone,
                    "metadata": json.loads(house.metadata_json) if house.metadata_json else {}
                }
        return None
        
    async def get_rooms(self, house_id: str = None) -> List[Dict[str, Any]]:
        """Get all rooms."""
        async with self.session_factory() as session:
            repo = ClientRoomRepository(session)
            if house_id:
                rooms = await repo.get_by_house(house_id)
            else:
                rooms = await repo.get_all()
                
            return [
                {
                    "id": room.id,
                    "house_id": room.house_id,
                    "name": room.name,
                    "floor": room.floor,
                    "room_type": room.room_type,
                    "metadata": json.loads(room.metadata_json) if room.metadata_json else {}
                }
                for room in rooms
            ]
            
    async def get_devices(self, room_id: str = None) -> List[Dict[str, Any]]:
        """Get devices, optionally filtered by room."""
        async with self.session_factory() as session:
            repo = ClientDeviceRepository(session)
            if room_id:
                devices = await repo.get_by_room(room_id)
            else:
                devices = await repo.get_all()
                
            return [
                {
                    "id": device.id,
                    "room_id": device.room_id,
                    "name": device.name,
                    "device_type": device.device_type.value,
                    "manufacturer": device.manufacturer,
                    "model": device.model,
                    "capabilities": json.loads(device.capabilities) if device.capabilities else [],
                    "configuration": json.loads(device.configuration) if device.configuration else {},
                    "metadata": json.loads(device.metadata_json) if device.metadata_json else {}
                }
                for device in devices
            ]
            
    async def get_device_state(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get current state of a device."""
        async with self.session_factory() as session:
            repo = ClientEntityStateRepository(session)
            state = await repo.get_latest_by_entity(device_id)
            if state:
                return {
                    "id": state.id,
                    "entity_id": state.entity_id,
                    "state": json.loads(state.state) if state.state else {},
                    "attributes": json.loads(state.attributes) if state.attributes else {},
                    "updated_at": state.updated_at.isoformat()
                }
        return None
        
    async def update_device_state(self, device_id: str, state: Dict[str, Any], attributes: Dict[str, Any] = None):
        """Update device state."""
        async with self.session_factory() as session:
            repo = ClientEntityStateRepository(session)
            
            # Create new state entry
            entity_state = await repo.create(
                id=f"state-{device_id}-{datetime.now().timestamp()}",
                entity_id=device_id,
                entity_type="device",
                state=json.dumps(state),
                attributes=json.dumps(attributes or {})
            )
            
            await session.commit()
            
        # Notify observers
        await self._notify_observers("state_change", {
            "device_id": device_id,
            "state": state,
            "attributes": attributes
        })
        
    async def create_room(self, house_id: str, name: str, **kwargs) -> str:
        """Create a new room."""
        async with self.session_factory() as session:
            repo = ClientRoomRepository(session)
            room = await repo.create(
                id=f"room-{datetime.now().timestamp()}",
                house_id=house_id,
                name=name,
                floor=kwargs.get("floor", 0),
                room_type=kwargs.get("room_type"),
                metadata=json.dumps(kwargs.get("metadata", {}))
            )
            await session.commit()
            
        # Notify observers
        await self._notify_observers("room_created", {"room_id": room.id})
        
        return room.id
        
    async def create_device(self, room_id: str, name: str, device_type: str, **kwargs) -> str:
        """Create a new device."""
        async with self.session_factory() as session:
            repo = ClientDeviceRepository(session)
            
            # Import device type enum
            from .models.device import ClientDeviceType
            device_type_enum = ClientDeviceType(device_type)
            
            device = await repo.create(
                id=f"device-{datetime.now().timestamp()}",
                room_id=room_id,
                name=name,
                device_type=device_type_enum,
                manufacturer=kwargs.get("manufacturer"),
                model=kwargs.get("model"),
                capabilities=json.dumps(kwargs.get("capabilities", [])),
                configuration=json.dumps(kwargs.get("configuration", {})),
                metadata=json.dumps(kwargs.get("metadata", {}))
            )
            await session.commit()
            
        # Notify observers
        await self._notify_observers("device_created", {"device_id": device.id})
        
        return device.id
        
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