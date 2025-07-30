"""
HomeKit Rooms API endpoints.
"""

from typing import List, Optional
from datetime import datetime, UTC
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models import Room

router = APIRouter()


@router.post("/", response_model=dict)
async def create_room(
    home_id: str,
    name: str,
    db: AsyncSession = Depends(get_db)
):
    """Create a new room."""
    room = Room(
        id=str(uuid.uuid4()),
        home_id=home_id,
        name=name
    )
    db.add(room)
    await db.commit()
    return room.to_dict()


@router.get("/{room_id}", response_model=dict)
async def get_room(
    room_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a room by ID."""
    result = await db.execute(
        select(Room).where(Room.id == room_id)
    )
    room = result.scalar_one_or_none()
    
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return room.to_dict()


@router.get("/", response_model=List[dict])
async def list_rooms(
    home_id: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List rooms, optionally filtered by home."""
    query = select(Room)
    
    if home_id:
        query = query.where(Room.home_id == home_id)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    rooms = result.scalars().all()
    return [room.to_dict() for room in rooms]


@router.put("/{room_id}", response_model=dict)
async def update_room(
    room_id: str,
    name: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update a room."""
    result = await db.execute(
        select(Room).where(Room.id == room_id)
    )
    room = result.scalar_one_or_none()
    
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    if name is not None:
        room.name = name
    
    room.updated_at = datetime.now(UTC)
    await db.commit()
    
    return room.to_dict()


@router.delete("/{room_id}")
async def delete_room(
    room_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a room."""
    result = await db.execute(
        select(Room).where(Room.id == room_id)
    )
    room = result.scalar_one_or_none()
    
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    await db.delete(room)
    await db.commit()
    
    return {"status": "deleted", "id": room_id}