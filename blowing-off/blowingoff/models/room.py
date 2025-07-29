"""Client-side Room model with sync tracking."""

from sqlalchemy import Column, String, Integer, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, ClientTimestampMixin


class ClientRoom(Base, ClientTimestampMixin):
    """Client-side representation of a room."""
    
    __tablename__ = "client_rooms"
    
    id = Column(String(50), primary_key=True)
    house_id = Column(String(50), ForeignKey("client_houses.id"), nullable=False)
    name = Column(String(100), nullable=False)
    floor = Column(Integer, default=0)
    room_type = Column(String(50), nullable=True)
    metadata_json = Column(Text, nullable=True)  # JSON string
    
    # Relationships
    house = relationship("ClientHouse", back_populates="rooms")
    devices = relationship("ClientDevice", back_populates="room", cascade="all, delete-orphan")
    
    def to_sync_dict(self):
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "house_id": self.house_id,
            "name": self.name,
            "floor": self.floor,
            "room_type": self.room_type,
            "metadata": self.metadata_json,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }