"""
HomeKit Services API endpoints.
"""

from typing import List, Optional
from datetime import datetime, UTC
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...database import get_db
from ...models import Service

router = APIRouter()


@router.post("/", response_model=dict)
async def create_service(
    accessory_id: str,
    service_type: str,
    name: str,
    is_primary: bool = True,
    is_user_interactive: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Create a new service."""
    service = Service(
        id=str(uuid.uuid4()),
        accessory_id=accessory_id,
        service_type=service_type,
        name=name,
        is_primary=is_primary,
        is_user_interactive=is_user_interactive
    )
    db.add(service)
    await db.commit()
    return service.to_dict()


@router.get("/{service_id}", response_model=dict)
async def get_service(
    service_id: str,
    include_characteristics: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """Get a service by ID."""
    query = select(Service).where(Service.id == service_id)
    
    if include_characteristics:
        query = query.options(selectinload(Service.characteristics))
    
    result = await db.execute(query)
    service = result.scalar_one_or_none()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    data = service.to_dict()
    if include_characteristics:
        data['characteristics'] = [char.to_dict() for char in service.characteristics]
    
    return data


@router.get("/", response_model=List[dict])
async def list_services(
    accessory_id: Optional[str] = None,
    service_type: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List services, optionally filtered by accessory or type."""
    query = select(Service)
    
    if accessory_id:
        query = query.where(Service.accessory_id == accessory_id)
    
    if service_type:
        query = query.where(Service.service_type == service_type)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    services = result.scalars().all()
    return [svc.to_dict() for svc in services]


@router.put("/{service_id}", response_model=dict)
async def update_service(
    service_id: str,
    name: Optional[str] = None,
    is_primary: Optional[bool] = None,
    is_user_interactive: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update a service."""
    result = await db.execute(
        select(Service).where(Service.id == service_id)
    )
    service = result.scalar_one_or_none()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    if name is not None:
        service.name = name
    if is_primary is not None:
        service.is_primary = is_primary
    if is_user_interactive is not None:
        service.is_user_interactive = is_user_interactive
    
    service.updated_at = datetime.now(UTC)
    await db.commit()
    
    return service.to_dict()


@router.delete("/{service_id}")
async def delete_service(
    service_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a service."""
    result = await db.execute(
        select(Service).where(Service.id == service_id)
    )
    service = result.scalar_one_or_none()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    await db.delete(service)
    await db.commit()
    
    return {"status": "deleted", "id": service_id}