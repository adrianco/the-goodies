"""
Database Seeding System for Human Testing

DEVELOPMENT CONTEXT:
Created to provide realistic, populated data for manual testing and development.
This module creates a comprehensive smart home scenario with multiple houses,
rooms, devices, users, and realistic device states for testing purposes.

FUNCTIONALITY:
- Creates multiple house scenarios (apartment, house, office)
- Populates realistic room layouts and device configurations
- Sets up users with different roles and permissions
- Creates device states and event history
- Provides both minimal and comprehensive data sets

PURPOSE:
Enables developers and testers to quickly spin up a populated database
for manual testing, API exploration, and demonstration purposes.

REVISION HISTORY:
- 2025-07-29: Initial implementation with comprehensive seeding scenarios
"""

import asyncio
import json
from datetime import datetime, timedelta, UTC
from typing import Dict, List, Optional
import uuid
import sys
from pathlib import Path

# Add current directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Import the actual classes directly to avoid module import issues
from models.base import Base
from config import Settings
from repositories.house import HouseRepository
from repositories.room import RoomRepository
from repositories.device import DeviceRepository  
from repositories.user import UserRepository
from repositories.entity_state import EntityStateRepository
from repositories.event import EventRepository


class DatabaseSeeder:
    """Handles database seeding with realistic test data."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.house_repo = HouseRepository()
        self.room_repo = RoomRepository()
        self.device_repo = DeviceRepository()
        self.user_repo = UserRepository()
        self.state_repo = EntityStateRepository()
        self.event_repo = EventRepository()
        
    async def seed_all(self, scenario: str = "comprehensive") -> Dict[str, int]:
        """
        Seed database with test data.
        
        Args:
            scenario: "minimal" or "comprehensive"
            
        Returns:
            Dictionary with count of created entities
        """
        print(f"🌱 Starting database seeding with '{scenario}' scenario...")
        
        if scenario == "minimal":
            return await self._seed_minimal()
        else:
            return await self._seed_comprehensive()
    
    async def _seed_minimal(self) -> Dict[str, int]:
        """Create minimal test data - single house with basic setup."""
        print("Creating minimal test data...")
        
        counts = {"houses": 0, "rooms": 0, "devices": 0, "users": 0, "states": 0, "events": 0}
        
        # Create single house
        house = await self.house_repo.create(
            self.session,
            name="Test Smart Home",
            address="123 Developer Lane",
            timezone="America/Los_Angeles"
        )
        counts["houses"] += 1
        
        # Create basic rooms
        rooms = []
        room_configs = [
            ("Living Room", "living_room", 1),
            ("Kitchen", "kitchen", 1),
            ("Bedroom", "bedroom", 2)
        ]
        
        for name, room_type, floor in room_configs:
            room = await self.room_repo.create_with_house_name(
                self.session, house.id, house.name, 
                name=name, room_type=room_type, floor=floor
            )
            rooms.append(room)
            counts["rooms"] += 1
        
        # Create basic devices
        device_configs = [
            (rooms[0].id, "Main Light", "light"),
            (rooms[1].id, "Kitchen Light", "light"),
            (rooms[2].id, "Bedside Lamp", "light")
        ]
        
        devices = []
        for room_id, name, device_type in device_configs:
            room = next(r for r in rooms if r.id == room_id)
            device = await self.device_repo.create_with_names(
                self.session,
                room_id=room_id,
                room_name=room.name,
                house_id=house.id,
                house_name=house.name,
                name=name,
                device_type=device_type
            )
            devices.append(device)
            counts["devices"] += 1
        
        # Create test user
        user = await self.user_repo.create(
            self.session,
            house_id=house.id,
            name="Test User",
            email="test@example.com",
            role="admin"
        )
        counts["users"] += 1
        
        # Create basic device states
        for device in devices:
            await self.state_repo.create(
                self.session,
                entity_id=device.id,
                entity_type="device",
                state_type="on_off",
                state_value="off",
                state_json=json.dumps({"brightness": 0}),
                user_id=user.id
            )
            counts["states"] += 1
        
        await self.session.commit()
        print(f"✅ Minimal seeding complete: {counts}")
        return counts
    
    async def _seed_comprehensive(self) -> Dict[str, int]:
        """Create comprehensive test data with multiple scenarios."""
        print("Creating comprehensive test data...")
        
        counts = {"houses": 0, "rooms": 0, "devices": 0, "users": 0, "states": 0, "events": 0}
        
        # Scenario 1: Modern Smart Home
        house1 = await self._create_modern_smart_home()
        counts["houses"] += 1
        
        # Scenario 2: Small Apartment
        house2 = await self._create_small_apartment()
        counts["houses"] += 1
        
        # Scenario 3: Smart Office
        house3 = await self._create_smart_office()
        counts["houses"] += 1
        
        # Count all created entities
        for house in [house1, house2, house3]:
            # Count rooms
            rooms = await self.room_repo.get_by_house_id(self.session, house.id)
            counts["rooms"] += len(rooms)
            
            # Count devices and states
            for room in rooms:
                devices = await self.device_repo.get_by_room_id(self.session, room.id)
                counts["devices"] += len(devices)
                
                # Count states for each device
                for device in devices:
                    states = await self.state_repo.get_by_entity_id(self.session, device.id)
                    counts["states"] += len(states)
            
            # Count users
            users = await self.user_repo.get_by_house_id(self.session, house.id)
            counts["users"] += len(users)
        
        await self.session.commit()
        print(f"✅ Comprehensive seeding complete: {counts}")
        return counts
    
    async def _create_modern_smart_home(self):
        """Create a modern smart home with comprehensive automation."""
        print("  🏠 Creating Modern Smart Home...")
        
        house = await self.house_repo.create(
            self.session,
            name="The Martinez Smart Home",
            address="456 Innovation Drive, Smart City, SC 90210",
            timezone="America/Los_Angeles",
            latitude=34.0522,
            longitude=-118.2437
        )
        
        # Create rooms with realistic layouts
        rooms = {}
        room_configs = [
            ("Living Room", "living_room", 1, {"area_sqft": 320, "ceiling_height": 9}),
            ("Kitchen", "kitchen", 1, {"area_sqft": 200, "ceiling_height": 9}),
            ("Dining Room", "dining_room", 1, {"area_sqft": 180, "ceiling_height": 9}),
            ("Master Bedroom", "bedroom", 2, {"area_sqft": 250, "ceiling_height": 8}),
            ("Master Bathroom", "bathroom", 2, {"area_sqft": 120, "ceiling_height": 8}),
            ("Guest Bedroom", "bedroom", 2, {"area_sqft": 180, "ceiling_height": 8}),
            ("Guest Bathroom", "bathroom", 2, {"area_sqft": 60, "ceiling_height": 8}),
            ("Home Office", "office", 2, {"area_sqft": 150, "ceiling_height": 8}),
            ("Garage", "garage", 1, {"area_sqft": 400, "ceiling_height": 8}),
            ("Backyard", "outdoor", 1, {"area_sqft": 800, "ceiling_height": 0})
        ]
        
        for name, room_type, floor, metadata in room_configs:
            room = await self.room_repo.create_with_house_name(
                self.session, house.id, house.name,
                name=name, room_type=room_type, floor=floor,
                metadata_json=json.dumps(metadata)
            )
            rooms[name] = room
        
        # Create comprehensive device setup
        await self._add_living_room_devices(house, rooms["Living Room"])
        await self._add_kitchen_devices(house, rooms["Kitchen"])
        await self._add_bedroom_devices(house, rooms["Master Bedroom"])
        await self._add_office_devices(house, rooms["Home Office"])
        await self._add_outdoor_devices(house, rooms["Backyard"])
        
        # Create family users
        users = []
        user_configs = [
            ("Carlos Martinez", "carlos@martinez-family.com", "admin"),
            ("Maria Martinez", "maria@martinez-family.com", "admin"),
            ("Sofia Martinez", "sofia@martinez-family.com", "member"),
            ("Guest User", "guest@martinez-family.com", "guest")
        ]
        
        for name, email, role in user_configs:
            user = await self.user_repo.create(
                self.session, house_id=house.id, name=name, email=email, role=role
            )
            users.append(user)
        
        return house
    
    async def _create_small_apartment(self):
        """Create a small apartment scenario."""
        print("  🏢 Creating Small Apartment...")
        
        house = await self.house_repo.create(
            self.session,
            name="Downtown Loft - Unit 4B",
            address="789 Urban Street, Apt 4B, Metro City, MC 12345",
            timezone="America/New_York"
        )
        
        # Compact apartment layout
        room_configs = [
            ("Living Area", "living_room", 1),
            ("Kitchen", "kitchen", 1),
            ("Bedroom", "bedroom", 1),
            ("Bathroom", "bathroom", 1)
        ]
        
        rooms = {}
        for name, room_type, floor in room_configs:
            room = await self.room_repo.create_with_house_name(
                self.session, house.id, house.name,
                name=name, room_type=room_type, floor=floor
            )
            rooms[name] = room
        
        # Minimal but smart device setup
        device_configs = [
            (rooms["Living Area"], "Smart TV", "entertainment", {"brand": "Samsung", "model": "QN65Q80T"}),
            (rooms["Living Area"], "Ceiling Light", "light", {"type": "LED", "color_temp": True}),
            (rooms["Kitchen"], "Under-Cabinet Lights", "light", {"type": "LED Strip", "dimmable": True}),
            (rooms["Kitchen"], "Smart Fridge", "appliance", {"brand": "LG", "smart_features": True}),
            (rooms["Bedroom"], "Bedside Lamp", "light", {"type": "Smart Bulb", "color_changing": True}),
            (rooms["Bedroom"], "Smart Thermostat", "climate", {"brand": "Nest", "model": "3rd Gen"}),
            (rooms["Bathroom"], "Vanity Light", "light", {"type": "LED", "motion_sensor": True})
        ]
        
        for room, name, device_type, metadata in device_configs:
            await self.device_repo.create_with_names(
                self.session,
                room_id=room.id,
                room_name=room.name,
                house_id=house.id,
                house_name=house.name,
                name=name,
                device_type=device_type,
                metadata_json=json.dumps(metadata)
            )
        
        # Single resident
        await self.user_repo.create(
            self.session,
            house_id=house.id,
            name="Alex Chen",
            email="alex@example.com",
            role="admin"
        )
        
        return house
    
    async def _create_smart_office(self):
        """Create a smart office scenario."""
        print("  🏢 Creating Smart Office...")
        
        house = await self.house_repo.create(
            self.session,
            name="TechStart Inc. - Floor 12",
            address="321 Business Plaza, Suite 1200, Corp City, CC 54321",
            timezone="America/Chicago"
        )
        
        # Office layout
        room_configs = [
            ("Reception", "office", 1),
            ("Conference Room A", "meeting_room", 1),
            ("Conference Room B", "meeting_room", 1),
            ("Open Workspace", "office", 1),
            ("CEO Office", "office", 1),
            ("Break Room", "kitchen", 1),
            ("Server Room", "utility", 1)
        ]
        
        rooms = {}
        for name, room_type, floor in room_configs:
            room = await self.room_repo.create_with_house_name(
                self.session, house.id, house.name,
                name=name, room_type=room_type, floor=floor
            )
            rooms[name] = room
        
        # Office devices
        device_configs = [
            (rooms["Reception"], "Reception Lights", "light", {"zone": "entrance"}),
            (rooms["Conference Room A"], "Presentation Display", "entertainment", {"type": "4K Monitor"}),
            (rooms["Conference Room A"], "Conference Camera", "security", {"type": "PTZ Camera"}),
            (rooms["Open Workspace"], "Workspace Lighting", "light", {"type": "Smart Panels"}),
            (rooms["Break Room"], "Coffee Machine", "appliance", {"brand": "Jura", "smart": True}),
            (rooms["Server Room"], "Temperature Monitor", "sensor", {"type": "Environmental"})
        ]
        
        for room, name, device_type, metadata in device_configs:
            await self.device_repo.create_with_names(
                self.session,
                room_id=room.id,
                room_name=room.name,
                house_id=house.id,
                house_name=house.name,
                name=name,
                device_type=device_type,
                metadata_json=json.dumps(metadata)
            )
        
        # Office staff
        staff_configs = [
            ("Sarah Johnson", "sarah@techstart.com", "admin"),
            ("Mike Rodriguez", "mike@techstart.com", "member"),
            ("Facilities Manager", "facilities@techstart.com", "admin")
        ]
        
        for name, email, role in staff_configs:
            await self.user_repo.create(
                self.session, house_id=house.id, name=name, email=email, role=role
            )
        
        return house
    
    async def _add_living_room_devices(self, house, room):
        """Add comprehensive living room devices."""
        device_configs = [
            ("65\" Smart TV", "entertainment", {
                "brand": "Samsung", "model": "QN65Q90T", "resolution": "4K",
                "smart_features": ["Netflix", "Prime Video", "Disney+"]
            }),
            ("Sound System", "entertainment", {
                "brand": "Sonos", "type": "Arc Soundbar", "surround": True
            }),
            ("Main Ceiling Lights", "light", {
                "type": "Recessed LED", "dimmable": True, "color_temp": True,
                "zones": ["seating", "entertainment", "ambient"]
            }),
            ("Table Lamps", "light", {
                "type": "Smart Bulbs", "color_changing": True, "count": 2
            }),
            ("Smart Thermostat", "climate", {
                "brand": "Ecobee", "model": "SmartThermostat", "sensors": 3
            }),
            ("Security Camera", "security", {
                "type": "Indoor", "resolution": "1080p", "night_vision": True
            })
        ]
        
        devices = []
        for name, device_type, metadata in device_configs:
            device = await self.device_repo.create_with_names(
                self.session,
                room_id=room.id,
                room_name=room.name,
                house_id=house.id,
                house_name=house.name,
                name=name,
                device_type=device_type,
                metadata_json=json.dumps(metadata)
            )
            devices.append(device)
        
        # Add realistic device states
        await self._add_realistic_device_states(devices)
    
    async def _add_kitchen_devices(self, house, room):
        """Add kitchen devices with realistic states."""
        device_configs = [
            ("Smart Refrigerator", "appliance", {
                "brand": "Samsung", "model": "RF28R7351SG", "capacity": "28 cu ft",
                "features": ["Family Hub", "Twin Cooling Plus"]
            }),
            ("Induction Cooktop", "appliance", {
                "brand": "Bosch", "zones": 4, "power_boost": True
            }),
            ("Under-Cabinet Lighting", "light", {
                "type": "LED Strip", "length": "8ft", "dimmable": True
            }),
            ("Pendant Lights", "light", {
                "type": "Smart Bulbs", "count": 3, "style": "Industrial"
            }),
            ("Smart Oven", "appliance", {
                "brand": "GE", "model": "Profile", "convection": True, "wifi": True
            })
        ]
        
        devices = []
        for name, device_type, metadata in device_configs:
            device = await self.device_repo.create_with_names(
                self.session,
                room_id=room.id,
                room_name=room.name,
                house_id=house.id,
                house_name=house.name,
                name=name,
                device_type=device_type,
                metadata_json=json.dumps(metadata)
            )
            devices.append(device)
        
        await self._add_realistic_device_states(devices)
    
    async def _add_bedroom_devices(self, house, room):
        """Add bedroom devices."""
        device_configs = [
            ("Bedside Lamps", "light", {
                "type": "Smart Table Lamps", "count": 2, "touch_control": True
            }),
            ("Ceiling Fan", "climate", {
                "brand": "Hunter", "smart_control": True, "light_kit": True
            }),
            ("Blackout Shades", "window", {
                "type": "Motorized", "brand": "Lutron", "light_sensor": True
            }),
            ("Air Purifier", "appliance", {
                "brand": "Dyson", "model": "Pure Cool", "hepa_filter": True
            })
        ]
        
        devices = []
        for name, device_type, metadata in device_configs:
            device = await self.device_repo.create_with_names(
                self.session,
                room_id=room.id,
                room_name=room.name,
                house_id=house.id,
                house_name=house.name,
                name=name,
                device_type=device_type,
                metadata_json=json.dumps(metadata)
            )
            devices.append(device)
        
        await self._add_realistic_device_states(devices)
    
    async def _add_office_devices(self, house, room):
        """Add home office devices."""
        device_configs = [
            ("Desk Lamp", "light", {
                "type": "LED Desk Lamp", "brightness_levels": 10, "color_temp": True
            }),
            ("Smart Monitor", "entertainment", {
                "brand": "Dell", "size": "32inch", "resolution": "4K", "usb_c": True
            }),
            ("Air Quality Monitor", "sensor", {
                "brand": "Awair", "measures": ["CO2", "VOC", "PM2.5", "humidity"]
            })
        ]
        
        devices = []
        for name, device_type, metadata in device_configs:
            device = await self.device_repo.create_with_names(
                self.session,
                room_id=room.id,
                room_name=room.name,
                house_id=house.id,
                house_name=house.name,
                name=name,
                device_type=device_type,
                metadata_json=json.dumps(metadata)
            )
            devices.append(device)
        
        await self._add_realistic_device_states(devices)
    
    async def _add_outdoor_devices(self, house, room):
        """Add outdoor/backyard devices."""
        device_configs = [
            ("Patio Lights", "light", {
                "type": "String Lights", "length": "50ft", "weatherproof": True
            }),
            ("Garden Sprinklers", "irrigation", {
                "zones": 4, "smart_controller": True, "weather_sensor": True
            }),
            ("Security Floodlights", "security", {
                "type": "Motion Activated", "brightness": "3000 lumens"
            })
        ]
        
        devices = []
        for name, device_type, metadata in device_configs:
            device = await self.device_repo.create_with_names(
                self.session,
                room_id=room.id,
                room_name=room.name,
                house_id=house.id,
                house_name=house.name,
                name=name,
                device_type=device_type,
                metadata_json=json.dumps(metadata)
            )
            devices.append(device)
        
        await self._add_realistic_device_states(devices)
    
    async def _add_realistic_device_states(self, devices):
        """Add realistic device states with history."""
        # Create a test user for state changes (will be created later, using admin for now)
        base_time = datetime.now(UTC) - timedelta(days=7)
        
        for device in devices:
            # Create recent state history
            for i in range(5):
                state_time = base_time + timedelta(hours=i * 12 + i)
                
                # Generate realistic states based on device type
                if device.device_type == "light":
                    states = [
                        ("on_off", "on", {"brightness": 80, "color_temp": 3000}),
                        ("on_off", "off", {"brightness": 0}),
                        ("on_off", "on", {"brightness": 60, "color_temp": 2700})
                    ]
                elif device.device_type == "climate":
                    states = [
                        ("temperature", "72", {"target": 72, "mode": "heat"}),
                        ("temperature", "68", {"target": 68, "mode": "cool"})
                    ]
                elif device.device_type == "entertainment":
                    states = [
                        ("power", "on", {"volume": 25, "input": "Netflix"}),
                        ("power", "off", {}),
                        ("power", "on", {"volume": 30, "input": "HDMI1"})
                    ]
                else:
                    states = [
                        ("power", "on", {}),
                        ("power", "off", {})
                    ]
                
                state_type, state_value, state_data = states[i % len(states)]
                
                # Note: user_id will be set properly when we have actual users
                # For now, we'll create states without user_id and update later
                try:
                    await self.state_repo.create(
                        self.session,
                        entity_id=device.id,
                        entity_type="device",
                        state_type=state_type,
                        state_value=state_value,
                        state_json=json.dumps(state_data),
                        created_at=state_time,
                        updated_at=state_time
                    )
                except Exception as e:
                    # Skip state creation if there's an issue (e.g., missing user_id)
                    print(f"  Warning: Could not create state for {device.name}: {e}")
                    continue
    
    async def clear_all_data(self) -> Dict[str, int]:
        """Clear all data from database (for testing)."""
        print("🗑️ Clearing all database data...")
        
        # Get counts before deletion
        counts = {}
        
        # Clear in reverse dependency order
        await self.session.execute("DELETE FROM entity_states")
        await self.session.execute("DELETE FROM events") 
        await self.session.execute("DELETE FROM users")
        await self.session.execute("DELETE FROM devices")
        await self.session.execute("DELETE FROM rooms")
        await self.session.execute("DELETE FROM houses")
        
        await self.session.commit()
        
        print("✅ Database cleared")
        return counts


async def seed_database(scenario: str = "comprehensive", database_url: Optional[str] = None):
    """
    Main function to seed the database.
    
    Args:
        scenario: "minimal" or "comprehensive"
        database_url: Optional database URL, uses default if not provided
    """
    if not database_url:
        settings = Settings()
        database_url = settings.database_url
    
    # Create async engine and session
    engine = create_async_engine(database_url, echo=False)
    
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session and seed
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        seeder = DatabaseSeeder(session)
        counts = await seeder.seed_all(scenario)
        
        print("\n🎉 Database seeding completed!")
        print("📊 Summary:")
        for entity_type, count in counts.items():
            print(f"  {entity_type.capitalize()}: {count}")
        
        return counts
    
    await engine.dispose()


async def clear_database(database_url: Optional[str] = None):
    """Clear all data from database."""
    if not database_url:
        settings = Settings()
        database_url = settings.database_url
    
    engine = create_async_engine(database_url, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        seeder = DatabaseSeeder(session)
        await seeder.clear_all_data()
    
    await engine.dispose()


if __name__ == "__main__":
    import sys
    
    scenario = "comprehensive"
    command = "seed"
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
    if len(sys.argv) > 2:
        scenario = sys.argv[2]
    
    if command == "clear":
        asyncio.run(clear_database())
    else:
        asyncio.run(seed_database(scenario))