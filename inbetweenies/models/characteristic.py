"""Shared Characteristic model (HomeKit HMCharacteristic equivalent)."""

from sqlalchemy import Column, String, Text, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, InbetweeniesTimestampMixin


class Characteristic(Base, InbetweeniesTimestampMixin):
    """
    Represents a HomeKit Characteristic (HMCharacteristic).
    Characteristics are the properties of a service (e.g., on/off, brightness, temperature).
    """
    
    __tablename__ = "characteristics"
    
    # HomeKit HMCharacteristic properties
    id = Column(String(36), primary_key=True)  # UUID
    service_id = Column(String(36), ForeignKey("services.id"), nullable=False)
    characteristic_type = Column(String(100), nullable=False)  # e.g., "power_state", "brightness"
    
    # Value fields - use appropriate type based on characteristic
    value = Column(Text, nullable=True)  # Stored as JSON string for flexibility
    
    # Metadata
    format = Column(String(50), nullable=True)  # bool, uint8, float, string, etc.
    unit = Column(String(50), nullable=True)  # celsius, percentage, lux, etc.
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    step_value = Column(Float, nullable=True)
    
    # Permissions
    is_readable = Column(Boolean, nullable=False, default=True)
    is_writable = Column(Boolean, nullable=False, default=True)
    supports_event_notification = Column(Boolean, nullable=False, default=True)
    
    # Relationships
    service = relationship("Service", back_populates="characteristics")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "service_id": self.service_id,
            "characteristic_type": self.characteristic_type,
            "value": self.value,
            "format": self.format,
            "unit": self.unit,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step_value": self.step_value,
            "is_readable": self.is_readable,
            "is_writable": self.is_writable,
            "supports_event_notification": self.supports_event_notification,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }