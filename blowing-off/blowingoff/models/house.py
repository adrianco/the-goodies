"""Client-side House model with sync tracking."""

from sqlalchemy import Column, String, Text
from sqlalchemy.orm import relationship
from .base import Base, ClientTimestampMixin


class ClientHouse(Base, ClientTimestampMixin):
    """Client-side representation of a house."""
    
    __tablename__ = "client_houses"
    
    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    address = Column(Text, nullable=True)
    timezone = Column(String(50), default="UTC")
    metadata_json = Column(Text, nullable=True)  # JSON string
    
    # Relationships
    rooms = relationship("ClientRoom", back_populates="house", cascade="all, delete-orphan")
    users = relationship("ClientUser", back_populates="house", cascade="all, delete-orphan")
    
    def to_sync_dict(self):
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "timezone": self.timezone,
            "metadata": self.metadata_json,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }