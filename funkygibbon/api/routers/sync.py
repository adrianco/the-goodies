"""
FunkyGibbon - Sync API Router (Bidirectional Sync & Inbetweenies Protocol)

DEVELOPMENT CONTEXT:
Created in July 2025 as the core synchronization endpoint implementing
both our simplified sync protocol and the Inbetweenies protocol for
compatibility with other smart home systems. This is the heart of our
bidirectional sync strategy with last-write-wins conflict resolution.
Updated to work with HomeKit-compatible models from Inbetweenies.

FUNCTIONALITY:
- Standard sync endpoint (/sync) for bulk entity synchronization
- Last-write-wins conflict resolution with detailed reporting
- Change tracking endpoint for incremental sync
- Full Inbetweenies protocol implementation (request/push/ack)
- Handles HomeKit entity types (homes, rooms, accessories, users)
- Batched operations for performance with ~300 entities
- Removed soft delete support (not in HomeKit models)

PURPOSE:
Enables offline-capable clients to synchronize their local state with
the server, resolving conflicts automatically. The Inbetweenies protocol
support allows integration with third-party smart home systems.

KNOWN ISSUES:
- No authentication on sync endpoints (security risk)
- Large sync requests could timeout (no pagination)
- Conflict resolution doesn't consider semantic meaning
- No rate limiting on sync operations
- Inbetweenies implementation incomplete (missing push conflict details)
- No transaction wrapping for atomic sync operations
- Memory usage could spike with large entity counts

REVISION HISTORY:
- 2025-07-28: Initial sync endpoint with basic conflict resolution
- 2025-07-28: Added change tracking for incremental sync
- 2025-07-28: Added Inbetweenies protocol endpoints
- 2025-07-28: Fixed timezone handling in timestamps
- 2025-07-28: Added soft delete support in sync operations
- 2025-07-28: Improved error handling in push operations

DEPENDENCIES:
- fastapi: Web framework and routing
- pydantic: Request/response validation
- sqlalchemy: Database operations
- ...repositories: Entity-specific data access
- ...models.base: ConflictResolution model

USAGE:
# Standard sync (bidirectional):
POST /api/v1/sync
{
    "houses": [{"sync_id": "...", "name": "..."}],
    "devices": [{"sync_id": "...", "name": "..."}],
    "last_sync": "2025-07-28T10:00:00Z"
}

# Get changes since timestamp:
GET /api/v1/sync/changes?since=2025-07-28T10:00:00Z

# Inbetweenies protocol:
POST /api/v1/sync/request (initial sync request)
POST /api/v1/sync/push (push changes)
POST /api/v1/sync/ack (acknowledge completion)
"""

from datetime import datetime, UTC
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from inbetweenies.sync import ConflictResolution
from ...repositories import (
    AccessoryRepository,
    HomeRepository,
    RoomRepository,
    UserRepository,
)

router = APIRouter()


class SyncRequest(BaseModel):
    """Sync request with entities to sync."""
    homes: List[Dict] = []
    rooms: List[Dict] = []
    accessories: List[Dict] = []
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
    home_repo = HomeRepository()
    room_repo = RoomRepository()
    accessory_repo = AccessoryRepository()
    user_repo = UserRepository()
    
    synced_counts = {
        "homes": 0,
        "rooms": 0,
        "accessories": 0,
        "users": 0
    }
    conflicts = []
    
    # Sync homes
    for home_data in request.homes:
        _, updated, conflict = await home_repo.sync_entity(db, home_data)
        if updated:
            synced_counts["homes"] += 1
        if conflict:
            conflicts.append(conflict)
    
    # Sync rooms
    for room_data in request.rooms:
        _, updated, conflict = await room_repo.sync_entity(db, room_data)
        if updated:
            synced_counts["rooms"] += 1
        if conflict:
            conflicts.append(conflict)
    
    # Sync accessories
    for accessory_data in request.accessories:
        _, updated, conflict = await accessory_repo.sync_entity(db, accessory_data)
        if updated:
            synced_counts["accessories"] += 1
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
    changes = {"homes": [], "rooms": [], "accessories": [], "users": []}
    
    if request.last_sync:
        # Get entities changed since last sync
        changed_homes = await home_repo.get_changes_since(db, request.last_sync)
        changed_rooms = await room_repo.get_changes_since(db, request.last_sync)
        changed_accessories = await accessory_repo.get_changes_since(db, request.last_sync)
        changed_users = await user_repo.get_changes_since(db, request.last_sync)
        
        changes["homes"] = [h.to_dict() for h in changed_homes]
        changes["rooms"] = [r.to_dict() for r in changed_rooms]
        changes["accessories"] = [a.to_dict() for a in changed_accessories]
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
        home_repo = HomeRepository()
        homes = await home_repo.get_changes_since(db, since, limit)
        changes["homes"] = [h.to_dict() for h in homes]
    
    if not entity_type or entity_type == "rooms":
        room_repo = RoomRepository()
        rooms = await room_repo.get_changes_since(db, since, limit)
        changes["rooms"] = [r.to_dict() for r in rooms]
    
    if not entity_type or entity_type == "devices":
        accessory_repo = AccessoryRepository()
        accessories = await accessory_repo.get_changes_since(db, since, limit)
        changes["accessories"] = [a.to_dict() for a in accessories]
    
    if not entity_type or entity_type == "users":
        user_repo = UserRepository()
        users = await user_repo.get_changes_since(db, since, limit)
        changes["users"] = [u.to_dict() for u in users]
    
    return {
        "changes": changes,
        "since": since.isoformat(),
        "timestamp": datetime.now(UTC).isoformat()
    }


# Inbetweenies Protocol Endpoints

class InbetweeniesyncRequest(BaseModel):
    """Sync request from Inbetweenies client."""
    type: str = "sync_request"
    client_id: str
    last_sync: Optional[str] = None
    entity_types: List[str] = ["devices", "entity_states", "rooms", "users", "houses"]
    include_deleted: bool = True


class InbetweeniesChange(BaseModel):
    """A single entity change."""
    entity_type: str
    entity_id: str
    operation: str  # create, update, delete
    data: Dict[str, Any]
    client_sync_id: Optional[str] = None


class InbetweeniesyncPush(BaseModel):
    """Push changes from client."""
    type: str = "sync_push"
    client_id: str
    changes: List[InbetweeniesChange]


class InbetweeniesyncAck(BaseModel):
    """Sync acknowledgment."""
    type: str = "sync_ack"
    client_id: str
    sync_completed_at: str


@router.post("/request")
async def inbetweenies_sync_request(
    request: InbetweeniesyncRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Handle Inbetweenies sync request - return changes since last sync."""
    last_sync = None
    if request.last_sync:
        last_sync = datetime.fromisoformat(request.last_sync.replace("Z", "+00:00"))
    
    print(f"DEBUG: Sync request from {request.client_id}, last_sync={last_sync}, entity_types={request.entity_types}")
        
    changes = []
    conflicts = []
    
    # Get changes for each entity type
    repo_map = {
        "homes": HomeRepository(),
        "rooms": RoomRepository(),
        "accessories": AccessoryRepository(),
        "users": UserRepository()
    }
    
    for entity_type in request.entity_types:
        if entity_type in repo_map:
            repo = repo_map[entity_type]
            
            # Get entities modified since last sync
            if last_sync and hasattr(repo, 'get_changes_since'):
                entities = await repo.get_changes_since(db, last_sync)
            else:
                entities = await repo.get_all(db)
            
            # Debug logging
            print(f"DEBUG: Entity type {entity_type}: found {len(entities)} entities")
            
            for entity in entities:
                # Check if modified since last sync
                if last_sync and hasattr(entity, 'updated_at'):
                    if entity.updated_at <= last_sync:
                        continue
                        
                # Add to changes
                entity_dict = entity.to_dict() if hasattr(entity, 'to_dict') else {}
                change_data = {
                    "entity_type": "accessory" if entity_type == "accessories" else entity_type.rstrip("s"),  # Remove plural correctly
                    "entity_id": entity.id,
                    "operation": "update",  # TODO: Track creates/deletes
                    "data": entity_dict,
                    "updated_at": entity.updated_at.isoformat() if hasattr(entity, 'updated_at') else datetime.now(UTC).isoformat(),
                    "sync_id": getattr(entity, 'sync_id', f"server-{entity.id}")
                }
                changes.append(change_data)
                
    print(f"DEBUG: Returning {len(changes)} changes")
    
    return {
        "type": "sync_delta",
        "server_time": datetime.now(UTC).isoformat(),
        "changes": changes,
        "conflicts": conflicts,
        "more": False
    }


@router.post("/push")
async def inbetweenies_sync_push(
    push: InbetweeniesyncPush,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Handle push from Inbetweenies client - apply changes and return results."""
    applied = []
    conflicts = []
    
    repo_map = {
        "home": HomeRepository(),
        "room": RoomRepository(),
        "accessory": AccessoryRepository(),
        "user": UserRepository()
    }
    
    for change in push.changes:
        entity_type = change.entity_type
        entity_id = change.entity_id
        operation = change.operation
        data = change.data
        client_sync_id = change.client_sync_id
        
        repo = repo_map.get(entity_type)
        if not repo:
            continue
            
        try:
            if operation == "delete":
                success = await repo.delete(db, entity_id)
                if success:
                    applied.append({
                        "client_sync_id": client_sync_id,
                        "server_sync_id": f"server-{entity_id}",
                        "status": "applied"
                    })
            else:
                # Use sync_entity method if available
                if hasattr(repo, 'sync_entity'):
                    entity, updated, conflict = await repo.sync_entity(db, data)
                    if conflict:
                        conflicts.append({
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "reason": "newer_on_server",
                            "server_version": entity.to_dict() if hasattr(entity, 'to_dict') else {},
                            "client_version": data,
                            "resolution": "server_wins"
                        })
                    elif updated:
                        applied.append({
                            "client_sync_id": client_sync_id,
                            "server_sync_id": f"server-{entity_id}",
                            "status": "applied"
                        })
                else:
                    # Fallback to create/update
                    existing = await repo.get(entity_id)
                    if existing:
                        await repo.update(entity_id, **data)
                    else:
                        await repo.create(**data)
                    applied.append({
                        "client_sync_id": client_sync_id,
                        "server_sync_id": f"server-{entity_id}",
                        "status": "applied"
                    })
                    
        except Exception as e:
            # Log error but continue
            print(f"Error applying change {entity_id}: {e}")
            
    await db.commit()
    
    return {
        "type": "sync_result",
        "applied": applied,
        "conflicts": conflicts
    }


@router.post("/ack")
async def inbetweenies_sync_acknowledge(
    ack: InbetweeniesyncAck,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Acknowledge Inbetweenies sync completion."""
    # In a real implementation, we might track client sync state
    return {
        "type": "sync_ack_response",
        "status": "acknowledged",
        "server_time": datetime.now(UTC).isoformat()
    }