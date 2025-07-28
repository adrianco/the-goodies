"""
House repository with relationship management.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.house import House
from ..models.room import Room
from ..models.device import Device
from ..models.user import User
from .base import BaseRepository


class HouseRepository(BaseRepository[House]):
    """Repository for House entities."""
    
    def __init__(self):
        super().__init__(House)
    
    async def get_with_rooms(self, db: AsyncSession, id: str) -> Optional[House]:
        """Get house with all rooms loaded."""
        stmt = select(House).where(
            House.id == id,
            House.is_deleted == False
        ).options(selectinload(House.rooms))
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_with_all_relations(self, db: AsyncSession, id: str) -> Optional[House]:
        """Get house with all relationships loaded."""
        stmt = select(House).where(
            House.id == id,
            House.is_deleted == False
        ).options(
            selectinload(House.rooms),
            selectinload(House.users)
        )
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_counters(self, db: AsyncSession, house_id: str) -> None:
        """Update denormalized counters for a house."""
        house = await self.get_by_id(db, house_id)
        if not house:
            return
        
        # Count rooms
        room_count_stmt = select(func.count()).select_from(Room).where(
            Room.house_id == house_id,
            Room.is_deleted == False
        )
        room_count_result = await db.execute(room_count_stmt)
        house.room_count = room_count_result.scalar() or 0
        
        # Count devices
        device_count_stmt = select(func.count()).select_from(Device).where(
            Device.house_id == house_id,
            Device.is_deleted == False
        )
        device_count_result = await db.execute(device_count_stmt)
        house.device_count = device_count_result.scalar() or 0
        
        # Count users
        user_count_stmt = select(func.count()).select_from(User).where(
            User.house_id == house_id,
            User.is_deleted == False
        )
        user_count_result = await db.execute(user_count_stmt)
        house.user_count = user_count_result.scalar() or 0
        
        await db.commit()