"""
Inbetweenies Protocol - Home Model (HomeKit HMHome)

DEVELOPMENT CONTEXT:
Created in July 2025 as part of the shared model migration. This model
represents a Home in the HomeKit sense - the top-level container for
all smart home data. Replaces the previous House model.

FUNCTIONALITY:
- Represents a HomeKit home (HMHome)
- Primary home designation
- Relationships to rooms, accessories, and users
- Sync tracking via InbetweeniesTimestampMixin

PURPOSE:
Provides the root entity for the smart home hierarchy. Each deployment
typically has one primary home, though the model supports multiple homes
for future expansion.

KNOWN ISSUES:
- No validation for single primary home
- Missing HomeKit zone support

REVISION HISTORY:
- 2025-07-28: Created as House model
- 2025-07-29: Renamed to Home for HomeKit
- 2025-07-29: Removed non-HomeKit fields

DEPENDENCIES:
- .base: Base classes and mixins
- sqlalchemy: ORM relationships
"""

from sqlalchemy import Column, String, Boolean
from sqlalchemy.orm import relationship
from .base import Base, InbetweeniesTimestampMixin


class Home(Base, InbetweeniesTimestampMixin):
    """
    Represents a HomeKit Home (HMHome).
    Simplified to match what HomeKit provides.
    """
    
    __tablename__ = "homes"
    
    # HomeKit HMHome properties
    id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(255), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    
    # Relationships
    rooms = relationship("Room", back_populates="home", cascade="all, delete-orphan")
    accessories = relationship("Accessory", back_populates="home", cascade="all, delete-orphan")
    users = relationship("User", back_populates="home", cascade="all, delete-orphan")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "name": self.name,
            "is_primary": self.is_primary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }