"""Client-side Accessory repository."""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .base import ClientBaseRepository
from ..models import Accessory as ClientAccessory
# ClientDeviceType removed - using HomeKit model


class ClientAccessoryRepository(ClientBaseRepository[ClientAccessory]):
    """Repository for client-side accessory operations."""
    
    def __init__(self, session):
        super().__init__(ClientAccessory, session)
        
    async def get_by_room(self, room_id: str) -> List[ClientAccessory]:
        """Get all accessories in a room."""
        result = await self.session.execute(
            select(ClientAccessory).where(ClientAccessory.room_id == room_id)
        )
        return list(result.scalars().all())
        
    # ClientDeviceType removed for HomeKit focus
    # async def get_by_type(self, device_type: ClientDeviceType) -> List[ClientDevice]:
    #     """Get all devices of a specific type."""
    #     result = await self.session.execute(
    #         select(ClientDevice).where(ClientDevice.device_type == device_type)
    #     )
    #     return list(result.scalars().all())
        
    async def get_with_states(self, id: str) -> Optional[ClientAccessory]:
        """Get accessory with states loaded."""
        result = await self.session.execute(
            select(ClientAccessory)
            .where(ClientAccessory.id == id)
            .options(selectinload(ClientAccessory.states))
        )
        return result.scalar_one_or_none()