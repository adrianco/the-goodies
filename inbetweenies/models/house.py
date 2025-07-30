"""Shared House model for Inbetweenies protocol."""

from sqlalchemy import Column, String, Float, Integer, Text
from sqlalchemy.orm import relationship
from .base import Base, InbetweeniesTimestampMixin


class House(Base, InbetweeniesTimestampMixin):
    """A smart home location."""
    
    __tablename__ = "houses"
    
    id = Column(String(50), primary_key=True)
    
    # Basic attributes
    name = Column(String(255), nullable=False)
    address = Column(String(500), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timezone = Column(String(50), nullable=False, default="UTC")
    
    # Counts for quick access
    room_count = Column(Integer, nullable=False, default=0)
    device_count = Column(Integer, nullable=False, default=0) 
    user_count = Column(Integer, nullable=False, default=0)
    
    # JSON fields
    settings_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    
    # Relationships
    rooms = relationship("Room", back_populates="house", cascade="all, delete-orphan")
    users = relationship("User", back_populates="house", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="house", cascade="all, delete-orphan")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for sync/API responses."""
        return {
            "id": self.id,
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id,
            "version": self.version,
            "is_deleted": self.is_deleted
        }