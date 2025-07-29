"""
FunkyGibbon - House Model (Root Entity)

DEVELOPMENT CONTEXT:
Created in January 2024 as the root entity of the smart home knowledge graph.
In our simplified single-house design, there's typically only one House record
per deployment, representing the entire smart home installation.

FUNCTIONALITY:
- Root entity that contains all rooms, devices, and users
- Stores house-level metadata (name, address, location, timezone)
- Maintains denormalized counters for performance (room/device/user counts)
- Provides settings storage via JSON field for flexibility
- Implements cascading deletes to remove all child entities
- Supports soft deletes for sync scenarios

PURPOSE:
The House model serves as the entry point for all smart home data. Since we
target single-family homes, this simplifies the data model compared to
multi-tenant systems while still providing a logical hierarchy.

KNOWN ISSUES:
- Denormalized counters can drift from actual counts without triggers
- settings_json is Text not JSON type (SQLite compatibility)
- No validation on latitude/longitude ranges
- Timezone field doesn't validate against known timezones
- Address field is unstructured text (no geocoding integration)

REVISION HISTORY:
- 2024-01-15: Initial model with basic fields
- 2024-01-16: Added location fields (lat/long/timezone)
- 2024-01-17: Added denormalized counters for performance
- 2024-01-18: Added cascade delete for child entities
- 2024-01-19: Added to_dict method for API serialization

DEPENDENCIES:
- sqlalchemy: ORM mappings and relationships
- .base: BaseEntity for common fields and timestamps

USAGE:
# Create a house:
house = House(
    name="Smith Residence",
    address="123 Main St",
    timezone="America/New_York"
)

# Access relationships:
for room in house.rooms:
    print(f"Room: {room.name}")
"""

from typing import Optional

from sqlalchemy import Column, Float, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base, BaseEntity


class House(Base, BaseEntity):
    """House entity - represents a single home."""
    
    __tablename__ = "houses"
    
    # Basic attributes
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    
    # Location
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timezone = Column(String(50), nullable=True, default="UTC")
    
    # Denormalized counters for performance
    room_count = Column(Integer, nullable=False, default=0)
    device_count = Column(Integer, nullable=False, default=0)
    user_count = Column(Integer, nullable=False, default=0)
    
    # Settings as JSON
    settings_json = Column(Text, nullable=True)
    
    # Relationships
    rooms = relationship("Room", back_populates="house", cascade="all, delete-orphan")
    users = relationship("User", back_populates="house", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<House(id={self.id}, name='{self.name}', rooms={self.room_count})>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "sync_id": self.sync_id,
            "name": self.name,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone,
            "room_count": self.room_count,
            "device_count": self.device_count,
            "user_count": self.user_count,
            "settings_json": self.settings_json,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "is_deleted": self.is_deleted,
        }