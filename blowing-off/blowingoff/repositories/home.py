"""Client-side Home repository."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .base import ClientBaseRepository
from ..models import Home as ClientHome


class ClientHomeRepository(ClientBaseRepository[ClientHome]):
    """Repository for client-side home operations."""
    
    def __init__(self, session):
        super().__init__(ClientHome, session)
        
    async def get_with_rooms(self, id: str) -> Optional[ClientHome]:
        """Get home with rooms loaded."""
        result = await self.session.execute(
            select(ClientHome)
            .where(ClientHome.id == id)
            .options(selectinload(ClientHome.rooms))
        )
        return result.scalar_one_or_none()
        
    async def get_with_all(self, id: str) -> Optional[ClientHome]:
        """Get home with all relationships loaded."""
        result = await self.session.execute(
            select(ClientHome)
            .where(ClientHome.id == id)
            .options(
                selectinload(ClientHome.rooms),
                selectinload(ClientHome.users)
            )
        )
        return result.scalar_one_or_none()