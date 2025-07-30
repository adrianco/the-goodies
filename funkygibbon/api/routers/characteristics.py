"""
HomeKit Characteristics API endpoints.
"""

from typing import List, Optional, Any
from datetime import datetime, UTC
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models import Characteristic

router = APIRouter()


@router.post("/", response_model=dict)
async def create_characteristic(
    service_id: str,
    characteristic_type: str,
    value: str,
    format: Optional[str] = None,
    unit: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    step_value: Optional[float] = None,
    is_readable: bool = True,
    is_writable: bool = True,
    supports_event_notification: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Create a new characteristic."""
    characteristic = Characteristic(
        id=str(uuid.uuid4()),
        service_id=service_id,
        characteristic_type=characteristic_type,
        value=value,
        format=format,
        unit=unit,
        min_value=min_value,
        max_value=max_value,
        step_value=step_value,
        is_readable=is_readable,
        is_writable=is_writable,
        supports_event_notification=supports_event_notification
    )
    db.add(characteristic)
    await db.commit()
    return characteristic.to_dict()


@router.get("/{characteristic_id}", response_model=dict)
async def get_characteristic(
    characteristic_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a characteristic by ID."""
    result = await db.execute(
        select(Characteristic).where(Characteristic.id == characteristic_id)
    )
    characteristic = result.scalar_one_or_none()
    
    if not characteristic:
        raise HTTPException(status_code=404, detail="Characteristic not found")
    
    return characteristic.to_dict()


@router.get("/", response_model=List[dict])
async def list_characteristics(
    service_id: Optional[str] = None,
    characteristic_type: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List characteristics, optionally filtered by service or type."""
    query = select(Characteristic)
    
    if service_id:
        query = query.where(Characteristic.service_id == service_id)
    
    if characteristic_type:
        query = query.where(Characteristic.characteristic_type == characteristic_type)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    characteristics = result.scalars().all()
    return [char.to_dict() for char in characteristics]


@router.put("/{characteristic_id}/value", response_model=dict)
async def update_characteristic_value(
    characteristic_id: str,
    value: str,
    db: AsyncSession = Depends(get_db)
):
    """Update a characteristic's value."""
    result = await db.execute(
        select(Characteristic).where(Characteristic.id == characteristic_id)
    )
    characteristic = result.scalar_one_or_none()
    
    if not characteristic:
        raise HTTPException(status_code=404, detail="Characteristic not found")
    
    if not characteristic.is_writable:
        raise HTTPException(status_code=403, detail="Characteristic is not writable")
    
    characteristic.value = value
    characteristic.updated_at = datetime.now(UTC)
    await db.commit()
    
    return characteristic.to_dict()


@router.put("/{characteristic_id}", response_model=dict)
async def update_characteristic(
    characteristic_id: str,
    value: Optional[str] = None,
    format: Optional[str] = None,
    unit: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    step_value: Optional[float] = None,
    is_readable: Optional[bool] = None,
    is_writable: Optional[bool] = None,
    supports_event_notification: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update a characteristic."""
    result = await db.execute(
        select(Characteristic).where(Characteristic.id == characteristic_id)
    )
    characteristic = result.scalar_one_or_none()
    
    if not characteristic:
        raise HTTPException(status_code=404, detail="Characteristic not found")
    
    if value is not None:
        characteristic.value = value
    if format is not None:
        characteristic.format = format
    if unit is not None:
        characteristic.unit = unit
    if min_value is not None:
        characteristic.min_value = min_value
    if max_value is not None:
        characteristic.max_value = max_value
    if step_value is not None:
        characteristic.step_value = step_value
    if is_readable is not None:
        characteristic.is_readable = is_readable
    if is_writable is not None:
        characteristic.is_writable = is_writable
    if supports_event_notification is not None:
        characteristic.supports_event_notification = supports_event_notification
    
    characteristic.updated_at = datetime.now(UTC)
    await db.commit()
    
    return characteristic.to_dict()


@router.delete("/{characteristic_id}")
async def delete_characteristic(
    characteristic_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a characteristic."""
    result = await db.execute(
        select(Characteristic).where(Characteristic.id == characteristic_id)
    )
    characteristic = result.scalar_one_or_none()
    
    if not characteristic:
        raise HTTPException(status_code=404, detail="Characteristic not found")
    
    await db.delete(characteristic)
    await db.commit()
    
    return {"status": "deleted", "id": characteristic_id}