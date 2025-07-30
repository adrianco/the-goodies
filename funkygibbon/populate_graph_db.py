#!/usr/bin/env python3
"""
Populate FunkyGibbon MCP graph database with comprehensive test data.

Creates a realistic smart home knowledge graph with:
- Multiple homes with rooms and zones
- Various device types with relationships
- Procedures and manuals for devices
- Automations and schedules
- Notes and documentation
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

from inbetweenies.models import Base, Entity, EntityType, SourceType, EntityRelationship, RelationshipType

# Default database URL
DATABASE_URL = "sqlite+aiosqlite:///./funkygibbon.db"


class GraphPopulator:
    """Populate graph database with realistic smart home data"""
    
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
        self.engine = create_async_engine(db_url, echo=False)
        self.session_maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.entities = {}  # Store created entities by key for relationships
        
    async def setup_database(self):
        """Create tables and clear existing data"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            print("🗑️  Clearing existing graph data...")
            # Clear in reverse dependency order
            await conn.execute(text("DELETE FROM entity_relationships"))
            await conn.execute(text("DELETE FROM entities"))
            print("✅ Database ready for population")
    
    async def create_entity(self, session: AsyncSession, entity_type: EntityType, 
                          name: str, content: dict, key: str = None) -> Entity:
        """Create and store an entity"""
        entity = Entity(
            id=str(uuid4()),
            version=Entity.create_version("populate-script"),
            entity_type=entity_type,
            name=name,
            content=content,
            source_type=SourceType.GENERATED,
            user_id="populate-script",
            parent_versions=[]
        )
        session.add(entity)
        
        if key:
            self.entities[key] = entity
        
        return entity
    
    async def create_relationship(self, session: AsyncSession, 
                                from_entity: Entity, to_entity: Entity,
                                rel_type: RelationshipType, 
                                properties: dict = None) -> EntityRelationship:
        """Create a relationship between entities"""
        relationship = EntityRelationship(
            id=str(uuid4()),
            from_entity_id=from_entity.id,
            from_entity_version=from_entity.version,
            to_entity_id=to_entity.id,
            to_entity_version=to_entity.version,
            relationship_type=rel_type,
            properties=properties or {},
            user_id="populate-script"
        )
        session.add(relationship)
        return relationship
    
    async def populate(self):
        """Populate the database with comprehensive test data"""
        async with self.session_maker() as session:
            print("\n🏠 Creating Smart Home Graph...")
            
            # Create main home
            home = await self.create_entity(
                session, EntityType.HOME,
                "The Martinez Smart Home",
                {
                    "address": "456 Innovation Drive, Smart City, SC 90210",
                    "timezone": "America/Los_Angeles",
                    "floors": 2,
                    "square_feet": 2500
                },
                key="main_home"
            )
            
            # Create zones
            print("\n🗺️  Creating zones...")
            ground_floor = await self.create_entity(
                session, EntityType.ZONE,
                "Ground Floor",
                {"floor": 1, "description": "Main living areas"},
                key="ground_floor"
            )
            
            upper_floor = await self.create_entity(
                session, EntityType.ZONE,
                "Upper Floor", 
                {"floor": 2, "description": "Bedrooms and office"},
                key="upper_floor"
            )
            
            outdoor = await self.create_entity(
                session, EntityType.ZONE,
                "Outdoor Areas",
                {"description": "Patio, garden, and garage"},
                key="outdoor"
            )
            
            # Create zone relationships
            await self.create_relationship(session, ground_floor, home, RelationshipType.PART_OF)
            await self.create_relationship(session, upper_floor, home, RelationshipType.PART_OF)
            await self.create_relationship(session, outdoor, home, RelationshipType.PART_OF)
            
            # Create rooms
            print("\n🚪 Creating rooms...")
            living_room = await self.create_entity(
                session, EntityType.ROOM,
                "Living Room",
                {"area": 350, "floor": 1, "features": ["fireplace", "bay_window"]},
                key="living_room"
            )
            
            kitchen = await self.create_entity(
                session, EntityType.ROOM,
                "Kitchen",
                {"area": 250, "floor": 1, "features": ["island", "pantry"]},
                key="kitchen"
            )
            
            dining_room = await self.create_entity(
                session, EntityType.ROOM,
                "Dining Room",
                {"area": 200, "floor": 1, "features": ["chandelier"]},
                key="dining_room"
            )
            
            master_bedroom = await self.create_entity(
                session, EntityType.ROOM,
                "Master Bedroom",
                {"area": 300, "floor": 2, "features": ["walk_in_closet", "ensuite"]},
                key="master_bedroom"
            )
            
            office = await self.create_entity(
                session, EntityType.ROOM,
                "Home Office",
                {"area": 150, "floor": 2, "features": ["built_in_shelves"]},
                key="office"
            )
            
            garage = await self.create_entity(
                session, EntityType.ROOM,
                "Garage",
                {"area": 400, "capacity": 2, "features": ["ev_charger", "workbench"]},
                key="garage"
            )
            
            # Room relationships
            await self.create_relationship(session, living_room, ground_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, kitchen, ground_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, dining_room, ground_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, master_bedroom, upper_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, office, upper_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, garage, outdoor, RelationshipType.LOCATED_IN)
            
            # Room to home relationships
            for room in [living_room, kitchen, dining_room, master_bedroom, office, garage]:
                await self.create_relationship(session, room, home, RelationshipType.PART_OF)
            
            # Create doors connecting rooms
            print("\n🚪 Creating doors and connections...")
            kitchen_dining_door = await self.create_entity(
                session, EntityType.DOOR,
                "Kitchen-Dining Door",
                {"type": "swinging", "material": "wood"},
                key="kitchen_dining_door"
            )
            
            await self.create_relationship(session, kitchen_dining_door, kitchen, RelationshipType.CONNECTS_TO)
            await self.create_relationship(session, kitchen_dining_door, dining_room, RelationshipType.CONNECTS_TO)
            await self.create_relationship(session, kitchen, dining_room, RelationshipType.CONNECTS_TO,
                                         {"via": "door", "accessibility": "wheelchair_accessible"})
            
            # Create devices
            print("\n📱 Creating devices...")
            
            # Living room devices
            tv = await self.create_entity(
                session, EntityType.DEVICE,
                "65\" Smart TV",
                {
                    "manufacturer": "Samsung",
                    "model": "QN90A",
                    "type": "entertainment",
                    "capabilities": ["power", "volume", "input", "apps"],
                    "network": "wifi",
                    "ip": "192.168.1.100"
                },
                key="tv"
            )
            
            thermostat = await self.create_entity(
                session, EntityType.DEVICE,
                "Smart Thermostat",
                {
                    "manufacturer": "Nest",
                    "model": "Learning Thermostat",
                    "type": "climate",
                    "capabilities": ["temperature", "humidity", "schedule", "eco_mode"],
                    "network": "wifi",
                    "ip": "192.168.1.101"
                },
                key="thermostat"
            )
            
            # Kitchen devices
            fridge = await self.create_entity(
                session, EntityType.DEVICE,
                "Smart Refrigerator",
                {
                    "manufacturer": "LG",
                    "model": "InstaView",
                    "type": "appliance",
                    "capabilities": ["temperature", "door_sensor", "inventory"],
                    "network": "wifi",
                    "ip": "192.168.1.102"
                },
                key="fridge"
            )
            
            oven = await self.create_entity(
                session, EntityType.DEVICE,
                "Smart Oven",
                {
                    "manufacturer": "Samsung",
                    "model": "Flex Duo",
                    "type": "appliance",
                    "capabilities": ["temperature", "timer", "preheat", "self_clean"],
                    "network": "wifi",
                    "ip": "192.168.1.103"
                },
                key="oven"
            )
            
            # Lighting
            living_room_lights = await self.create_entity(
                session, EntityType.DEVICE,
                "Living Room Lights",
                {
                    "manufacturer": "Philips",
                    "model": "Hue Go",
                    "type": "light",
                    "capabilities": ["power", "brightness", "color", "scenes"],
                    "count": 4,
                    "network": "zigbee",
                    "hub": "philips_hue_bridge"
                },
                key="living_room_lights"
            )
            
            # Security
            doorbell = await self.create_entity(
                session, EntityType.DEVICE,
                "Video Doorbell",
                {
                    "manufacturer": "Ring",
                    "model": "Doorbell Pro 2",
                    "type": "security",
                    "capabilities": ["video", "motion", "two_way_audio", "night_vision"],
                    "network": "wifi",
                    "ip": "192.168.1.104"
                },
                key="doorbell"
            )
            
            # Device location relationships
            await self.create_relationship(session, tv, living_room, RelationshipType.LOCATED_IN,
                                         {"position": "wall_mounted", "height": "eye_level"})
            await self.create_relationship(session, thermostat, living_room, RelationshipType.LOCATED_IN,
                                         {"position": "wall", "height": "5ft"})
            await self.create_relationship(session, fridge, kitchen, RelationshipType.LOCATED_IN,
                                         {"position": "north_wall"})
            await self.create_relationship(session, oven, kitchen, RelationshipType.LOCATED_IN,
                                         {"position": "east_wall"})
            await self.create_relationship(session, living_room_lights, living_room, RelationshipType.LOCATED_IN,
                                         {"positions": ["ceiling_center", "corners"]})
            await self.create_relationship(session, doorbell, home, RelationshipType.MONITORS,
                                         {"location": "front_entrance"})
            
            # Create procedures
            print("\n📋 Creating procedures and manuals...")
            
            tv_setup = await self.create_entity(
                session, EntityType.PROCEDURE,
                "TV Initial Setup",
                {
                    "steps": [
                        "1. Connect power cable",
                        "2. Turn on TV with remote",
                        "3. Select language",
                        "4. Connect to WiFi network",
                        "5. Sign in to Samsung account",
                        "6. Run channel scan",
                        "7. Install streaming apps"
                    ],
                    "duration": "30 minutes",
                    "difficulty": "easy"
                },
                key="tv_setup"
            )
            
            thermostat_schedule = await self.create_entity(
                session, EntityType.PROCEDURE,
                "Configure Thermostat Schedule",
                {
                    "steps": [
                        "1. Press thermostat to wake",
                        "2. Navigate to Settings > Schedule",
                        "3. Set Wake time and temperature",
                        "4. Set Away time and temperature",
                        "5. Set Sleep time and temperature",
                        "6. Repeat for each day",
                        "7. Enable Auto-Schedule learning"
                    ],
                    "duration": "15 minutes",
                    "difficulty": "medium"
                },
                key="thermostat_schedule"
            )
            
            # Create manuals
            tv_manual = await self.create_entity(
                session, EntityType.MANUAL,
                "Samsung QN90A User Manual",
                {
                    "manufacturer": "Samsung",
                    "model": "QN90A",
                    "version": "1.2",
                    "languages": ["en", "es", "fr"],
                    "pages": 120,
                    "sections": ["setup", "features", "troubleshooting", "specifications"],
                    "url": "https://samsung.com/support/QN90A"
                },
                key="tv_manual"
            )
            
            # Procedure relationships
            await self.create_relationship(session, tv_setup, tv, RelationshipType.PROCEDURE_FOR)
            await self.create_relationship(session, thermostat_schedule, thermostat, RelationshipType.PROCEDURE_FOR)
            await self.create_relationship(session, tv, tv_manual, RelationshipType.DOCUMENTED_BY)
            
            # Create automations
            print("\n🤖 Creating automations...")
            
            good_morning = await self.create_entity(
                session, EntityType.AUTOMATION,
                "Good Morning Routine",
                {
                    "trigger": {
                        "type": "time",
                        "time": "07:00",
                        "days": ["mon", "tue", "wed", "thu", "fri"]
                    },
                    "actions": [
                        {"device": "thermostat", "action": "set_temperature", "value": 72},
                        {"device": "living_room_lights", "action": "turn_on", "brightness": 50},
                        {"device": "kitchen_lights", "action": "turn_on", "brightness": 100}
                    ],
                    "enabled": True
                },
                key="good_morning"
            )
            
            movie_time = await self.create_entity(
                session, EntityType.AUTOMATION,
                "Movie Time Scene",
                {
                    "trigger": {"type": "manual", "voice_command": "movie time"},
                    "actions": [
                        {"device": "tv", "action": "turn_on"},
                        {"device": "living_room_lights", "action": "dim", "brightness": 10},
                        {"device": "thermostat", "action": "set_temperature", "value": 70}
                    ],
                    "enabled": True
                },
                key="movie_time"
            )
            
            # Automation relationships
            await self.create_relationship(session, good_morning, thermostat, RelationshipType.AUTOMATES)
            await self.create_relationship(session, good_morning, living_room_lights, RelationshipType.AUTOMATES)
            await self.create_relationship(session, movie_time, tv, RelationshipType.CONTROLS)
            await self.create_relationship(session, movie_time, living_room_lights, RelationshipType.CONTROLS)
            
            # Create schedules
            print("\n📅 Creating schedules...")
            
            vacation_mode = await self.create_entity(
                session, EntityType.SCHEDULE,
                "Vacation Mode",
                {
                    "start_date": "2025-08-01",
                    "end_date": "2025-08-15",
                    "settings": {
                        "thermostat": {"mode": "eco", "temp_min": 60, "temp_max": 85},
                        "lights": {"mode": "random", "start_time": "sunset", "end_time": "23:00"},
                        "security": {"mode": "enhanced", "notifications": "all"}
                    },
                    "active": False
                },
                key="vacation_mode"
            )
            
            # Schedule relationships
            await self.create_relationship(session, vacation_mode, thermostat, RelationshipType.MANAGES)
            await self.create_relationship(session, vacation_mode, doorbell, RelationshipType.MANAGES)
            
            # Create notes
            print("\n📝 Creating notes...")
            
            wifi_note = await self.create_entity(
                session, EntityType.NOTE,
                "WiFi Configuration",
                {
                    "content": "Network: MartinezHome5G\nPassword: Sm@rtH0me2025!\nGuest Network: MartinezGuest\nGuest Password: Welcome123",
                    "category": "network",
                    "private": True,
                    "created": datetime.now(timezone.utc).isoformat()
                },
                key="wifi_note"
            )
            
            maintenance_note = await self.create_entity(
                session, EntityType.NOTE,
                "HVAC Maintenance",
                {
                    "content": "Last filter change: July 1, 2025\nNext service due: October 1, 2025\nTechnician: Bob from ComfortPro (555-0123)",
                    "category": "maintenance",
                    "reminder_date": "2025-10-01",
                    "created": datetime.now(timezone.utc).isoformat()
                },
                key="maintenance_note"
            )
            
            # Note relationships
            await self.create_relationship(session, wifi_note, home, RelationshipType.DOCUMENTED_BY)
            await self.create_relationship(session, maintenance_note, thermostat, RelationshipType.DOCUMENTED_BY)
            
            # Commit all changes
            await session.commit()
            
            # Print summary
            print("\n✅ Graph population complete!")
            print("\n📊 Created:")
            print(f"  • 1 Home")
            print(f"  • 3 Zones")
            print(f"  • 6 Rooms")
            print(f"  • 1 Door")
            print(f"  • 6 Devices")
            print(f"  • 2 Procedures")
            print(f"  • 1 Manual")
            print(f"  • 2 Automations")
            print(f"  • 1 Schedule")
            print(f"  • 2 Notes")
            print(f"  • ~30+ Relationships")
            
            return True


async def main():
    """Main entry point"""
    print("🏠 Populating FunkyGibbon MCP Graph Database...")
    print("=" * 50)
    
    populator = GraphPopulator()
    
    try:
        await populator.setup_database()
        await populator.populate()
        print("\n🎉 Database population successful!")
        print(f"\n📁 Database location: {DATABASE_URL}")
        print("\n🧪 Test with: oook stats")
        
    except Exception as e:
        print(f"\n❌ Error populating database: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)