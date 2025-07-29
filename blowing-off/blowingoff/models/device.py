"""Client-side Device models with sync tracking."""

from sqlalchemy import Column, String, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
from .base import Base, ClientTimestampMixin


class ClientDeviceType(enum.Enum):
    """Device types matching server."""
    LIGHT = "light"
    SWITCH = "switch"
    SENSOR = "sensor"
    THERMOSTAT = "thermostat"
    LOCK = "lock"
    CAMERA = "camera"
    SPEAKER = "speaker"
    OTHER = "other"


class ClientDevice(Base, ClientTimestampMixin):
    """Client-side representation of a device."""
    
    __tablename__ = "client_devices"
    
    id = Column(String(50), primary_key=True)
    room_id = Column(String(50), ForeignKey("client_rooms.id"), nullable=False)
    name = Column(String(100), nullable=False)
    device_type = Column(Enum(ClientDeviceType), nullable=False)
    manufacturer = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    capabilities = Column(Text, nullable=True)  # JSON string
    configuration = Column(Text, nullable=True)  # JSON string
    metadata_json = Column(Text, nullable=True)  # JSON string
    
    # Relationships
    room = relationship("ClientRoom", back_populates="devices")
    states = relationship("ClientEntityState", back_populates="device", cascade="all, delete-orphan")
    events = relationship("ClientEvent", back_populates="device", cascade="all, delete-orphan")
    
    def to_sync_dict(self):
        """Convert to dictionary for sync."""
        return {
            "id": self.id,
            "room_id": self.room_id,
            "name": self.name,
            "device_type": self.device_type.value,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "capabilities": self.capabilities,
            "configuration": self.configuration,
            "metadata": self.metadata_json,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }