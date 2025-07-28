"""
Entity State model - time-series state tracking for devices.
"""

from sqlalchemy import Column, ForeignKey, Integer, String, Text

from .base import Base, TimestampMixin


class EntityState(Base, TimestampMixin):
    """Entity state - tracks device states over time."""
    
    __tablename__ = "entity_states"
    
    # Primary key is just an auto-incrementing integer for time-series data
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False)
    
    # State data
    state_type = Column(String(50), nullable=False)  # on_off, temperature, motion, etc
    state_value = Column(String(255), nullable=False)
    state_json = Column(Text, nullable=True)  # Additional state details
    
    # Source tracking
    source = Column(String(50), nullable=True)  # user, automation, device
    user_id = Column(String(36), nullable=True)
    
    # Relationships
    from sqlalchemy.orm import relationship
    device = relationship("Device", back_populates="entity_states")
    
    def __repr__(self) -> str:
        return f"<EntityState(id={self.id}, device_id='{self.device_id}', type='{self.state_type}')>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "device_id": self.device_id,
            "state_type": self.state_type,
            "state_value": self.state_value,
            "state_json": self.state_json,
            "source": self.source,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }