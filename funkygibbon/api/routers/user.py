"""
User API endpoints.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...repositories.house import HouseRepository
from ...repositories.user import UserRepository

router = APIRouter()
user_repo = UserRepository()
house_repo = HouseRepository()


@router.post("/", response_model=dict)
async def create_user(
    house_id: str,
    name: str,
    email: Optional[str] = None,
    role: str = "member",
    db: AsyncSession = Depends(get_db)
):
    """Create a new user."""
    # Verify house exists
    house = await house_repo.get_by_id(db, house_id)
    if not house:
        raise HTTPException(status_code=404, detail="House not found")
    
    # Check email uniqueness
    if email:
        existing = await user_repo.get_by_email(db, email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
    
    user = await user_repo.create(
        db,
        house_id=house_id,
        name=name,
        email=email,
        role=role
    )
    
    # Update house user count
    house.user_count += 1
    await db.commit()
    
    return user.to_dict()


@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a user by ID."""
    user = await user_repo.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user.to_dict()


@router.get("/", response_model=List[dict])
async def list_users(
    house_id: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List users with optional filters."""
    if house_id:
        users = await user_repo.get_by_house(db, house_id)
    else:
        users = await user_repo.get_all(db, limit=limit)
    
    # Filter by role if specified
    if role:
        users = [u for u in users if u.role == role]
    
    return [user.to_dict() for user in users]


@router.put("/{user_id}", response_model=dict)
async def update_user(
    user_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update user information."""
    # Check email uniqueness if changing
    if email:
        existing = await user_repo.get_by_email(db, email)
        if existing and existing.id != user_id:
            raise HTTPException(status_code=400, detail="Email already registered")
    
    updates = {}
    if name is not None:
        updates['name'] = name
    if email is not None:
        updates['email'] = email
    if role is not None:
        updates['role'] = role
    
    user = await user_repo.update(db, user_id, **updates)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user.to_dict()


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Soft delete a user."""
    user = await user_repo.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    success = await user_repo.soft_delete(db, user_id)
    
    # Update house user count
    house = await house_repo.get_by_id(db, user.house_id)
    if house:
        house.user_count = max(0, house.user_count - 1)
        await db.commit()
    
    return {"status": "deleted", "id": user_id}