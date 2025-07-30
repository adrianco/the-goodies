"""
FunkyGibbon - Home Repository

DEVELOPMENT CONTEXT:
Created in July 2025 as the repository for Home entities (previously House).
Updated to work with the simplified HomeKit-compatible Home model from the
Inbetweenies package. This is the top-level entity in our smart home hierarchy.

FUNCTIONALITY:
- CRUD operations for Home entities
- Relationship loading for rooms, accessories, and users
- Primary home management
- Sync operations with conflict resolution

PURPOSE:
Manages Home entities which represent the top-level container for all smart
home data. Each deployment typically has one primary home.

KNOWN ISSUES:
- No validation for multiple primary homes
- Relationship loading could be optimized with joins

REVISION HISTORY:
- 2025-07-28: Initial implementation as HouseRepository
- 2025-07-29: Renamed to HomeRepository for HomeKit compatibility
- 2025-07-29: Removed address, timezone, and location fields

DEPENDENCIES:
- inbetweenies.models: Home model
- .base: BaseRepository for common operations
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from inbetweenies.models import Home, Room, Accessory as Device, User
from .base import BaseRepository


class HomeRepository(BaseRepository[Home]):
    """Repository for Home entities."""
    
    def __init__(self):
        super().__init__(Home)
    
    async def get_with_rooms(self, db: AsyncSession, id: str) -> Optional[Home]:
        """Get home with all rooms loaded."""
        stmt = select(Home).where(
            Home.id == id,
            Home.is_deleted == False
        ).options(selectinload(Home.rooms))
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_with_all_relations(self, db: AsyncSession, id: str) -> Optional[Home]:
        """Get home with all relationships loaded."""
        stmt = select(Home).where(
            Home.id == id,
            Home.is_deleted == False
        ).options(
            selectinload(Home.rooms),
            selectinload(Home.users)
        )
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_counters(self, db: AsyncSession, home_id: str) -> None:
        """Update denormalized counters for a home."""
        home = await self.get_by_id(db, home_id)
        if not home:
            return
        
        # Count rooms
        room_count_stmt = select(func.count()).select_from(Room).where(
            Room.home_id == home_id,
            Room.is_deleted == False
        )
        room_count_result = await db.execute(room_count_stmt)
        home.room_count = room_count_result.scalar() or 0
        
        # Count devices
        device_count_stmt = select(func.count()).select_from(Device).where(
            Device.home_id == home_id,
            Device.is_deleted == False
        )
        device_count_result = await db.execute(device_count_stmt)
        home.device_count = device_count_result.scalar() or 0
        
        # Count users
        user_count_stmt = select(func.count()).select_from(User).where(
            User.home_id == home_id,
            User.is_deleted == False
        )
        user_count_result = await db.execute(user_count_stmt)
        home.user_count = user_count_result.scalar() or 0
        
        await db.commit()