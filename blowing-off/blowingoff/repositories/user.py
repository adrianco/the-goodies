"""Client-side User repository."""

from typing import List, Optional
from sqlalchemy import select
from .base import ClientBaseRepository
from ..models.user import ClientUser


class ClientUserRepository(ClientBaseRepository[ClientUser]):
    """Repository for client-side user operations."""
    
    def __init__(self, session):
        super().__init__(ClientUser, session)
        
    async def get_by_house(self, house_id: str) -> List[ClientUser]:
        """Get all users in a house."""
        result = await self.session.execute(
            select(ClientUser).where(ClientUser.house_id == house_id)
        )
        return list(result.scalars().all())
        
    async def get_by_email(self, email: str) -> Optional[ClientUser]:
        """Get user by email."""
        result = await self.session.execute(
            select(ClientUser).where(ClientUser.email == email)
        )
        return result.scalar_one_or_none()