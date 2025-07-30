#!/usr/bin/env python3
"""
Simple database population script for FunkyGibbon.
Run this to create test data for manual testing.
"""

import asyncio
import json
import os
from datetime import datetime, UTC
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from funkygibbon.database import Base


async def populate_database():
    """Populate database with test data using HomeKit-compatible models."""
    db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./funkygibbon.db")
    
    # Create engine
    engine = create_async_engine(db_url, echo=False)
    
    async with engine.begin() as conn:
        # Create tables using SQLAlchemy models
        await conn.run_sync(Base.metadata.create_all)
        
        # Clear existing data
        await conn.execute(text("DELETE FROM accessories"))
        await conn.execute(text("DELETE FROM rooms"))
        await conn.execute(text("DELETE FROM users"))
        await conn.execute(text("DELETE FROM homes"))
        
        # Insert home
        home_id = "home-" + str(datetime.now().timestamp())
        sync_id = f"sync-{home_id}"
        
        await conn.execute(text("""
            INSERT INTO homes (id, sync_id, name, is_primary, created_at, updated_at)
            VALUES (:id, :sync_id, :name, :is_primary, :created_at, :updated_at)
        """), {
            "id": home_id,
            "sync_id": sync_id,
            "name": "The Martinez Smart Home",
            "is_primary": True,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC)
        })
        
        # Insert rooms
        room_configs = [
            ("Living Room", "Living space with entertainment center"),
            ("Kitchen", "Modern kitchen with smart appliances"),
            ("Master Bedroom", "Primary bedroom with climate control"),
            ("Office", "Home office with automated lighting")
        ]
        
        room_ids = []
        for i, (name, description) in enumerate(room_configs):
            room_id = f"room-{home_id}-{i}"
            room_ids.append(room_id)
            
            await conn.execute(text("""
                INSERT INTO rooms (id, sync_id, home_id, name, created_at, updated_at)
                VALUES (:id, :sync_id, :home_id, :name, :created_at, :updated_at)
            """), {
                "id": room_id,
                "sync_id": f"sync-{room_id}",
                "home_id": home_id,
                "name": name,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC)
            })
        
        # Insert accessories
        accessory_configs = [
            ("Smart TV", "Samsung", "QN90A", room_ids[0]),
            ("Ceiling Light", "Philips", "Hue Go", room_ids[0]),
            ("Smart Fridge", "LG", "InstaView", room_ids[1]),
            ("Overhead Light", "Lutron", "Caseta", room_ids[1]),
            ("Bedside Lamp", "IKEA", "TRADFRI", room_ids[2]),
            ("Smart Thermostat", "Nest", "Learning Thermostat", room_ids[2]),
            ("Desk Lamp", "BenQ", "ScreenBar", room_ids[3]),
            ("Smart Speaker", "Apple", "HomePod mini", room_ids[3])
        ]
        
        accessory_ids = []
        for i, (name, manufacturer, model, room_id) in enumerate(accessory_configs):
            accessory_id = f"accessory-{home_id}-{i}"
            accessory_ids.append(accessory_id)
            
            await conn.execute(text("""
                INSERT INTO accessories (id, sync_id, home_id, name, manufacturer, model, 
                                       serial_number, firmware_version, is_reachable, is_blocked, 
                                       is_bridge, created_at, updated_at)
                VALUES (:id, :sync_id, :home_id, :name, :manufacturer, :model,
                        :serial_number, :firmware_version, :is_reachable, :is_blocked,
                        :is_bridge, :created_at, :updated_at)
            """), {
                "id": accessory_id,
                "sync_id": f"sync-{accessory_id}",
                "home_id": home_id,
                "name": name,
                "manufacturer": manufacturer,
                "model": model,
                "serial_number": f"SN-{i:06d}",
                "firmware_version": "1.0.0",
                "is_reachable": True,
                "is_blocked": False,
                "is_bridge": False,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC)
            })
            
            # Associate accessory with room
            await conn.execute(text("""
                INSERT INTO accessory_rooms (accessory_id, room_id)
                VALUES (:accessory_id, :room_id)
            """), {
                "accessory_id": accessory_id,
                "room_id": room_id
            })
        
        # Insert users  
        user_configs = [
            ("John Martinez", True, True),    # Owner and admin
            ("Jane Martinez", True, False),   # Admin but not owner
            ("Guest User", False, False)      # Regular user
        ]
        
        for i, (name, is_admin, is_owner) in enumerate(user_configs):
            user_id = f"user-{home_id}-{i}"
            
            await conn.execute(text("""
                INSERT INTO users (id, sync_id, home_id, name, is_administrator, is_owner,
                                 remote_access_allowed, created_at, updated_at)
                VALUES (:id, :sync_id, :home_id, :name, :is_administrator, :is_owner,
                        :remote_access_allowed, :created_at, :updated_at)
            """), {
                "id": user_id,
                "sync_id": f"sync-{user_id}",
                "home_id": home_id,
                "name": name,
                "is_administrator": is_admin,
                "is_owner": is_owner,
                "remote_access_allowed": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC)
            })
        
        # Commit is handled by context manager
        
    print("✅ Database populated successfully!")
    print(f"   - 1 home: {home_id}")
    print(f"   - {len(room_ids)} rooms")
    print(f"   - {len(accessory_ids)} accessories")
    print(f"   - {len(user_configs)} users")


if __name__ == "__main__":
    asyncio.run(populate_database())