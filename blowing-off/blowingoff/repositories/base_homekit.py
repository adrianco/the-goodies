"""
Base repository for HomeKit models.
"""

from typing import TypeVar, Generic, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import Base

T = TypeVar("T", bound=Base)


class HomeKitBaseRepository(Generic[T]):
    """Base repository for HomeKit entities."""
    
    def __init__(self, model: T, session: AsyncSession):
        self.model = model
        self.session = session
        
    async def get(self, id: str) -> Optional[T]:
        """Get entity by ID."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
        
    async def get_all(self, limit: int = 100) -> List[T]:
        """Get all entities with limit."""
        result = await self.session.execute(
            select(self.model).limit(limit)
        )
        return list(result.scalars().all())
        
    async def create(self, **kwargs) -> T:
        """Create new entity."""
        entity = self.model(**kwargs)
        self.session.add(entity)
        await self.session.flush()
        return entity
        
    async def update(self, id: str, **kwargs) -> Optional[T]:
        """Update entity."""
        entity = await self.get(id)
        if not entity:
            return None
            
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
                
        entity.updated_at = datetime.utcnow()
        await self.session.flush()
        return entity
        
    async def delete(self, id: str) -> bool:
        """Delete entity."""
        entity = await self.get(id)
        if not entity:
            return False
            
        await self.session.delete(entity)
        await self.session.flush()
        return True