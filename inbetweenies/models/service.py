"""Shared Service model (HomeKit HMService equivalent)."""

from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, InbetweeniesTimestampMixin


class Service(Base, InbetweeniesTimestampMixin):
    """
    Represents a HomeKit Service (HMService).
    Services define what an accessory can do (e.g., lightbulb, thermostat).
    """
    
    __tablename__ = "services"
    
    # HomeKit HMService properties
    id = Column(String(36), primary_key=True)  # UUID
    accessory_id = Column(String(36), ForeignKey("accessories.id"), nullable=False)
    service_type = Column(String(100), nullable=False)  # e.g., "lightbulb", "thermostat"
    name = Column(String(255), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    is_user_interactive = Column(Boolean, nullable=False, default=True)
    
    # Relationships
    accessory = relationship("Accessory", back_populates="services")
    characteristics = relationship("Characteristic", back_populates="service", cascade="all, delete-orphan")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "accessory_id": self.accessory_id,
            "service_type": self.service_type,
            "name": self.name,
            "is_primary": self.is_primary,
            "is_user_interactive": self.is_user_interactive,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }