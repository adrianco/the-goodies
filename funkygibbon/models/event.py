"""
Event model - audit log and automation triggers.
"""

from sqlalchemy import Column, Integer, String, Text

from .base import Base, TimestampMixin


class Event(Base, TimestampMixin):
    """Event entity - audit log and automation triggers."""
    
    __tablename__ = "events"
    
    # Primary key is just an auto-incrementing integer for time-series data
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Event details
    event_type = Column(String(50), nullable=False)  # device_added, state_changed, etc
    entity_type = Column(String(50), nullable=False)  # house, room, device, user
    entity_id = Column(String(36), nullable=False)
    
    # Event data
    description = Column(Text, nullable=True)
    data_json = Column(Text, nullable=True)
    
    # Source tracking
    source = Column(String(50), nullable=True)  # user, system, automation
    user_id = Column(String(36), nullable=True)
    
    def __repr__(self) -> str:
        return f"<Event(id={self.id}, type='{self.event_type}', entity='{self.entity_type}')>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "description": self.description,
            "data_json": self.data_json,
            "source": self.source,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }