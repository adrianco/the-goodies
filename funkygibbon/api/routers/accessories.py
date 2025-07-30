"""
HomeKit Accessories API endpoints.
"""

from typing import List, Optional
from datetime import datetime, UTC
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...database import get_db
from ...models import Accessory, accessory_rooms

router = APIRouter()


@router.post("/", response_model=dict)
async def create_accessory(
    home_id: str,
    name: str,
    manufacturer: str,
    model: str,
    room_ids: Optional[List[str]] = None,
    serial_number: Optional[str] = None,
    firmware_version: Optional[str] = "1.0.0",
    is_bridge: bool = False,
    bridge_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Create a new accessory."""
    accessory = Accessory(
        id=str(uuid.uuid4()),
        home_id=home_id,
        name=name,
        manufacturer=manufacturer,
        model=model,
        serial_number=serial_number or f"SN-{uuid.uuid4().hex[:8]}",
        firmware_version=firmware_version,
        is_reachable=True,
        is_blocked=False,
        is_bridge=is_bridge,
        bridge_id=bridge_id
    )
    db.add(accessory)
    
    # Add room associations
    if room_ids:
        for room_id in room_ids:
            await db.execute(
                accessory_rooms.insert().values(
                    accessory_id=accessory.id,
                    room_id=room_id
                )
            )
    
    await db.commit()
    await db.refresh(accessory)
    
    # Manually construct response to avoid lazy loading
    return {
        "id": accessory.id,
        "home_id": accessory.home_id,
        "name": accessory.name,
        "manufacturer": accessory.manufacturer,
        "model": accessory.model,
        "serial_number": accessory.serial_number,
        "firmware_version": accessory.firmware_version,
        "is_reachable": accessory.is_reachable,
        "is_blocked": accessory.is_blocked,
        "is_bridge": accessory.is_bridge,
        "bridge_id": accessory.bridge_id,
        "room_ids": room_ids or [],
        "created_at": accessory.created_at.isoformat() if accessory.created_at else None,
        "updated_at": accessory.updated_at.isoformat() if accessory.updated_at else None,
        "sync_id": accessory.sync_id
    }


@router.get("/{accessory_id}", response_model=dict)
async def get_accessory(
    accessory_id: str,
    include_services: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """Get an accessory by ID."""
    query = select(Accessory).where(Accessory.id == accessory_id)
    
    if include_services:
        query = query.options(selectinload(Accessory.services))
    
    result = await db.execute(query)
    accessory = result.scalar_one_or_none()
    
    if not accessory:
        raise HTTPException(status_code=404, detail="Accessory not found")
    
    data = accessory.to_dict()
    if include_services:
        data['services'] = [svc.to_dict() for svc in accessory.services]
    
    return data


@router.get("/", response_model=List[dict])
async def list_accessories(
    home_id: Optional[str] = None,
    room_id: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List accessories, optionally filtered by home or room."""
    query = select(Accessory)
    
    if home_id:
        query = query.where(Accessory.home_id == home_id)
    
    if room_id:
        query = query.join(accessory_rooms).where(
            accessory_rooms.c.room_id == room_id
        )
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    accessories = result.scalars().all()
    return [acc.to_dict() for acc in accessories]


@router.put("/{accessory_id}", response_model=dict)
async def update_accessory(
    accessory_id: str,
    name: Optional[str] = None,
    is_reachable: Optional[bool] = None,
    is_blocked: Optional[bool] = None,
    firmware_version: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update an accessory."""
    result = await db.execute(
        select(Accessory).where(Accessory.id == accessory_id)
    )
    accessory = result.scalar_one_or_none()
    
    if not accessory:
        raise HTTPException(status_code=404, detail="Accessory not found")
    
    if name is not None:
        accessory.name = name
    if is_reachable is not None:
        accessory.is_reachable = is_reachable
    if is_blocked is not None:
        accessory.is_blocked = is_blocked
    if firmware_version is not None:
        accessory.firmware_version = firmware_version
    
    accessory.updated_at = datetime.now(UTC)
    await db.commit()
    
    return accessory.to_dict()


@router.post("/{accessory_id}/rooms/{room_id}")
async def add_accessory_to_room(
    accessory_id: str,
    room_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Add an accessory to a room."""
    # Verify accessory exists
    result = await db.execute(
        select(Accessory).where(Accessory.id == accessory_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Accessory not found")
    
    # Add association
    await db.execute(
        accessory_rooms.insert().values(
            accessory_id=accessory_id,
            room_id=room_id
        )
    )
    await db.commit()
    
    return {"status": "added", "accessory_id": accessory_id, "room_id": room_id}


@router.delete("/{accessory_id}/rooms/{room_id}")
async def remove_accessory_from_room(
    accessory_id: str,
    room_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Remove an accessory from a room."""
    result = await db.execute(
        accessory_rooms.delete().where(
            (accessory_rooms.c.accessory_id == accessory_id) &
            (accessory_rooms.c.room_id == room_id)
        )
    )
    await db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Association not found")
    
    return {"status": "removed", "accessory_id": accessory_id, "room_id": room_id}


@router.delete("/{accessory_id}")
async def delete_accessory(
    accessory_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete an accessory."""
    result = await db.execute(
        select(Accessory).where(Accessory.id == accessory_id)
    )
    accessory = result.scalar_one_or_none()
    
    if not accessory:
        raise HTTPException(status_code=404, detail="Accessory not found")
    
    await db.delete(accessory)
    await db.commit()
    
    return {"status": "deleted", "id": accessory_id}