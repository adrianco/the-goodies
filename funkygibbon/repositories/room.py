"""
Room repository with device management.
"""

from typing import List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.device import Device
from ..models.room import Room
from .base import BaseRepository


class RoomRepository(BaseRepository[Room]):
    """Repository for Room entities."""
    
    def __init__(self):
        super().__init__(Room)
    
    async def get_by_house(self, db: AsyncSession, house_id: str) -> List[Room]:
        """Get all rooms in a house."""
        stmt = select(Room).where(
            and_(
                Room.house_id == house_id,
                Room.is_deleted == False
            )
        ).order_by(Room.floor, Room.name)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_with_devices(self, db: AsyncSession, id: str) -> Optional[Room]:
        """Get room with all devices loaded."""
        stmt = select(Room).where(
            and_(
                Room.id == id,
                Room.is_deleted == False
            )
        ).options(selectinload(Room.devices))
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_device_count(self, db: AsyncSession, room_id: str) -> None:
        """Update device count for a room."""
        room = await self.get_by_id(db, room_id)
        if not room:
            return
        
        # Count devices
        count_stmt = select(func.count()).select_from(Device).where(
            and_(
                Device.room_id == room_id,
                Device.is_deleted == False
            )
        )
        result = await db.execute(count_stmt)
        room.device_count = result.scalar() or 0
        
        await db.commit()
    
    async def create_with_house_name(
        self, 
        db: AsyncSession, 
        house_id: str,
        house_name: str,
        **kwargs
    ) -> Room:
        """Create room with denormalized house name."""
        kwargs["house_id"] = house_id
        kwargs["house_name"] = house_name
        return await self.create(db, **kwargs)