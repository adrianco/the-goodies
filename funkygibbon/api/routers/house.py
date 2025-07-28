"""
House API endpoints.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models.house import House
from ...repositories.house import HouseRepository

router = APIRouter()
house_repo = HouseRepository()


@router.post("/", response_model=dict)
async def create_house(
    name: str,
    address: Optional[str] = None,
    timezone: str = "UTC",
    db: AsyncSession = Depends(get_db)
):
    """Create a new house."""
    house = await house_repo.create(
        db,
        name=name,
        address=address,
        timezone=timezone
    )
    return house.to_dict()


@router.get("/{house_id}", response_model=dict)
async def get_house(
    house_id: str,
    include_rooms: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """Get a house by ID."""
    if include_rooms:
        house = await house_repo.get_with_rooms(db, house_id)
    else:
        house = await house_repo.get_by_id(db, house_id)
    
    if not house:
        raise HTTPException(status_code=404, detail="House not found")
    
    result = house.to_dict()
    if include_rooms and hasattr(house, 'rooms'):
        result['rooms'] = [room.to_dict() for room in house.rooms if not room.is_deleted]
    
    return result


@router.get("/", response_model=List[dict])
async def list_houses(
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all houses."""
    houses = await house_repo.get_all(db, limit=limit)
    return [house.to_dict() for house in houses]


@router.put("/{house_id}", response_model=dict)
async def update_house(
    house_id: str,
    name: Optional[str] = None,
    address: Optional[str] = None,
    timezone: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update a house."""
    updates = {}
    if name is not None:
        updates['name'] = name
    if address is not None:
        updates['address'] = address
    if timezone is not None:
        updates['timezone'] = timezone
    
    house = await house_repo.update(db, house_id, **updates)
    if not house:
        raise HTTPException(status_code=404, detail="House not found")
    
    return house.to_dict()


@router.delete("/{house_id}")
async def delete_house(
    house_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Soft delete a house."""
    success = await house_repo.soft_delete(db, house_id)
    if not success:
        raise HTTPException(status_code=404, detail="House not found")
    
    return {"status": "deleted", "id": house_id}