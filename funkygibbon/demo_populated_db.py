#!/usr/bin/env python3
"""
Demo script for populated database testing.

Since the full seeding system has import complexities, this script demonstrates
how to quickly populate the database using the existing repository patterns
for human testing purposes.

Run with: python demo_populated_db.py
Then start server with: python -m funkygibbon
"""

import asyncio
from pathlib import Path
import sys

# Add paths for proper imports
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))

async def create_demo_data():
    """Create demo data using the same pattern as the tests."""
    print("🏠 Creating demo smart home data...")
    
    # Import the test session creation
    from funkygibbon.conftest import async_session
    from funkygibbon.repositories import HouseRepository, RoomRepository, DeviceRepository, UserRepository
    
    # Create session like the tests do
    async for session in async_session():
        house_repo = HouseRepository()
        room_repo = RoomRepository()
        device_repo = DeviceRepository()
        user_repo = UserRepository()
        
        # Create The Martinez Smart Home
        print("  🏠 Creating The Martinez Smart Home...")
        house = await house_repo.create(
            session,
            name="The Martinez Smart Home",
            address="456 Innovation Drive, Smart City, SC 90210",
            timezone="America/Los_Angeles"
        )
        
        # Create rooms
        print("  🏠 Adding rooms...")
        living_room = await room_repo.create_with_house_name(
            session, house.id, house.name,
            name="Living Room", room_type="living_room", floor=1
        )
        
        kitchen = await room_repo.create_with_house_name(
            session, house.id, house.name,
            name="Kitchen", room_type="kitchen", floor=1
        )
        
        master_bedroom = await room_repo.create_with_house_name(
            session, house.id, house.name,
            name="Master Bedroom", room_type="bedroom", floor=2
        )
        
        # Create devices
        print("  💡 Adding smart devices...")
        
        # Living room devices
        tv = await device_repo.create_with_names(
            session,
            room_id=living_room.id,
            room_name=living_room.name,
            house_id=house.id,
            house_name=house.name,
            name="65\" Smart TV",
            device_type="entertainment"
        )
        
        thermostat = await device_repo.create_with_names(
            session,
            room_id=living_room.id,
            room_name=living_room.name,
            house_id=house.id,
            house_name=house.name,
            name="Smart Thermostat",
            device_type="climate"
        )
        
        # Kitchen devices
        fridge = await device_repo.create_with_names(
            session,
            room_id=kitchen.id,
            room_name=kitchen.name,
            house_id=house.id,
            house_name=house.name,
            name="Smart Refrigerator",
            device_type="appliance"
        )
        
        # Bedroom devices
        bedside_lamp = await device_repo.create_with_names(
            session,
            room_id=master_bedroom.id,
            room_name=master_bedroom.name,
            house_id=house.id,
            house_name=house.name,
            name="Bedside Lamps",
            device_type="light"
        )
        
        # Create users
        print("  👤 Adding family members...")
        carlos = await user_repo.create(
            session,
            house_id=house.id,
            name="Carlos Martinez",
            email="carlos@martinez-family.com",
            role="admin"
        )
        
        maria = await user_repo.create(
            session,
            house_id=house.id,
            name="Maria Martinez", 
            email="maria@martinez-family.com",
            role="admin"
        )
        
        print("✅ Demo data created successfully!")
        print("\n📊 Summary:")
        print(f"  • House: {house.name}")
        print(f"  • Rooms: 3 (Living Room, Kitchen, Master Bedroom)")
        print(f"  • Devices: 4 (TV, Thermostat, Fridge, Bedside Lamps)")
        print(f"  • Users: 2 (Carlos, Maria)")
        
        print("\n🚀 Next steps:")
        print("  1. Start the server: python -m funkygibbon")
        print("  2. Visit: http://localhost:8000/docs")
        print("  3. Try API endpoints:")
        print("     • GET /api/v1/houses")
        print("     • GET /api/v1/rooms")
        print("     • GET /api/v1/devices")
        print("     • GET /api/v1/users")
        
        break  # Only need one iteration of the async generator

if __name__ == "__main__":
    try:
        asyncio.run(create_demo_data())
    except Exception as e:
        print(f"❌ Error creating demo data: {e}")
        print("\n💡 Alternative: Run the existing tests which create test data:")
        print("   python -m pytest tests/integration/test_end_to_end.py -v")
        sys.exit(1)