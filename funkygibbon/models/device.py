"""
Device model - represents smart home devices.
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