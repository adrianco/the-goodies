"""
User model - represents household members.
"""

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from .base import Base, BaseEntity


class User(Base, BaseEntity):
    """User entity - represents a household member."""
    
    __tablename__ = "users"
    
    # Foreign keys
    house_id = Column(String(36), ForeignKey("houses.id"), nullable=False)
    
    # Basic attributes
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True, unique=True)
    role = Column(String(50), nullable=False, default="member")  # admin, member, guest
    
    # Device tracking
    device_ids_json = Column(Text, nullable=True)  # JSON array of device IDs
    
    # Preferences as JSON
    preferences_json = Column(Text, nullable=True)
    
    # Relationships
    house = relationship("House", back_populates="users")
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, name='{self.name}', role='{self.role}')>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "sync_id": self.sync_id,
            "house_id": self.house_id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "device_ids_json": self.device_ids_json,
            "preferences_json": self.preferences_json,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "is_deleted": self.is_deleted,
        }