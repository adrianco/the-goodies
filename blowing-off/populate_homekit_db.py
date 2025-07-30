#!/usr/bin/env python3
"""
Populate Blowing-off database with test HomeKit-compatible data.

Creates a realistic smart home setup with:
- 1 Home
- 4 Rooms 
- Multiple Accessories with Services and Characteristics
- 3 Users
"""

import asyncio
import json
import uuid
from datetime import datetime, UTC
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Default test database URL
DATABASE_URL = "sqlite+aiosqlite:///./test_blowingoff.db"


async def populate_database(db_url: str = DATABASE_URL):
    """Populate database with HomeKit test data."""
    engine = create_async_engine(db_url, echo=False)
    
    # Import models to create tables
    import sys
    sys.path.insert(0, '/workspaces/the-goodies')
    from inbetweenies.models import Base
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Clearing existing data...")
        # Clear tables in correct order
        await conn.execute(text("DELETE FROM characteristics"))
        await conn.execute(text("DELETE FROM services"))
        await conn.execute(text("DELETE FROM accessory_rooms"))
        await conn.execute(text("DELETE FROM accessories"))
        await conn.execute(text("DELETE FROM users"))
        await conn.execute(text("DELETE FROM rooms"))
        await conn.execute(text("DELETE FROM homes"))
        
        # Create home
        home_id = "00000000-0000-4000-8000-000000000001"
        await conn.execute(text("""
            INSERT INTO homes (id, name, is_primary, created_at, updated_at, sync_id)
            VALUES (:id, :name, :is_primary, :created_at, :updated_at, :sync_id)
        """), {
            "id": home_id,
            "name": "Martinez Family Home",
            "is_primary": True,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "sync_id": f"sync-{home_id}"
        })
        
        # Create rooms
        room_data = [
            ("00000000-0000-4000-8000-000000000010", "Living Room"),
            ("00000000-0000-4000-8000-000000000011", "Kitchen"),
            ("00000000-0000-4000-8000-000000000012", "Master Bedroom"),
            ("00000000-0000-4000-8000-000000000013", "Home Office"),
        ]
        
        for room_id, room_name in room_data:
            await conn.execute(text("""
                INSERT INTO rooms (id, home_id, name, created_at, updated_at, sync_id)
                VALUES (:id, :home_id, :name, :created_at, :updated_at, :sync_id)
            """), {
                "id": room_id,
                "home_id": home_id,
                "name": room_name,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "sync_id": f"sync-{room_id}"
            })
        
        # Create accessories and their services/characteristics
        accessories = [
            {
                "id": "00000000-0000-4000-8000-000000000100",
                "name": "Living Room Light",
                "room_id": "00000000-0000-4000-8000-000000000010",
                "manufacturer": "Philips",
                "model": "Hue White",
                "services": [{
                    "id": "00000000-0000-4000-8000-000000000200",
                    "service_type": "lightbulb",
                    "name": "Light",
                    "characteristics": [
                        {"type": "power_state", "value": "true", "format": "bool"},
                        {"type": "brightness", "value": "75", "format": "uint8", "unit": "percentage", "min_value": 0, "max_value": 100},
                    ]
                }]
            },
            {
                "id": "00000000-0000-4000-8000-000000000101", 
                "name": "Smart Thermostat",
                "room_id": "00000000-0000-4000-8000-000000000010",
                "manufacturer": "Ecobee",
                "model": "SmartThermostat",
                "services": [{
                    "id": "00000000-0000-4000-8000-000000000201",
                    "service_type": "thermostat",
                    "name": "Thermostat",
                    "characteristics": [
                        {"type": "current_temperature", "value": "21.5", "format": "float", "unit": "celsius", "min_value": 0, "max_value": 100},
                        {"type": "target_temperature", "value": "22.0", "format": "float", "unit": "celsius", "min_value": 10, "max_value": 32},
                        {"type": "heating_cooling_state", "value": "heat", "format": "string"},
                    ]
                }]
            },
            {
                "id": "00000000-0000-4000-8000-000000000102",
                "name": "Kitchen Light Strip", 
                "room_id": "00000000-0000-4000-8000-000000000011",
                "manufacturer": "Philips",
                "model": "Hue Lightstrip",
                "services": [{
                    "id": "00000000-0000-4000-8000-000000000202",
                    "service_type": "lightbulb",
                    "name": "Light Strip",
                    "characteristics": [
                        {"type": "power_state", "value": "false", "format": "bool"},
                        {"type": "brightness", "value": "50", "format": "uint8", "unit": "percentage", "min_value": 0, "max_value": 100},
                        {"type": "hue", "value": "180", "format": "float", "unit": "arcdegrees", "min_value": 0, "max_value": 360},
                        {"type": "saturation", "value": "50", "format": "float", "unit": "percentage", "min_value": 0, "max_value": 100},
                    ]
                }]
            },
            {
                "id": "00000000-0000-4000-8000-000000000103",
                "name": "Bedroom Lamp",
                "room_id": "00000000-0000-4000-8000-000000000012", 
                "manufacturer": "IKEA",
                "model": "TRADFRI",
                "services": [{
                    "id": "00000000-0000-4000-8000-000000000203",
                    "service_type": "lightbulb",
                    "name": "Lamp",
                    "characteristics": [
                        {"type": "power_state", "value": "false", "format": "bool"},
                        {"type": "brightness", "value": "25", "format": "uint8", "unit": "percentage", "min_value": 0, "max_value": 100},
                    ]
                }]
            },
            {
                "id": "00000000-0000-4000-8000-000000000104",
                "name": "Office Motion Sensor",
                "room_id": "00000000-0000-4000-8000-000000000013",
                "manufacturer": "Aqara", 
                "model": "Motion Sensor",
                "services": [{
                    "id": "00000000-0000-4000-8000-000000000204",
                    "service_type": "motion_sensor",
                    "name": "Motion",
                    "characteristics": [
                        {"type": "motion_detected", "value": "false", "format": "bool"},
                        {"type": "battery_level", "value": "87", "format": "uint8", "unit": "percentage", "min_value": 0, "max_value": 100},
                    ]
                }]
            }
        ]
        
        # Insert accessories
        for acc in accessories:
            await conn.execute(text("""
                INSERT INTO accessories (id, home_id, name, manufacturer, model, serial_number, 
                                       firmware_version, is_reachable, is_blocked, is_bridge, 
                                       bridge_id, created_at, updated_at, sync_id)
                VALUES (:id, :home_id, :name, :manufacturer, :model, :serial_number,
                        :firmware_version, :is_reachable, :is_blocked, :is_bridge,
                        :bridge_id, :created_at, :updated_at, :sync_id)
            """), {
                "id": acc["id"],
                "home_id": home_id,
                "name": acc["name"],
                "manufacturer": acc["manufacturer"],
                "model": acc["model"],
                "serial_number": f"SN-{acc['id'][-6:]}",
                "firmware_version": "1.0.0",
                "is_reachable": True,
                "is_blocked": False,
                "is_bridge": False,
                "bridge_id": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "sync_id": f"sync-{acc['id']}"
            })
            
            # Link accessory to room
            await conn.execute(text("""
                INSERT INTO accessory_rooms (accessory_id, room_id)
                VALUES (:accessory_id, :room_id)
            """), {
                "accessory_id": acc["id"],
                "room_id": acc["room_id"]
            })
            
            # Insert services and characteristics
            for svc in acc["services"]:
                await conn.execute(text("""
                    INSERT INTO services (id, accessory_id, service_type, name, is_primary, 
                                        is_user_interactive, created_at, updated_at, sync_id)
                    VALUES (:id, :accessory_id, :service_type, :name, :is_primary,
                            :is_user_interactive, :created_at, :updated_at, :sync_id)
                """), {
                    "id": svc["id"],
                    "accessory_id": acc["id"],
                    "service_type": svc["service_type"],
                    "name": svc["name"],
                    "is_primary": True,
                    "is_user_interactive": True,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                    "sync_id": f"sync-{svc['id']}"
                })
                
                # Insert characteristics
                for idx, char in enumerate(svc["characteristics"]):
                    # Generate unique UUID for each characteristic
                    char_id = str(uuid.uuid4())
                    await conn.execute(text("""
                        INSERT INTO characteristics (id, service_id, characteristic_type, value,
                                                   format, unit, min_value, max_value, step_value,
                                                   is_readable, is_writable, supports_event_notification,
                                                   created_at, updated_at, sync_id)
                        VALUES (:id, :service_id, :characteristic_type, :value,
                                :format, :unit, :min_value, :max_value, :step_value,
                                :is_readable, :is_writable, :supports_event_notification,
                                :created_at, :updated_at, :sync_id)
                    """), {
                        "id": char_id,
                        "service_id": svc["id"],
                        "characteristic_type": char["type"],
                        "value": char["value"],
                        "format": char.get("format"),
                        "unit": char.get("unit"),
                        "min_value": char.get("min_value"),
                        "max_value": char.get("max_value"),
                        "step_value": char.get("step_value"),
                        "is_readable": True,
                        "is_writable": True,
                        "supports_event_notification": True,
                        "created_at": datetime.now(UTC),
                        "updated_at": datetime.now(UTC),
                        "sync_id": f"sync-{char_id}"
                    })
        
        # Create users
        users = [
            ("00000000-0000-4000-8000-000000001000", "Carlos Martinez", True, True),
            ("00000000-0000-4000-8000-000000001001", "Maria Martinez", True, False), 
            ("00000000-0000-4000-8000-000000001002", "Sofia Martinez", False, False),
        ]
        
        for user_id, name, is_admin, is_owner in users:
            await conn.execute(text("""
                INSERT INTO users (id, home_id, name, is_administrator, is_owner, 
                                 remote_access_allowed, created_at, updated_at, sync_id)
                VALUES (:id, :home_id, :name, :is_administrator, :is_owner,
                        :remote_access_allowed, :created_at, :updated_at, :sync_id)
            """), {
                "id": user_id,
                "home_id": home_id,
                "name": name,
                "is_administrator": is_admin,
                "is_owner": is_owner,
                "remote_access_allowed": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "sync_id": f"sync-{user_id}"
            })
        
        await conn.commit()
    
    await engine.dispose()
    print("✅ HomeKit test database populated successfully!")
    print(f"   - 1 Home")
    print(f"   - {len(room_data)} Rooms")
    print(f"   - {len(accessories)} Accessories with Services and Characteristics")
    print(f"   - {len(users)} Users")


if __name__ == "__main__":
    import sys
    import os
    
    # Get database URL from environment or command line
    if len(sys.argv) > 1:
        db_url = sys.argv[1]
    else:
        db_url = os.environ.get("DATABASE_URL", DATABASE_URL)
    
    print(f"Populating database: {db_url}")
    asyncio.run(populate_database(db_url))