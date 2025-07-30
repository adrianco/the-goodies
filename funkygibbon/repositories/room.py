"""
Room repository with accessory management.
"""

from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from inbetweenies.models import Room
from .base import BaseRepository


class RoomRepository(BaseRepository[Room]):
    """Repository for Room entities."""
    
    def __init__(self):
        super().__init__(Room)
    
    async def get_by_home(self, db: AsyncSession, home_id: str) -> List[Room]:
        """Get all rooms in a home."""
        stmt = select(Room).where(
            and_(
                Room.home_id == home_id,
                True  # Models don't have is_deleted
            )
        ).order_by(Room.name)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_with_accessories(self, db: AsyncSession, id: str) -> Optional[Room]:
        """Get room with all accessories loaded."""
        stmt = select(Room).where(
            and_(
                Room.id == id,
                True  # Models don't have is_deleted
            )
        ).options(selectinload(Room.accessories))
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def create_with_home_name(
        self, 
        db: AsyncSession, 
        home_id: str,
        home_name: str,
        **kwargs
    ) -> Room:
        """Create room with denormalized home name."""
        kwargs["home_id"] = home_id
        # Note: home_name is not stored in the simplified Room model
        kwargs.pop("home_name", None)  # Remove if passed
        return await self.create(db, **kwargs)