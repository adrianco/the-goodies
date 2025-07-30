"""Client-side Room repository."""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .base import ClientBaseRepository
from ..models import Room as ClientRoom


class ClientRoomRepository(ClientBaseRepository[ClientRoom]):
    """Repository for client-side room operations."""
    
    def __init__(self, session):
        super().__init__(ClientRoom, session)
        
    async def get_by_home(self, home_id: str) -> List[ClientRoom]:
        """Get all rooms for a home."""
        result = await self.session.execute(
            select(ClientRoom).where(ClientRoom.home_id == home_id)
        )
        return list(result.scalars().all())
        
    async def get_with_accessories(self, id: str) -> Optional[ClientRoom]:
        """Get room with accessories loaded."""
        result = await self.session.execute(
            select(ClientRoom)
            .where(ClientRoom.id == id)
            .options(selectinload(ClientRoom.accessories))
        )
        return result.scalar_one_or_none()