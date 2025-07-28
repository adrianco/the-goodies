"""
Event repository for audit logging.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.event import Event


class EventRepository:
    """Repository for Event audit logging."""
    
    def __init__(self):
        self.model_class = Event
    
    async def log_event(
        self,
        db: AsyncSession,
        event_type: str,
        entity_type: str,
        entity_id: str,
        description: Optional[str] = None,
        data_json: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Event:
        """Log an event."""
        event = Event(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            data_json=data_json,
            source="user" if user_id else "system",
            user_id=user_id
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event
    
    async def get_entity_events(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: str,
        limit: int = 100
    ) -> List[Event]:
        """Get events for a specific entity."""
        stmt = select(Event).where(
            and_(
                Event.entity_type == entity_type,
                Event.entity_id == entity_id
            )
        ).order_by(Event.created_at.desc()).limit(limit)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_recent_events(
        self,
        db: AsyncSession,
        limit: int = 100,
        event_type: Optional[str] = None
    ) -> List[Event]:
        """Get recent events."""
        stmt = select(Event)
        
        if event_type:
            stmt = stmt.where(Event.event_type == event_type)
        
        stmt = stmt.order_by(Event.created_at.desc()).limit(limit)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_events_in_range(
        self,
        db: AsyncSession,
        start_time: datetime,
        end_time: datetime,
        event_type: Optional[str] = None
    ) -> List[Event]:
        """Get events in a time range."""
        stmt = select(Event).where(
            and_(
                Event.created_at >= start_time,
                Event.created_at <= end_time
            )
        )
        
        if event_type:
            stmt = stmt.where(Event.event_type == event_type)
        
        stmt = stmt.order_by(Event.created_at)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())