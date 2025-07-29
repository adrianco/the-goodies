#!/usr/bin/env python3
"""
Simple database population script for FunkyGibbon.
Run this to create test data for manual testing.
"""

import asyncio
import json
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

async def populate_database():
    """Populate database with test data using direct SQL."""
    print("🏠 Creating test data for FunkyGibbon...")
    
    # Create database connection
    DATABASE_URL = "sqlite+aiosqlite:///./funkygibbon.db"
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        # Create tables if they don't exist
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS houses (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                address TEXT,
                timezone TEXT DEFAULT 'UTC',
                latitude REAL,
                longitude REAL,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_id TEXT
            )
        """))
        
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                house_id TEXT NOT NULL,
                house_name TEXT,
                name TEXT NOT NULL,
                floor INTEGER DEFAULT 1,
                room_type TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_id TEXT,
                FOREIGN KEY (house_id) REFERENCES houses(id)
            )
        """))
        
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                room_name TEXT,
                house_id TEXT NOT NULL,
                house_name TEXT,
                name TEXT NOT NULL,
                device_type TEXT NOT NULL,
                manufacturer TEXT,
                model TEXT,
                serial_number TEXT,
                firmware_version TEXT,
                capabilities TEXT,
                configuration TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_id TEXT,
                FOREIGN KEY (room_id) REFERENCES rooms(id),
                FOREIGN KEY (house_id) REFERENCES houses(id)
            )
        """))
        
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                house_id TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT DEFAULT 'member',
                avatar_url TEXT,
                preferences TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_id TEXT,
                FOREIGN KEY (house_id) REFERENCES houses(id)
            )
        """))
        
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_states (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                state_type TEXT NOT NULL,
                state_value TEXT,
                state_json TEXT,
                attributes TEXT,
                last_changed TIMESTAMP,
                last_reported TIMESTAMP,
                user_id TEXT,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))
        
        # Clear existing data
        await conn.execute(text("DELETE FROM entity_states"))
        await conn.execute(text("DELETE FROM devices"))
        await conn.execute(text("DELETE FROM users"))
        await conn.execute(text("DELETE FROM rooms"))
        await conn.execute(text("DELETE FROM houses"))
        
        # Insert test house
        house_id = "house-" + str(datetime.now().timestamp())
        await conn.execute(text("""
            INSERT INTO houses (id, name, address, timezone, metadata_json)
            VALUES (:id, :name, :address, :timezone, :metadata)
        """), {
            "id": house_id,
            "name": "The Martinez Smart Home",
            "address": "456 Innovation Drive, Smart City, SC 90210",
            "timezone": "America/Los_Angeles",
            "metadata": json.dumps({"type": "single_family", "year_built": 2020})
        })
        
        # Insert rooms
        room_configs = [
            ("living-room", "Living Room", "living_room", 1),
            ("kitchen", "Kitchen", "kitchen", 1),
            ("master-bedroom", "Master Bedroom", "bedroom", 2),
            ("home-office", "Home Office", "office", 2)
        ]
        
        room_ids = {}
        for room_id, name, room_type, floor in room_configs:
            full_room_id = f"{room_id}-{datetime.now().timestamp()}"
            room_ids[room_id] = full_room_id
            await conn.execute(text("""
                INSERT INTO rooms (id, house_id, house_name, name, room_type, floor, metadata_json)
                VALUES (:id, :house_id, :house_name, :name, :room_type, :floor, :metadata)
            """), {
                "id": full_room_id,
                "house_id": house_id,
                "house_name": "The Martinez Smart Home",
                "name": name,
                "room_type": room_type,
                "floor": floor,
                "metadata": json.dumps({"area_sqft": 200})
            })
        
        # Insert devices
        device_configs = [
            ("living-room", "65\" Smart TV", "entertainment", "Samsung", "QN65Q90T"),
            ("living-room", "Smart Thermostat", "climate", "Ecobee", "SmartThermostat"),
            ("kitchen", "Smart Refrigerator", "appliance", "Samsung", "RF28R7351SG"),
            ("kitchen", "Under-Cabinet Lights", "light", "Philips", "Hue Strip"),
            ("master-bedroom", "Bedside Lamps", "light", "Philips", "Hue Go"),
            ("home-office", "Desk Lamp", "light", "BenQ", "ScreenBar")
        ]
        
        device_ids = []
        for room_key, name, device_type, manufacturer, model in device_configs:
            device_id = f"device-{name.lower().replace(' ', '-')}-{datetime.now().timestamp()}"
            device_ids.append(device_id)
            await conn.execute(text("""
                INSERT INTO devices (id, room_id, room_name, house_id, house_name, name, 
                                   device_type, manufacturer, model, metadata_json)
                VALUES (:id, :room_id, :room_name, :house_id, :house_name, :name, 
                        :device_type, :manufacturer, :model, :metadata)
            """), {
                "id": device_id,
                "room_id": room_ids[room_key],
                "room_name": next(n for rk, n, _, _ in room_configs if rk == room_key),
                "house_id": house_id,
                "house_name": "The Martinez Smart Home",
                "name": name,
                "device_type": device_type,
                "manufacturer": manufacturer,
                "model": model,
                "metadata": json.dumps({"warranty": "2 years"})
            })
        
        # Insert users
        user_configs = [
            ("Carlos Martinez", "carlos@martinez-family.com", "admin"),
            ("Maria Martinez", "maria@martinez-family.com", "admin"),
            ("Sofia Martinez", "sofia@martinez-family.com", "member")
        ]
        
        user_id = None
        for name, email, role in user_configs:
            uid = f"user-{email.split('@')[0]}-{datetime.now().timestamp()}"
            if user_id is None:
                user_id = uid  # Save first user ID for device states
            await conn.execute(text("""
                INSERT INTO users (id, house_id, name, email, role, metadata_json)
                VALUES (:id, :house_id, :name, :email, :role, :metadata)
            """), {
                "id": uid,
                "house_id": house_id,
                "name": name,
                "email": email,
                "role": role,
                "metadata": json.dumps({"notifications": True})
            })
        
        # Insert some device states
        for i, device_id in enumerate(device_ids[:3]):  # Just add states for first 3 devices
            state_data = {
                "light": {"power": "on", "brightness": 80},
                "entertainment": {"power": "off", "last_input": "HDMI1"},
                "climate": {"target_temp": 72, "current_temp": 70, "mode": "cool"}
            }
            
            device_type = device_configs[i][2]
            state = state_data.get(device_type, {"power": "on"})
            
            await conn.execute(text("""
                INSERT INTO entity_states (id, entity_id, entity_type, state_type, 
                                         state_value, state_json, user_id)
                VALUES (:id, :entity_id, :entity_type, :state_type, 
                        :state_value, :state_json, :user_id)
            """), {
                "id": f"state-{device_id}-{datetime.now().timestamp()}",
                "entity_id": device_id,
                "entity_type": "device",
                "state_type": "current",
                "state_value": json.dumps(state),
                "state_json": json.dumps(state),
                "user_id": user_id
            })
    
    await engine.dispose()
    
    print("✅ Database populated successfully!")
    print("\n📊 Created:")
    print("  • 1 House (The Martinez Smart Home)")
    print("  • 4 Rooms (Living Room, Kitchen, Master Bedroom, Home Office)")
    print("  • 6 Devices (TV, Thermostat, Fridge, Lights)")
    print("  • 3 Users (Carlos, Maria, Sofia)")
    print("  • 3 Device States")
    print("\n🚀 Next steps:")
    print("  1. Start the server: python -m funkygibbon")
    print("  2. Visit API docs: http://localhost:8000/docs")

if __name__ == "__main__":
    asyncio.run(populate_database())