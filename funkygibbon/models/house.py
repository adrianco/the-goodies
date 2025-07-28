"""
House model - top level entity in the knowledge graph.
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