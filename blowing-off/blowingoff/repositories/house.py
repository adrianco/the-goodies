"""Client-side House repository."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .base import ClientBaseRepository
from ..models.house import ClientHouse


class ClientHouseRepository(ClientBaseRepository[ClientHouse]):
    """Repository for client-side house operations."""
    
    def __init__(self, session):
        super().__init__(ClientHouse, session)
        
    async def get_with_rooms(self, id: str) -> Optional[ClientHouse]:
        """Get house with rooms loaded."""
        result = await self.session.execute(
            select(ClientHouse)
            .where(ClientHouse.id == id)
            .options(selectinload(ClientHouse.rooms))
        )
        return result.scalar_one_or_none()
        
    async def get_with_all(self, id: str) -> Optional[ClientHouse]:
        """Get house with all relationships loaded."""
        result = await self.session.execute(
            select(ClientHouse)
            .where(ClientHouse.id == id)
            .options(
                selectinload(ClientHouse.rooms),
                selectinload(ClientHouse.users)
            )
        )
        return result.scalar_one_or_none()