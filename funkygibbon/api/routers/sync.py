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
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from inbetweenies.sync.protocol import SyncRequest, SyncResponse
from ...repositories import (
    AccessoryRepository,
    HomeRepository,
    RoomRepository,
    UserRepository,
)

router = APIRouter()


@router.post("/", response_model=SyncResponse)
async def sync_entities(
    request: SyncRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Sync entities using Inbetweenies v2 protocol.
    
    Processes sync changes and returns server changes and conflicts.
    """
    from inbetweenies.sync.protocol import SyncStats, ConflictInfo, VectorClock, SyncChange, EntityChange
    
    # Process incoming changes
    applied_changes = 0
    conflicts = []
    
    repo_map = {
        "home": HomeRepository(),
        "room": RoomRepository(), 
        "accessory": AccessoryRepository(),
        "user": UserRepository()
    }
    
    for sync_change in request.changes:
        if sync_change.entity:
            entity = sync_change.entity
            entity_type = entity.entity_type
            
            repo = repo_map.get(entity_type)
            if not repo:
                continue
                
            try:
                # Convert entity data for repository
                entity_data = {
                    "id": entity.id,
                    "name": entity.name,
                    "sync_id": entity.version,
                    **entity.content
                }
                
                if sync_change.change_type == "delete":
                    if hasattr(repo, 'delete'):
                        await repo.delete(db, entity.id)
                        applied_changes += 1
                else:
                    # Use sync_entity if available
                    if hasattr(repo, 'sync_entity'):
                        _, updated, conflict = await repo.sync_entity(db, entity_data)
                        if updated:
                            applied_changes += 1
                        if conflict:
                            conflicts.append(ConflictInfo(
                                entity_id=entity.id,
                                local_version=conflict.local_version if hasattr(conflict, 'local_version') else "unknown",
                                remote_version=conflict.remote_version if hasattr(conflict, 'remote_version') else entity.version,
                                resolution_strategy="last_write_wins",
                                resolved_version=conflict.resolved_version if hasattr(conflict, 'resolved_version') else None
                            ))
                    
            except Exception as e:
                print(f"Error processing change for {entity_type} {entity.id}: {e}")
    
    await db.commit()
    
    # Return server changes (empty for now - client should use separate endpoint)
    return SyncResponse(
        protocol_version="inbetweenies-v2",
        sync_type=request.sync_type,
        changes=[],
        conflicts=conflicts,
        vector_clock=VectorClock(),
        sync_stats=SyncStats(
            entities_synced=applied_changes,
            conflicts_resolved=len(conflicts)
        )
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


# Legacy endpoints removed - only Inbetweenies v2 protocol supported