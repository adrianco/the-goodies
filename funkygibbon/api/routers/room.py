"""
Room API endpoints.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...repositories.house import HouseRepository
from ...repositories.room import RoomRepository

router = APIRouter()
room_repo = RoomRepository()
house_repo = HouseRepository()


@router.post("/", response_model=dict)
async def create_room(
    house_id: str,
    name: str,
    room_type: Optional[str] = None,
    floor: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Create a new room."""
    try:
        # Verify house exists
        house = await house_repo.get_by_id(db, house_id)
        if not house:
            raise HTTPException(status_code=404, detail="House not found")
        
        # Check if room with same name already exists in the house
        existing_rooms = await room_repo.get_by_house(db, house_id)
        if any(r.name == name for r in existing_rooms):
            raise HTTPException(
                status_code=409,
                detail=f"Room with name '{name}' already exists in house '{house.name}'"
            )
        
        room = await room_repo.create_with_house_name(
            db,
            house_id=house_id,
            house_name=house.name,
            name=name,
            room_type=room_type,
            floor=floor
        )
        
        # Update house room count
        house.room_count += 1
        await db.commit()
        
        return room.to_dict()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create room: {str(e)}")


@router.get("/{room_id}", response_model=dict)
async def get_room(
    room_id: str,
    include_devices: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """Get a room by ID."""
    if include_devices:
        room = await room_repo.get_with_devices(db, room_id)
    else:
        room = await room_repo.get_by_id(db, room_id)
    
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    result = room.to_dict()
    if include_devices and hasattr(room, 'devices'):
        result['devices'] = [device.to_dict() for device in room.devices if not device.is_deleted]
    
    return result


@router.get("/", response_model=List[dict])
async def list_rooms(
    house_id: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List rooms, optionally filtered by house."""
    if house_id:
        rooms = await room_repo.get_by_house(db, house_id)
    else:
        rooms = await room_repo.get_all(db, limit=limit)
    
    return [room.to_dict() for room in rooms]


@router.put("/{room_id}", response_model=dict)
async def update_room(
    room_id: str,
    name: Optional[str] = None,
    room_type: Optional[str] = None,
    floor: Optional[int] = None,
    temperature: Optional[float] = None,
    humidity: Optional[float] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update a room."""
    updates = {}
    if name is not None:
        updates['name'] = name
    if room_type is not None:
        updates['room_type'] = room_type
    if floor is not None:
        updates['floor'] = floor
    if temperature is not None:
        updates['temperature'] = temperature
    if humidity is not None:
        updates['humidity'] = humidity
    
    room = await room_repo.update(db, room_id, **updates)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return room.to_dict()


@router.delete("/{room_id}")
async def delete_room(
    room_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Soft delete a room."""
    room = await room_repo.get_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    success = await room_repo.soft_delete(db, room_id)
    
    # Update house room count
    house = await house_repo.get_by_id(db, room.house_id)
    if house:
        house.room_count = max(0, house.room_count - 1)
        await db.commit()
    
    return {"status": "deleted", "id": room_id}