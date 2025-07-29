"""Client-side Device repository."""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .base import ClientBaseRepository
from ..models.device import ClientDevice, ClientDeviceType


class ClientDeviceRepository(ClientBaseRepository[ClientDevice]):
    """Repository for client-side device operations."""
    
    def __init__(self, session):
        super().__init__(ClientDevice, session)
        
    async def get_by_room(self, room_id: str) -> List[ClientDevice]:
        """Get all devices in a room."""
        result = await self.session.execute(
            select(ClientDevice).where(ClientDevice.room_id == room_id)
        )
        return list(result.scalars().all())
        
    async def get_by_type(self, device_type: ClientDeviceType) -> List[ClientDevice]:
        """Get all devices of a specific type."""
        result = await self.session.execute(
            select(ClientDevice).where(ClientDevice.device_type == device_type)
        )
        return list(result.scalars().all())
        
    async def get_with_states(self, id: str) -> Optional[ClientDevice]:
        """Get device with states loaded."""
        result = await self.session.execute(
            select(ClientDevice)
            .where(ClientDevice.id == id)
            .options(selectinload(ClientDevice.states))
        )
        return result.scalar_one_or_none()