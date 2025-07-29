"""Client-side EntityState repository."""

from typing import List, Optional
from sqlalchemy import select, desc
from .base import ClientBaseRepository
from ..models.entity_state import ClientEntityState


class ClientEntityStateRepository(ClientBaseRepository[ClientEntityState]):
    """Repository for client-side entity state operations."""
    
    def __init__(self, session):
        super().__init__(ClientEntityState, session)
        
    async def get_by_entity(self, entity_id: str) -> List[ClientEntityState]:
        """Get all states for an entity."""
        result = await self.session.execute(
            select(ClientEntityState)
            .where(ClientEntityState.entity_id == entity_id)
            .order_by(desc(ClientEntityState.updated_at))
        )
        return list(result.scalars().all())
        
    async def get_latest_by_entity(self, entity_id: str) -> Optional[ClientEntityState]:
        """Get latest state for an entity."""
        result = await self.session.execute(
            select(ClientEntityState)
            .where(ClientEntityState.entity_id == entity_id)
            .order_by(desc(ClientEntityState.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()