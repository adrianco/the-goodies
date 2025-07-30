"""
Inbetweenies Protocol - Accessory Model (HomeKit HMAccessory)

DEVELOPMENT CONTEXT:
Created in July 2025 as part of the shared model migration. This model
represents an Accessory in the HomeKit sense - a physical smart home
device. Replaces the previous Device model with HomeKit-compatible fields.

FUNCTIONALITY:
- Represents a HomeKit accessory (HMAccessory)
- Manufacturer, model, and firmware tracking
- Reachability and blocking status
- Bridge accessory support
- Many-to-many room associations
- Service and characteristic relationships

PURPOSE:
Models individual smart home devices in a way that's directly compatible
with HomeKit's accessory structure. This enables native iOS integration
without field mapping or translation.

KNOWN ISSUES:
- No category field (HomeKit has this)
- Missing configuration URL support
- No accessory delegate support

REVISION HISTORY:
- 2025-07-28: Created as Device model
- 2025-07-29: Renamed to Accessory for HomeKit
- 2025-07-29: Added HomeKit-specific fields
- 2025-07-29: Added many-to-many room support

DEPENDENCIES:
- .base: Base classes and mixins
- sqlalchemy: ORM relationships
"""

from sqlalchemy import Column, String, Boolean, Table, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, InbetweeniesTimestampMixin

# Association table for many-to-many relationship between accessories and rooms
accessory_rooms = Table(
    'accessory_rooms',
    Base.metadata,
    Column('accessory_id', String(36), ForeignKey('accessories.id'), primary_key=True),
    Column('room_id', String(36), ForeignKey('rooms.id'), primary_key=True)
)


class Accessory(Base, InbetweeniesTimestampMixin):
    """
    Represents a HomeKit Accessory (HMAccessory).
    In HomeKit, an accessory is a physical device that provides services.
    """
    
    __tablename__ = "accessories"
    
    # HomeKit HMAccessory properties
    id = Column(String(36), primary_key=True)  # UUID
    home_id = Column(String(36), ForeignKey("homes.id"), nullable=False)
    name = Column(String(255), nullable=False)
    manufacturer = Column(String(255), nullable=True)
    model = Column(String(255), nullable=True)
    serial_number = Column(String(255), nullable=True)
    firmware_version = Column(String(50), nullable=True)
    is_reachable = Column(Boolean, nullable=False, default=True)
    is_blocked = Column(Boolean, nullable=False, default=False)
    
    # Bridge info (if this accessory is accessed through a bridge)
    is_bridge = Column(Boolean, nullable=False, default=False)
    bridge_id = Column(String(36), ForeignKey("accessories.id"), nullable=True)
    
    # Relationships
    home = relationship("Home", back_populates="accessories")
    rooms = relationship("Room", secondary=accessory_rooms, back_populates="accessories")
    services = relationship("Service", back_populates="accessory", cascade="all, delete-orphan")
    bridged_accessories = relationship("Accessory", backref="bridge", remote_side=[id])
    
    def to_dict(self) -> dict:
        """Convert to dictionary for sync."""
        # Note: Don't access relationships here to avoid lazy loading in async context
        return {
            "id": self.id,
            "home_id": self.home_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "firmware_version": self.firmware_version,
            "is_reachable": self.is_reachable,
            "is_blocked": self.is_blocked,
            "is_bridge": self.is_bridge,
            "bridge_id": self.bridge_id,
            # Don't include room_ids to avoid lazy loading
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }