"""
Blowing-Off HomeKit Client - Clean implementation using shared models
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text
import json

from .models import Base, Home, Room, Accessory, Service, Characteristic, User, accessory_rooms


class HomeKitClient:
    """Client for HomeKit-compatible smart home system."""
    
    def __init__(self, db_path: str = "homekit_client.db"):
        """Initialize client with local SQLite database."""
        self.db_path = db_path
        self.engine = None
        self.session_factory = None
        
    async def connect(self, server_url: str, auth_token: str):
        """Connect to server and initialize local database."""
        # Initialize database
        db_url = f"sqlite+aiosqlite:///{self.db_path}"
        self.engine = create_async_engine(db_url, echo=False)
        
        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
            # Enable SQLite optimizations
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))
            
        # Create session factory
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        self.server_url = server_url
        self.auth_token = auth_token
        
    async def disconnect(self):
        """Disconnect and cleanup resources."""
        if self.engine:
            await self.engine.dispose()
            
    async def get_homes(self) -> List[Dict[str, Any]]:
        """Get all homes."""
        async with self.session_factory() as session:
            result = await session.execute(select(Home))
            homes = result.scalars().all()
            return [home.to_dict() for home in homes]
            
    async def get_home(self, home_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific home."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(Home).where(Home.id == home_id)
            )
            home = result.scalar_one_or_none()
            return home.to_dict() if home else None
            
    async def get_rooms(self, home_id: str) -> List[Dict[str, Any]]:
        """Get all rooms in a home."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(Room).where(Room.home_id == home_id)
            )
            rooms = result.scalars().all()
            return [room.to_dict() for room in rooms]
            
    async def get_accessories(self, home_id: str = None, room_id: str = None) -> List[Dict[str, Any]]:
        """Get accessories, optionally filtered by home or room."""
        async with self.session_factory() as session:
            query = select(Accessory)
            
            if home_id:
                query = query.where(Accessory.home_id == home_id)
                
            if room_id:
                query = query.join(accessory_rooms).where(
                    accessory_rooms.c.room_id == room_id
                )
                
            result = await session.execute(query)
            accessories = result.scalars().all()
            return [acc.to_dict() for acc in accessories]
            
    async def get_services(self, accessory_id: str) -> List[Dict[str, Any]]:
        """Get all services for an accessory."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(Service).where(Service.accessory_id == accessory_id)
            )
            services = result.scalars().all()
            return [svc.to_dict() for svc in services]
            
    async def get_characteristics(self, service_id: str) -> List[Dict[str, Any]]:
        """Get all characteristics for a service."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(Characteristic).where(Characteristic.service_id == service_id)
            )
            characteristics = result.scalars().all()
            return [char.to_dict() for char in characteristics]
            
    async def update_characteristic(self, characteristic_id: str, value: str):
        """Update a characteristic value."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(Characteristic).where(Characteristic.id == characteristic_id)
            )
            char = result.scalar_one_or_none()
            
            if char:
                char.value = value
                char.updated_at = datetime.utcnow()
                await session.commit()
                
    async def create_home(self, name: str, is_primary: bool = False) -> str:
        """Create a new home."""
        async with self.session_factory() as session:
            home = Home(
                id=f"home-{datetime.now().timestamp()}",
                name=name,
                is_primary=is_primary
            )
            session.add(home)
            await session.commit()
            return home.id
            
    async def create_room(self, home_id: str, name: str) -> str:
        """Create a new room."""
        async with self.session_factory() as session:
            room = Room(
                id=f"room-{datetime.now().timestamp()}",
                home_id=home_id,
                name=name
            )
            session.add(room)
            await session.commit()
            return room.id