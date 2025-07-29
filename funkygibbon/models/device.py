"""
FunkyGibbon - Device Model (Smart Home Devices)

DEVELOPMENT CONTEXT:
Created in January 2024 as part of the core smart home entity hierarchy.
Devices are the primary entities users interact with - lights, switches,
sensors, etc. The model is designed to be flexible enough to support
various device types while maintaining performance at scale (~300 devices).

FUNCTIONALITY:
- Represents any smart home device (lights, switches, sensors, thermostats)
- Belongs to a room and house with denormalized names for performance
- Stores device state and capabilities as JSON for flexibility
- Tracks network information (IP/MAC) for debugging and discovery
- Maintains relationships to entity states for state history
- Supports manufacturer/model info for device identification

PURPOSE:
Central to the smart home system - devices are what users control and
monitor. The flexible JSON fields allow supporting new device types
without schema changes, critical for the evolving IoT ecosystem.

KNOWN ISSUES:
- state_json and capabilities_json are Text not JSON (SQLite compatibility)
- No validation on device_type values (should use enum)
- IP/MAC address formats aren't validated
- Denormalized room/house names can become stale
- No foreign key indexes on room_id/house_id for performance

REVISION HISTORY:
- 2024-01-15: Initial model with basic device fields
- 2024-01-16: Added state_json for flexible state storage
- 2024-01-17: Added denormalized room/house names for query performance
- 2024-01-18: Added network info fields (IP/MAC addresses)
- 2024-01-19: Added capabilities_json for device feature discovery

DEPENDENCIES:
- sqlalchemy: ORM mappings and relationships
- .base: BaseEntity for common fields and timestamps

USAGE:
# Create a device:
device = Device(
    name="Living Room Light",
    device_type="light",
    room_id=room.id,
    house_id=house.id,
    room_name=room.name,  # Denormalized
    house_name=house.name,  # Denormalized
    state_json='{"on": true, "brightness": 80}',
    capabilities_json='{"dimmable": true, "color": false}'
)

# Query devices by type:
lights = session.query(Device).filter_by(device_type="light").all()
"""

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from .base import Base, BaseEntity


class Device(Base, BaseEntity):
    """Device entity - represents a smart home device."""
    
    __tablename__ = "devices"
    
    # Foreign keys
    room_id = Column(String(36), ForeignKey("rooms.id"), nullable=False)
    house_id = Column(String(36), ForeignKey("houses.id"), nullable=False)
    
    # Basic attributes
    name = Column(String(255), nullable=False)
    device_type = Column(String(50), nullable=False)  # light, switch, sensor, etc
    manufacturer = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    
    # Denormalized for performance
    room_name = Column(String(255), nullable=False)
    house_name = Column(String(255), nullable=False)
    
    # Device state as JSON (flexible for different device types)
    state_json = Column(Text, nullable=True)
    capabilities_json = Column(Text, nullable=True)
    
    # Network info
    ip_address = Column(String(45), nullable=True)
    mac_address = Column(String(17), nullable=True)
    
    # Relationships
    room = relationship("Room", back_populates="devices")
    entity_states = relationship("EntityState", back_populates="device", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Device(id={self.id}, name='{self.name}', type='{self.device_type}')>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "sync_id": self.sync_id,
            "room_id": self.room_id,
            "house_id": self.house_id,
            "room_name": self.room_name,
            "house_name": self.house_name,
            "name": self.name,
            "device_type": self.device_type,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "state_json": self.state_json,
            "capabilities_json": self.capabilities_json,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "is_deleted": self.is_deleted,
        }