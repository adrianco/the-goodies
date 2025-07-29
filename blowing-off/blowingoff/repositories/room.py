"""Client-side Room repository."""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .base import ClientBaseRepository
from ..models.room import ClientRoom


class ClientRoomRepository(ClientBaseRepository[ClientRoom]):
    """Repository for client-side room operations."""
    
    def __init__(self, session):
        super().__init__(ClientRoom, session)
        
    async def get_by_house(self, house_id: str) -> List[ClientRoom]:
        """Get all rooms for a house."""
        result = await self.session.execute(
            select(ClientRoom).where(ClientRoom.house_id == house_id)
        )
        return list(result.scalars().all())
        
    async def get_with_devices(self, id: str) -> Optional[ClientRoom]:
        """Get room with devices loaded."""
        result = await self.session.execute(
            select(ClientRoom)
            .where(ClientRoom.id == id)
            .options(selectinload(ClientRoom.devices))
        )
        return result.scalar_one_or_none()