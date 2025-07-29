"""Client-side EntityState model with sync tracking."""

from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base, ClientTimestampMixin


class ClientEntityState(Base, ClientTimestampMixin):
    """Client-side representation of entity state."""
    
    __tablename__ = "client_entity_states"
    
    id = Column(String(50), primary_key=True)
    entity_id = Column(String(50), ForeignKey("client_devices.id"), nullable=False)
    entity_type = Column(String(50), default="device")
    state = Column(Text, nullable=False)  # JSON string
    attributes = Column(Text, nullable=True)  # JSON string
    metadata_json = Column(Text, nullable=True)  # JSON string
    
    # Relationships
    device = relationship("ClientDevice", back_populates="states")
    
    def to_sync_dict(self):
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "state": self.state,
            "attributes": self.attributes,
            "metadata": self.metadata_json,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }