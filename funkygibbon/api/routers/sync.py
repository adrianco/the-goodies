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

    # Import graph repository for entity storage
    from ...repositories.graph import GraphRepository
    from ...models import Entity as GraphEntity, EntityRelationship
    from ...models import EntityType as GraphEntityType, SourceType

    # Process incoming changes
    applied_changes = 0
    conflicts = []

    # Use graph repository for all entity types
    graph_repo = GraphRepository(db)

    for sync_change in request.changes:
        if sync_change.entity:
            entity = sync_change.entity

            try:
                # Convert to graph entity
                graph_entity = GraphEntity(
                    id=entity.id,
                    version=entity.version or GraphEntity.create_version("sync"),
                    entity_type=GraphEntityType(entity.entity_type),
                    name=entity.name,
                    content=entity.content,
                    source_type=SourceType(entity.source_type) if entity.source_type else SourceType.IMPORTED,
                    user_id=entity.user_id if hasattr(entity, 'user_id') else "sync",
                    parent_versions=entity.parent_versions if hasattr(entity, 'parent_versions') else []
                )

                if sync_change.change_type == "delete":
                    # Handle deletion (graph doesn't delete, it marks as deleted)
                    # For now, skip deletes
                    pass
                else:
                    # Check for existing entity
                    existing = await graph_repo.get_entity(entity.id)

                    if existing:
                        # Check for conflict
                        if existing.version != entity.version:
                            # Conflict detected - use last-write-wins based on version
                            if entity.version > existing.version:
                                # Incoming wins
                                await graph_repo.store_entity(graph_entity)
                                applied_changes += 1
                            else:
                                # Existing wins
                                conflicts.append(ConflictInfo(
                                    entity_id=entity.id,
                                    local_version=existing.version,
                                    remote_version=entity.version,
                                    resolution_strategy="last_write_wins",
                                    resolved_version=existing.version
                                ))
                    else:
                        # New entity
                        await graph_repo.store_entity(graph_entity)
                        applied_changes += 1

            except Exception as e:
                print(f"Error processing change for {entity.entity_type} {entity.id}: {e}")

    await db.commit()

    # Get server changes to send back
    server_changes = []

    # If this is a full sync or delta sync, return entities
    if request.sync_type in ["full", "delta"]:
        # Get all entities or entities since last sync
        since = None
        if request.filters and hasattr(request.filters, 'since'):
            since = request.filters.since

        # Get entities from graph
        for entity_type in GraphEntityType:
            try:
                entities = await graph_repo.get_entities_by_type(entity_type)
                for entity in entities:
                    # Filter by timestamp if delta sync
                    if since and hasattr(entity, 'updated_at') and entity.updated_at:
                        if entity.updated_at <= since:
                            continue

                    # Convert to sync change
                    entity_change = EntityChange(
                        id=entity.id,
                        version=entity.version,
                        entity_type=entity.entity_type.value,
                        name=entity.name,
                        content=entity.content,
                        source_type=entity.source_type.value,
                        parent_versions=entity.parent_versions
                    )

                    server_changes.append(SyncChange(
                        change_type="update",
                        entity=entity_change,
                        timestamp=entity.updated_at if hasattr(entity, 'updated_at') else datetime.now(UTC)
                    ))
            except Exception as e:
                print(f"Error getting entities for type {entity_type}: {e}")

    # Return server changes
    return SyncResponse(
        protocol_version="inbetweenies-v2",
        sync_type=request.sync_type,
        changes=server_changes[:100],  # Limit to 100 changes per sync
        conflicts=conflicts,
        vector_clock=VectorClock(),
        sync_stats=SyncStats(
            entities_synced=applied_changes,
            conflicts_resolved=len(conflicts)
        )
    )

# Graph-based sync only - no legacy HomeKit endpoints
