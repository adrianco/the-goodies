"""
FunkyGibbon - Room Model (House Subdivision)

DEVELOPMENT CONTEXT:
Created in January 2024 as part of the smart home entity hierarchy.
Rooms provide logical grouping of devices within a house, enabling
location-based automation and queries. The model includes denormalized
fields for performance optimization at our target scale.

FUNCTIONALITY:
- Represents physical rooms within a house (kitchen, bedroom, etc.)
- Groups devices by location for easier management
- Stores environmental sensor data (temperature, humidity, motion)
- Maintains denormalized device count for performance
- Supports floor numbers for multi-story homes
- Flexible settings storage via JSON field
- Cascading delete removes all devices in the room

PURPOSE:
Provides spatial organization for smart home devices. Users typically
interact with devices by room ("turn off living room lights"), making
this a critical entity for natural user interactions and automations.

KNOWN ISSUES:
- room_type should be an enum but uses free-form string
- last_motion_at stored as string not datetime (SQLite compatibility)
- No validation on temperature/humidity ranges
- Denormalized house_name can become stale
- No support for room dimensions or layout
- Floor number doesn't support basements (negative numbers)

REVISION HISTORY:
- 2024-01-15: Initial model with basic room fields
- 2024-01-16: Added environmental sensor fields
- 2024-01-17: Added denormalized house_name for performance
- 2024-01-18: Added floor field for multi-story support
- 2024-01-19: Added last_motion_at for presence detection

DEPENDENCIES:
- sqlalchemy: ORM mappings and relationships
- .base: BaseEntity for common fields and timestamps

USAGE:
# Create a room:
room = Room(
    name="Living Room",
    room_type="living_room",
    house_id=house.id,
    house_name=house.name,  # Denormalized
    floor=1,
    temperature=72.5,
    humidity=45.0
)

# Query devices in a room:
devices = room.devices  # Via relationship
"""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base, BaseEntity


class Room(Base, BaseEntity):
    """Room entity - represents a room in a house."""
    
    __tablename__ = "rooms"
    
    # Foreign keys
    house_id = Column(String(36), ForeignKey("houses.id"), nullable=False)
    
    # Basic attributes
    name = Column(String(255), nullable=False)
    room_type = Column(String(50), nullable=True)  # kitchen, bedroom, bathroom, etc
    floor = Column(Integer, nullable=True)
    
    # Denormalized for performance
    house_name = Column(String(255), nullable=False)  # Avoid JOIN for common queries
    device_count = Column(Integer, nullable=False, default=0)
    
    # Sensor data
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    last_motion_at = Column(String(30), nullable=True)  # ISO timestamp as string
    
    # Settings as JSON
    settings_json = Column(Text, nullable=True)
    
    # Relationships
    house = relationship("House", back_populates="rooms")
    devices = relationship("Device", back_populates="room", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Room(id={self.id}, name='{self.name}', type='{self.room_type}')>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "sync_id": self.sync_id,
            "house_id": self.house_id,
            "house_name": self.house_name,
            "name": self.name,
            "room_type": self.room_type,
            "floor": self.floor,
            "device_count": self.device_count,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "last_motion_at": self.last_motion_at,
            "settings_json": self.settings_json,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "is_deleted": self.is_deleted,
        }