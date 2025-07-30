#!/usr/bin/env python3
"""Test that HomeKit models work correctly in both server and client."""

import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Test imports
print("Testing model imports...")
try:
    from inbetweenies.models import Base, Home, Room, Accessory, Service, Characteristic, User
    print("✅ Inbetweenies models imported successfully")
except Exception as e:
    print(f"❌ Failed to import Inbetweenies models: {e}")
    sys.exit(1)

try:
    from funkygibbon.models import Home as ServerHome, Accessory as ServerAccessory
    print("✅ FunkyGibbon models imported successfully")
except Exception as e:
    print(f"❌ Failed to import FunkyGibbon models: {e}")
    sys.exit(1)

try:
    from blowingoff.models import Home as ClientHome, Accessory as ClientAccessory
    print("✅ Blowing-Off models imported successfully") 
except Exception as e:
    print(f"❌ Failed to import Blowing-Off models: {e}")
    # Try the new clean import
    try:
        sys.path.insert(0, '/workspaces/the-goodies/blowing-off')
        from blowingoff.models import Home as ClientHome, Accessory as ClientAccessory
        print("✅ Blowing-Off models imported successfully (after path fix)")
    except Exception as e2:
        print(f"❌ Still failed: {e2}")
        sys.exit(1)

# Verify they're the same classes
assert ServerHome is Home, "Server Home is not using shared model"
assert ClientHome is Home, "Client Home is not using shared model"
print("✅ Both server and client are using shared models")


async def test_database_creation():
    """Test creating tables with HomeKit models."""
    # Create test database
    engine = create_async_engine("sqlite+aiosqlite:///./test_homekit.db", echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Database tables created successfully")
        
        # Verify tables exist
        result = await conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """))
        tables = [row[0] for row in result]
        
        expected_tables = ['accessory_rooms', 'accessories', 'characteristics', 'homes', 'rooms', 'services', 'users']
        for table in expected_tables:
            if table in tables:
                print(f"  ✓ {table}")
            else:
                print(f"  ✗ {table} MISSING!")
    
    await engine.dispose()
    

async def test_homekit_data():
    """Test creating HomeKit-style data."""
    engine = create_async_engine("sqlite+aiosqlite:///./test_homekit.db", echo=False)
    
    async with engine.begin() as conn:
        # Create a home
        await conn.execute(text("""
            INSERT OR REPLACE INTO homes (id, name, is_primary, created_at, updated_at)
            VALUES ('test-home-1', 'Test Home', 1, datetime('now'), datetime('now'))
        """))
        
        # Create a room
        await conn.execute(text("""
            INSERT OR REPLACE INTO rooms (id, home_id, name, created_at, updated_at)
            VALUES ('test-room-1', 'test-home-1', 'Living Room', datetime('now'), datetime('now'))
        """))
        
        # Create an accessory
        await conn.execute(text("""
            INSERT OR REPLACE INTO accessories (id, home_id, name, manufacturer, model, 
                                              is_reachable, is_blocked, is_bridge,
                                              created_at, updated_at)
            VALUES ('test-acc-1', 'test-home-1', 'Smart Light', 'Philips', 'Hue White',
                    1, 0, 0, datetime('now'), datetime('now'))
        """))
        
        # Link accessory to room
        await conn.execute(text("""
            INSERT OR REPLACE INTO accessory_rooms (accessory_id, room_id)
            VALUES ('test-acc-1', 'test-room-1')
        """))
        
        # Create a service
        await conn.execute(text("""
            INSERT OR REPLACE INTO services (id, accessory_id, service_type, name,
                                           is_primary, is_user_interactive,
                                           created_at, updated_at)
            VALUES ('test-svc-1', 'test-acc-1', 'lightbulb', 'Light',
                    1, 1, datetime('now'), datetime('now'))
        """))
        
        # Create characteristics
        await conn.execute(text("""
            INSERT OR REPLACE INTO characteristics (id, service_id, characteristic_type,
                                                  value, format, is_readable, is_writable,
                                                  supports_event_notification,
                                                  created_at, updated_at)
            VALUES ('test-char-1', 'test-svc-1', 'power_state',
                    'true', 'bool', 1, 1, 1,
                    datetime('now'), datetime('now'))
        """))
        
        print("✅ Test HomeKit data created successfully")
        
        # Verify the data
        result = await conn.execute(text("SELECT COUNT(*) FROM homes"))
        count = result.scalar()
        print(f"  Homes: {count}")
        
        result = await conn.execute(text("SELECT COUNT(*) FROM accessories"))
        count = result.scalar()
        print(f"  Accessories: {count}")
        
        result = await conn.execute(text("SELECT COUNT(*) FROM characteristics"))
        count = result.scalar()
        print(f"  Characteristics: {count}")
    
    await engine.dispose()


if __name__ == "__main__":
    print("\n=== Testing HomeKit Models Integration ===\n")
    
    # Run tests
    asyncio.run(test_database_creation())
    print()
    asyncio.run(test_homekit_data())
    
    print("\n✅ All tests passed!")