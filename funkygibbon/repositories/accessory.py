"""
FunkyGibbon - Accessory Repository

DEVELOPMENT CONTEXT:
Created in July 2025 as the repository for Accessory entities (previously Device).
Updated to work with the HomeKit-compatible Accessory model from the Inbetweenies
package. Manages smart home accessories like lights, thermostats, and sensors.

FUNCTIONALITY:
- CRUD operations for Accessory entities
- Service and characteristic relationship management
- Room association via many-to-many relationship
- Reachability and blocking status updates
- Bridge accessory support

PURPOSE:
Manages Accessory entities which represent individual smart home devices.
Each accessory can have multiple services (e.g., a fan with light) and
characteristics (e.g., on/off, brightness).

KNOWN ISSUES:
- No validation for accessory capabilities
- Room associations need manual management

REVISION HISTORY:
- 2025-07-28: Initial implementation as DeviceRepository
- 2025-07-29: Renamed to AccessoryRepository for HomeKit compatibility
- 2025-07-29: Added support for HomeKit-specific fields

DEPENDENCIES:
- inbetweenies.models: Accessory model
- .base: BaseRepository for common operations
"""

from datetime import datetime, UTC
from typing import Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from inbetweenies.models import Accessory
from .base import BaseRepository


class AccessoryRepository(BaseRepository[Accessory]):
    """Repository for Accessory entities."""
    
    def __init__(self):
        super().__init__(Accessory)
    
    async def get_by_home(self, db: AsyncSession, home_id: str) -> List[Accessory]:
        """Get all accessories in a home."""
        stmt = select(Accessory).where(
            and_(
                Accessory.home_id == home_id,
                True  # Models don't have is_deleted
            )
        ).order_by(Accessory.name)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_with_services(
        self, 
        db: AsyncSession, 
        id: str
    ) -> Optional[Accessory]:
        """Get accessory with services loaded."""
        stmt = select(Accessory).where(
            and_(
                Accessory.id == id,
                True  # Models don't have is_deleted
            )
        ).options(
            selectinload(Accessory.services)
        )
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_reachable(self, db: AsyncSession, home_id: str) -> List[Accessory]:
        """Get all reachable accessories in a home."""
        stmt = select(Accessory).where(
            and_(
                Accessory.home_id == home_id,
                Accessory.is_reachable == True,
                True  # Models don't have is_deleted
            )
        ).order_by(Accessory.name)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def update_reachability(
        self,
        db: AsyncSession,
        accessory_id: str,
        is_reachable: bool
    ) -> Optional[Accessory]:
        """Update accessory reachability status."""
        accessory = await self.get_by_id(db, accessory_id)
        if not accessory:
            return None
        
        accessory.is_reachable = is_reachable
        accessory.updated_at = datetime.now(UTC)
        
        await db.commit()
        await db.refresh(accessory)
        return accessory