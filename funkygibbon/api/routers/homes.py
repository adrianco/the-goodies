"""
HomeKit Homes API endpoints.
"""

from typing import List, Optional
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models import Home

router = APIRouter()


@router.post("/", response_model=dict)
async def create_home(
    name: str,
    is_primary: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """Create a new home."""
    home = Home(
        id=f"home-{datetime.now().timestamp()}",
        name=name,
        is_primary=is_primary
    )
    db.add(home)
    await db.commit()
    return home.to_dict()


@router.get("/{home_id}", response_model=dict)
async def get_home(
    home_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a home by ID."""
    result = await db.execute(
        select(Home).where(Home.id == home_id)
    )
    home = result.scalar_one_or_none()
    
    if not home:
        raise HTTPException(status_code=404, detail="Home not found")
    
    return home.to_dict()


@router.get("/", response_model=List[dict])
async def list_homes(
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all homes."""
    result = await db.execute(
        select(Home).limit(limit)
    )
    homes = result.scalars().all()
    return [home.to_dict() for home in homes]


@router.put("/{home_id}", response_model=dict)
async def update_home(
    home_id: str,
    name: Optional[str] = None,
    is_primary: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update a home."""
    result = await db.execute(
        select(Home).where(Home.id == home_id)
    )
    home = result.scalar_one_or_none()
    
    if not home:
        raise HTTPException(status_code=404, detail="Home not found")
    
    if name is not None:
        home.name = name
    if is_primary is not None:
        home.is_primary = is_primary
    
    home.updated_at = datetime.now(UTC)
    await db.commit()
    
    return home.to_dict()


@router.delete("/{home_id}")
async def delete_home(
    home_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a home."""
    result = await db.execute(
        select(Home).where(Home.id == home_id)
    )
    home = result.scalar_one_or_none()
    
    if not home:
        raise HTTPException(status_code=404, detail="Home not found")
    
    await db.delete(home)
    await db.commit()
    
    return {"status": "deleted", "id": home_id}