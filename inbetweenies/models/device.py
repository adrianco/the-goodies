"""Shared Device model for Inbetweenies protocol."""

from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, InbetweeniesTimestampMixin


class Device(Base, InbetweeniesTimestampMixin):
    """A smart device within a room."""
    
    __tablename__ = "devices"
    
    id = Column(String(50), primary_key=True)
    room_id = Column(String(50), ForeignKey("rooms.id"), nullable=False)
    house_id = Column(String(50), ForeignKey("houses.id"), nullable=False)
    
    # Basic attributes
    name = Column(String(255), nullable=False)
    room_name = Column(String(255), nullable=False)
    house_name = Column(String(255), nullable=False)
    device_type = Column(String(50), nullable=False)
    manufacturer = Column(String(255), nullable=True)
    model = Column(String(255), nullable=True)
    
    # Device state as JSON (flexible for different device types)
    state_json = Column(Text, nullable=True)
    capabilities_json = Column(Text, nullable=True)
    
    # Network info
    ip_address = Column(String(45), nullable=True)
    mac_address = Column(String(17), nullable=True)
    
    metadata_json = Column(Text, nullable=True)
    
    # Relationships
    room = relationship("Room", back_populates="devices")
    states = relationship("EntityState", back_populates="device", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="device", cascade="all, delete-orphan")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for sync/API responses."""
        return {
            "id": self.id,
            "room_id": self.room_id,
            "house_id": self.house_id,
            "name": self.name,
            "room_name": self.room_name,
            "house_name": self.house_name,
            "device_type": self.device_type,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "state_json": self.state_json,
            "capabilities_json": self.capabilities_json,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id,
            "version": self.version,
            "is_deleted": self.is_deleted
        }