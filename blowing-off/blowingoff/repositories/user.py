"""Client-side User repository."""

from typing import List, Optional
from sqlalchemy import select
from .base import ClientBaseRepository
from ..models import User as ClientUser


class ClientUserRepository(ClientBaseRepository[ClientUser]):
    """Repository for client-side user operations."""
    
    def __init__(self, session):
        super().__init__(ClientUser, session)
        
    async def get_by_home(self, home_id: str) -> List[ClientUser]:
        """Get all users in a home."""
        result = await self.session.execute(
            select(ClientUser).where(ClientUser.home_id == home_id)
        )
        return list(result.scalars().all())
