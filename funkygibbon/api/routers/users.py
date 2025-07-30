"""
HomeKit Users API endpoints.
"""

from typing import List, Optional
from datetime import datetime, UTC
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models import User

router = APIRouter()


@router.post("/", response_model=dict)
async def create_user(
    home_id: str,
    name: str,
    is_administrator: bool = False,
    is_owner: bool = False,
    remote_access_allowed: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Create a new user."""
    user = User(
        id=str(uuid.uuid4()),
        home_id=home_id,
        name=name,
        is_administrator=is_administrator,
        is_owner=is_owner,
        remote_access_allowed=remote_access_allowed
    )
    db.add(user)
    await db.commit()
    return user.to_dict()


@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a user by ID."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user.to_dict()


@router.get("/", response_model=List[dict])
async def list_users(
    home_id: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List users, optionally filtered by home."""
    query = select(User)
    
    if home_id:
        query = query.where(User.home_id == home_id)
    
    query = query.limit(limit)
    
    result = await db.execute(query)
    users = result.scalars().all()
    return [user.to_dict() for user in users]


@router.put("/{user_id}", response_model=dict)
async def update_user(
    user_id: str,
    name: Optional[str] = None,
    is_administrator: Optional[bool] = None,
    is_owner: Optional[bool] = None,
    remote_access_allowed: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update a user."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if name is not None:
        user.name = name
    if is_administrator is not None:
        user.is_administrator = is_administrator
    if is_owner is not None:
        user.is_owner = is_owner
    if remote_access_allowed is not None:
        user.remote_access_allowed = remote_access_allowed
    
    user.updated_at = datetime.now(UTC)
    await db.commit()
    
    return user.to_dict()


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a user."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await db.delete(user)
    await db.commit()
    
    return {"status": "deleted", "id": user_id}