"""
User repository.
"""

from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User entities."""
    
    def __init__(self):
        super().__init__(User)
    
    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email."""
        stmt = select(User).where(
            and_(
                User.email == email,
                User.is_deleted == False
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_house(self, db: AsyncSession, house_id: str) -> List[User]:
        """Get all users in a house."""
        stmt = select(User).where(
            and_(
                User.house_id == house_id,
                User.is_deleted == False
            )
        ).order_by(User.role.desc(), User.name)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_admins(self, db: AsyncSession, house_id: str) -> List[User]:
        """Get all admin users in a house."""
        stmt = select(User).where(
            and_(
                User.house_id == house_id,
                User.role == "admin",
                User.is_deleted == False
            )
        )
        
        result = await db.execute(stmt)
        return list(result.scalars().all())