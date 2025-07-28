"""
Sync API endpoints for conflict resolution.
"""

from datetime import datetime, UTC
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models.base import ConflictResolution
from ...repositories import (
    DeviceRepository,
    HouseRepository,
    RoomRepository,
    UserRepository,
)

router = APIRouter()


class SyncRequest(BaseModel):
    """Sync request with entities to sync."""
    houses: List[Dict] = []
    rooms: List[Dict] = []
    devices: List[Dict] = []
    users: List[Dict] = []
    last_sync: Optional[datetime] = None


class SyncResponse(BaseModel):
    """Sync response with results and conflicts."""
    synced: Dict[str, int] = {}
    conflicts: List[ConflictResolution] = []
    changes: Dict[str, List[Dict]] = {}
    timestamp: datetime


@router.post("/", response_model=SyncResponse)
async def sync_entities(
    request: SyncRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Sync entities from client with last-write-wins conflict resolution.
    
    Returns updated entities and any conflicts that were resolved.
    """
    house_repo = HouseRepository()
    room_repo = RoomRepository()
    device_repo = DeviceRepository()
    user_repo = UserRepository()
    
    synced_counts = {
        "houses": 0,
        "rooms": 0,
        "devices": 0,
        "users": 0
    }
    conflicts = []
    
    # Sync houses
    for house_data in request.houses:
        _, updated, conflict = await house_repo.sync_entity(db, house_data)
        if updated:
            synced_counts["houses"] += 1
        if conflict:
            conflicts.append(conflict)
    
    # Sync rooms
    for room_data in request.rooms:
        _, updated, conflict = await room_repo.sync_entity(db, room_data)
        if updated:
            synced_counts["rooms"] += 1
        if conflict:
            conflicts.append(conflict)
    
    # Sync devices
    for device_data in request.devices:
        _, updated, conflict = await device_repo.sync_entity(db, device_data)
        if updated:
            synced_counts["devices"] += 1
        if conflict:
            conflicts.append(conflict)
    
    # Sync users
    for user_data in request.users:
        _, updated, conflict = await user_repo.sync_entity(db, user_data)
        if updated:
            synced_counts["users"] += 1
        if conflict:
            conflicts.append(conflict)
    
    # Get changes since last sync
    changes = {"houses": [], "rooms": [], "devices": [], "users": []}
    
    if request.last_sync:
        # Get entities changed since last sync
        changed_houses = await house_repo.get_changes_since(db, request.last_sync)
        changed_rooms = await room_repo.get_changes_since(db, request.last_sync)
        changed_devices = await device_repo.get_changes_since(db, request.last_sync)
        changed_users = await user_repo.get_changes_since(db, request.last_sync)
        
        changes["houses"] = [h.to_dict() for h in changed_houses]
        changes["rooms"] = [r.to_dict() for r in changed_rooms]
        changes["devices"] = [d.to_dict() for d in changed_devices]
        changes["users"] = [u.to_dict() for u in changed_users]
    
    return SyncResponse(
        synced=synced_counts,
        conflicts=conflicts,
        changes=changes,
        timestamp=datetime.now(UTC)
    )


@router.get("/changes", response_model=dict)
async def get_changes(
    since: datetime,
    entity_type: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get entities changed since a specific timestamp."""
    changes = {}
    
    if not entity_type or entity_type == "houses":
        house_repo = HouseRepository()
        houses = await house_repo.get_changes_since(db, since, limit)
        changes["houses"] = [h.to_dict() for h in houses]
    
    if not entity_type or entity_type == "rooms":
        room_repo = RoomRepository()
        rooms = await room_repo.get_changes_since(db, since, limit)
        changes["rooms"] = [r.to_dict() for r in rooms]
    
    if not entity_type or entity_type == "devices":
        device_repo = DeviceRepository()
        devices = await device_repo.get_changes_since(db, since, limit)
        changes["devices"] = [d.to_dict() for d in devices]
    
    if not entity_type or entity_type == "users":
        user_repo = UserRepository()
        users = await user_repo.get_changes_since(db, since, limit)
        changes["users"] = [u.to_dict() for u in users]
    
    return {
        "changes": changes,
        "since": since.isoformat(),
        "timestamp": datetime.now(UTC).isoformat()
    }