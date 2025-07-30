"""Shared Room model (HomeKit HMRoom equivalent)."""

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, InbetweeniesTimestampMixin


class Room(Base, InbetweeniesTimestampMixin):
    """
    Represents a HomeKit Room (HMRoom).
    Simplified to match what HomeKit provides.
    """
    
    __tablename__ = "rooms"
    
    # HomeKit HMRoom properties
    id = Column(String(36), primary_key=True)  # UUID
    home_id = Column(String(36), ForeignKey("homes.id"), nullable=False)
    name = Column(String(255), nullable=False)
    
    # Relationships
    home = relationship("Home", back_populates="rooms")
    accessories = relationship("Accessory", secondary="accessory_rooms", back_populates="rooms")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "home_id": self.home_id,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }