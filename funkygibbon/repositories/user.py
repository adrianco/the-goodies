"""
User repository.
"""

from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inbetweenies.models import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User entities."""
    
    def __init__(self):
        super().__init__(User)
    
    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[User]:
        """Get user by name."""
        stmt = select(User).where(
            and_(
                User.name == name,
                True  # Models don't have is_deleted
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_home(self, db: AsyncSession, home_id: str) -> List[User]:
        """Get all users in a home."""
        stmt = select(User).where(
            and_(
                User.home_id == home_id,
                True  # Models don't have is_deleted
            )
        ).order_by(User.is_owner.desc(), User.is_administrator.desc(), User.name)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_admins(self, db: AsyncSession, home_id: str) -> List[User]:
        """Get all admin users in a home."""
        stmt = select(User).where(
            and_(
                User.home_id == home_id,
                User.is_administrator == True,
                True  # Models don't have is_deleted
            )
        )
        
        result = await db.execute(stmt)
        return list(result.scalars().all())