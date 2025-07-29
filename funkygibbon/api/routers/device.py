"""
Device API endpoints.
"""

import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...repositories.device import DeviceRepository
from ...repositories.house import HouseRepository
from ...repositories.room import RoomRepository

router = APIRouter()
device_repo = DeviceRepository()
room_repo = RoomRepository()
house_repo = HouseRepository()


@router.post("/", response_model=dict)
async def create_device(
    room_id: str,
    name: str,
    device_type: str,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Create a new device."""
    try:
        # Verify room exists
        room = await room_repo.get_by_id(db, room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # Check if device with same name already exists in the room
        existing_devices = await device_repo.get_by_room(db, room_id)
        if any(d.name == name for d in existing_devices):
            raise HTTPException(
                status_code=409, 
                detail=f"Device with name '{name}' already exists in room '{room.name}'"
            )
        
        device = await device_repo.create_with_names(
            db,
            room_id=room_id,
            room_name=room.name,
            house_id=room.house_id,
            house_name=room.house_name,
            name=name,
            device_type=device_type,
            manufacturer=manufacturer,
            model=model
        )
        
        # Update counters
        room.device_count += 1
        house = await house_repo.get_by_id(db, room.house_id)
        if house:
            house.device_count += 1
        await db.commit()
        
        return device.to_dict()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create device: {str(e)}")


@router.get("/{device_id}", response_model=dict)
async def get_device(
    device_id: str,
    include_states: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """Get a device by ID."""
    if include_states:
        device = await device_repo.get_with_states(db, device_id)
    else:
        device = await device_repo.get_by_id(db, device_id)
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    result = device.to_dict()
    if include_states and hasattr(device, 'entity_states'):
        result['states'] = [state.to_dict() for state in device.entity_states]
    
    return result


@router.get("/", response_model=List[dict])
async def list_devices(
    room_id: Optional[str] = None,
    house_id: Optional[str] = None,
    device_type: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List devices with optional filters."""
    if room_id:
        devices = await device_repo.get_by_room(db, room_id)
    elif house_id:
        devices = await device_repo.get_by_house(db, house_id)
    else:
        devices = await device_repo.get_all(db, limit=limit)
    
    # Filter by type if specified
    if device_type:
        devices = [d for d in devices if d.device_type == device_type]
    
    return [device.to_dict() for device in devices]


@router.put("/{device_id}/state", response_model=dict)
async def update_device_state(
    device_id: str,
    state_type: str,
    state_value: str,
    state_data: Optional[Dict] = None,
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update device state and create history entry."""
    state = await device_repo.update_state(
        db,
        device_id=device_id,
        state_type=state_type,
        state_value=state_value,
        state_json=state_data,
        user_id=user_id
    )
    
    if not state:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return state.to_dict()


@router.put("/{device_id}", response_model=dict)
async def update_device(
    device_id: str,
    name: Optional[str] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    ip_address: Optional[str] = None,
    mac_address: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update device information."""
    updates = {}
    if name is not None:
        updates['name'] = name
    if manufacturer is not None:
        updates['manufacturer'] = manufacturer
    if model is not None:
        updates['model'] = model
    if ip_address is not None:
        updates['ip_address'] = ip_address
    if mac_address is not None:
        updates['mac_address'] = mac_address
    
    device = await device_repo.update(db, device_id, **updates)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return device.to_dict()


@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Soft delete a device."""
    device = await device_repo.get_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    success = await device_repo.soft_delete(db, device_id)
    
    # Update counters
    room = await room_repo.get_by_id(db, device.room_id)
    if room:
        room.device_count = max(0, room.device_count - 1)
    
    house = await house_repo.get_by_id(db, device.house_id)
    if house:
        house.device_count = max(0, house.device_count - 1)
    
    await db.commit()
    
    return {"status": "deleted", "id": device_id}