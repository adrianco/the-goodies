"""Client-side Event repository."""

from typing import List
from datetime import datetime
from sqlalchemy import select, desc, and_
from .base import ClientBaseRepository
from ..models.event import ClientEvent


class ClientEventRepository(ClientBaseRepository[ClientEvent]):
    """Repository for client-side event operations."""
    
    def __init__(self, session):
        super().__init__(ClientEvent, session)
        
    async def get_by_entity(self, entity_id: str, limit: int = 100) -> List[ClientEvent]:
        """Get events for an entity."""
        result = await self.session.execute(
            select(ClientEvent)
            .where(ClientEvent.entity_id == entity_id)
            .order_by(desc(ClientEvent.occurred_at))
            .limit(limit)
        )
        return list(result.scalars().all())
        
    async def get_by_user(self, user_id: str, limit: int = 100) -> List[ClientEvent]:
        """Get events for a user."""
        result = await self.session.execute(
            select(ClientEvent)
            .where(ClientEvent.user_id == user_id)
            .order_by(desc(ClientEvent.occurred_at))
            .limit(limit)
        )
        return list(result.scalars().all())
        
    async def get_recent(self, since: datetime) -> List[ClientEvent]:
        """Get recent events."""
        result = await self.session.execute(
            select(ClientEvent)
            .where(ClientEvent.occurred_at > since)
            .order_by(desc(ClientEvent.occurred_at))
        )
        return list(result.scalars().all())