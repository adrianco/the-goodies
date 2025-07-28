"""
Device repository with state management.
"""

from datetime import datetime, UTC
from typing import Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.device import Device
from ..models.entity_state import EntityState
from .base import BaseRepository


class DeviceRepository(BaseRepository[Device]):
    """Repository for Device entities."""
    
    def __init__(self):
        super().__init__(Device)
    
    async def get_by_room(self, db: AsyncSession, room_id: str) -> List[Device]:
        """Get all devices in a room."""
        stmt = select(Device).where(
            and_(
                Device.room_id == room_id,
                Device.is_deleted == False
            )
        ).order_by(Device.name)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_by_house(self, db: AsyncSession, house_id: str) -> List[Device]:
        """Get all devices in a house."""
        stmt = select(Device).where(
            and_(
                Device.house_id == house_id,
                Device.is_deleted == False
            )
        ).order_by(Device.room_name, Device.name)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_with_states(
        self, 
        db: AsyncSession, 
        id: str,
        limit: int = 100
    ) -> Optional[Device]:
        """Get device with recent states."""
        stmt = select(Device).where(
            and_(
                Device.id == id,
                Device.is_deleted == False
            )
        ).options(
            selectinload(Device.entity_states)
        )
        
        result = await db.execute(stmt)
        device = result.scalar_one_or_none()
        
        if device and hasattr(device, 'entity_states'):
            # Sort states by created_at descending and limit
            device.entity_states = sorted(
                device.entity_states, 
                key=lambda s: s.created_at, 
                reverse=True
            )[:limit]
        
        return device
    
    async def create_with_names(
        self,
        db: AsyncSession,
        room_id: str,
        room_name: str,
        house_id: str,
        house_name: str,
        **kwargs
    ) -> Device:
        """Create device with denormalized names."""
        kwargs.update({
            "room_id": room_id,
            "room_name": room_name,
            "house_id": house_id,
            "house_name": house_name
        })
        return await self.create(db, **kwargs)
    
    async def update_state(
        self,
        db: AsyncSession,
        device_id: str,
        state_type: str,
        state_value: str,
        state_json: Optional[Dict] = None,
        user_id: Optional[str] = None
    ) -> Optional[EntityState]:
        """Update device state and create state history entry."""
        device = await self.get_by_id(db, device_id)
        if not device:
            return None
        
        # Update device state_json if provided
        if state_json:
            import json
            device.state_json = json.dumps(state_json)
            device.updated_at = datetime.now(UTC)
        
        # Create state history entry
        state = EntityState(
            device_id=device_id,
            state_type=state_type,
            state_value=state_value,
            state_json=json.dumps(state_json) if state_json else None,
            source="user" if user_id else "system",
            user_id=user_id
        )
        db.add(state)
        
        await db.commit()
        await db.refresh(state)
        return state