"""Shared User model (HomeKit HMUser equivalent)."""

from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, InbetweeniesTimestampMixin


class User(Base, InbetweeniesTimestampMixin):
    """
    Represents a HomeKit User (HMUser).
    Simplified to match HomeKit's user management.
    """
    
    __tablename__ = "users"
    
    # HomeKit HMUser properties
    id = Column(String(36), primary_key=True)  # UUID
    home_id = Column(String(36), ForeignKey("homes.id"), nullable=False)
    name = Column(String(255), nullable=False)
    
    # HomeKit user types/permissions
    is_administrator = Column(Boolean, nullable=False, default=False)
    is_owner = Column(Boolean, nullable=False, default=False)
    remote_access_allowed = Column(Boolean, nullable=False, default=True)
    
    # Relationships
    home = relationship("Home", back_populates="users")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "home_id": self.home_id,
            "name": self.name,
            "is_administrator": self.is_administrator,
            "is_owner": self.is_owner,
            "remote_access_allowed": self.remote_access_allowed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }