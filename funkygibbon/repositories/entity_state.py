"""
Entity state repository for time-series data.
"""

from datetime import datetime, timedelta, UTC
from typing import List, Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entity_state import EntityState
from .base import BaseRepository


class EntityStateRepository(BaseRepository[EntityState]):
    """Repository for EntityState time-series data."""
    
    def __init__(self):
        super().__init__(EntityState)
    
    async def get_device_states(
        self,
        db: AsyncSession,
        device_id: str,
        limit: int = 100,
        state_type: Optional[str] = None
    ) -> List[EntityState]:
        """Get recent states for a device."""
        stmt = select(EntityState).where(
            EntityState.device_id == device_id
        )
        
        if state_type:
            stmt = stmt.where(EntityState.state_type == state_type)
        
        stmt = stmt.order_by(EntityState.created_at.desc()).limit(limit)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_device_states_in_range(
        self,
        db: AsyncSession,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
        state_type: Optional[str] = None
    ) -> List[EntityState]:
        """Get states for a device in a time range."""
        stmt = select(EntityState).where(
            and_(
                EntityState.device_id == device_id,
                EntityState.created_at >= start_time,
                EntityState.created_at <= end_time
            )
        )
        
        if state_type:
            stmt = stmt.where(EntityState.state_type == state_type)
        
        stmt = stmt.order_by(EntityState.created_at)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_latest_state(
        self,
        db: AsyncSession,
        device_id: str,
        state_type: str
    ) -> Optional[EntityState]:
        """Get the most recent state of a specific type for a device."""
        stmt = select(EntityState).where(
            and_(
                EntityState.device_id == device_id,
                EntityState.state_type == state_type
            )
        ).order_by(EntityState.created_at.desc()).limit(1)
        
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def cleanup_old_states(
        self,
        db: AsyncSession,
        days_to_keep: int = 30
    ) -> int:
        """Delete states older than specified days."""
        cutoff_date = datetime.now(UTC) - timedelta(days=days_to_keep)
        
        # Count records to delete
        count_stmt = select(func.count()).select_from(EntityState).where(
            EntityState.created_at < cutoff_date
        )
        count_result = await db.execute(count_stmt)
        count = count_result.scalar() or 0
        
        # Delete old records
        if count > 0:
            delete_stmt = delete(EntityState).where(
                EntityState.created_at < cutoff_date
            )
            await db.execute(delete_stmt)
            await db.commit()
        
        return count