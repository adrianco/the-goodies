"""Client-side User model with sync tracking."""

from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, ClientTimestampMixin


class ClientUser(Base, ClientTimestampMixin):
    """Client-side representation of a user."""
    
    __tablename__ = "client_users"
    
    id = Column(String(50), primary_key=True)
    house_id = Column(String(50), ForeignKey("client_houses.id"), nullable=False)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    role = Column(String(50), default="member")
    preferences = Column(Text, nullable=True)  # JSON string
    metadata_json = Column(Text, nullable=True)  # JSON string
    
    # Relationships
    house = relationship("ClientHouse", back_populates="users")
    events = relationship("ClientEvent", back_populates="user", cascade="all, delete-orphan")
    
    def to_sync_dict(self):
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "house_id": self.house_id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "preferences": self.preferences,
            "metadata": self.metadata_json,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }