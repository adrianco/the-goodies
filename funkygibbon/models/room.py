"""
Room model - represents rooms within a house.
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