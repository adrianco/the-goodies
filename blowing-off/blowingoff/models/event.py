"""Client-side Event model with sync tracking."""

from sqlalchemy import Column, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from .base import Base, ClientTimestampMixin


class ClientEvent(Base, ClientTimestampMixin):
    """Client-side representation of an event."""
    
    __tablename__ = "client_events"
    
    id = Column(String(50), primary_key=True)
    entity_id = Column(String(50), ForeignKey("client_devices.id"), nullable=True)
    user_id = Column(String(50), ForeignKey("client_users.id"), nullable=True)
    event_type = Column(String(100), nullable=False)
    event_data = Column(Text, nullable=True)  # JSON string
    occurred_at = Column(DateTime, nullable=False)
    metadata_json = Column(Text, nullable=True)  # JSON string
    
    # Relationships
    device = relationship("ClientDevice", back_populates="events")
    user = relationship("ClientUser", back_populates="events")
    
    def to_sync_dict(self):
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "event_data": self.event_data,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "metadata": self.metadata_json,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }