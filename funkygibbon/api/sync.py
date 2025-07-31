"""
Sync API endpoints for the enhanced Inbetweenies protocol.

Handles sync requests, conflict resolution, and delta synchronization
between FunkyGibbon server and clients.
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.database import get_db
from funkygibbon.sync.versioning import VersionManager
from funkygibbon.sync.conflict_resolution import ConflictResolver, ConflictStrategy
from funkygibbon.sync.delta import DeltaSyncEngine
from inbetweenies.models import Entity, EntityRelationship, EntityType
from inbetweenies.sync import (
    VectorClock, EntityChange, RelationshipChange, SyncChange,
    SyncFilters, SyncRequest, ConflictInfo, SyncStats, SyncResponse
)


# Router
router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


class SyncHandler:
    """Handle sync protocol requests"""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.version_manager = VersionManager(db_session)
        self.conflict_resolver = ConflictResolver()
        self.delta_engine = DeltaSyncEngine(db_session)
    
    async def handle_sync_request(self, request: SyncRequest) -> SyncResponse:
        """Process sync request and return changes"""
        start_time = datetime.now(timezone.utc)
        
        # Validate protocol version
        if request.protocol_version != "inbetweenies-v2":
            raise HTTPException(status_code=400, detail="Unsupported protocol version")
        
        # Process incoming changes
        conflicts = []
        entities_synced = 0
        relationships_synced = 0
        
        for change in request.changes:
            if change.change_type == "create":
                await self._handle_create(change)
                entities_synced += 1
            elif change.change_type == "update":
                conflict = await self._handle_update(change)
                if conflict:
                    conflicts.append(conflict)
                entities_synced += 1
            elif change.change_type == "delete":
                await self._handle_delete(change)
                entities_synced += 1
            
            # Process relationships
            relationships_synced += len(change.relationships)
        
        # Get changes to send back based on sync type
        response_changes = []
        
        if request.sync_type == "delta":
            # Get last sync time for device
            last_sync = self.delta_engine.get_last_sync_time(request.device_id)
            if not last_sync:
                # First sync, use full sync
                last_sync = datetime.min.replace(tzinfo=timezone.utc)
            
            # Calculate delta
            entity_types = None
            if request.filters and request.filters.entity_types:
                entity_types = [EntityType(et) for et in request.filters.entity_types]
            
            delta = await self.delta_engine.calculate_delta(last_sync, entity_types)
            
            # Convert delta to changes
            for entity in delta.added_entities:
                response_changes.append(SyncChange(
                    change_type="create",
                    entity=self._entity_to_change(entity)
                ))
            
            for entity in delta.modified_entities:
                response_changes.append(SyncChange(
                    change_type="update",
                    entity=self._entity_to_change(entity)
                ))
        
        elif request.sync_type == "full":
            # Return all entities
            entities = await self._get_all_entities(request.filters)
            for entity in entities:
                response_changes.append(SyncChange(
                    change_type="create",
                    entity=self._entity_to_change(entity)
                ))
        
        # Update sync time
        self.delta_engine.update_last_sync_time(request.device_id, datetime.now(timezone.utc))
        
        # Calculate duration
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        # Build response
        return SyncResponse(
            sync_type=request.sync_type,
            changes=response_changes,
            conflicts=conflicts,
            vector_clock=request.vector_clock,  # Echo back for now
            sync_stats=SyncStats(
                entities_synced=entities_synced,
                relationships_synced=relationships_synced,
                conflicts_resolved=len(conflicts),
                duration_ms=duration_ms
            )
        )
    
    async def _handle_create(self, change: SyncChange):
        """Handle entity creation"""
        if not change.entity:
            return
            
        # Check if entity already exists - get latest version
        from sqlalchemy import select
        stmt = select(Entity).where(Entity.id == change.entity.id).order_by(Entity.created_at.desc()).limit(1)
        result = await self.db_session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            # Already exists, this is a conflict
            # For now, skip creation
            return
        
        # Create new entity
        from inbetweenies.models import SourceType as ST
        entity = Entity(
            id=change.entity.id,
            version=change.entity.version,
            entity_type=EntityType(change.entity.entity_type),
            name=change.entity.name,
            content=change.entity.content,
            source_type=ST(change.entity.source_type),
            user_id=change.entity.user_id,
            parent_versions=change.entity.parent_versions
        )
        
        self.db_session.add(entity)
        await self.db_session.commit()
    
    async def _handle_update(self, change: SyncChange) -> Optional[ConflictInfo]:
        """Handle entity update"""
        if not change.entity:
            return None
            
        # Get existing entity - need to get the latest version
        from sqlalchemy import select
        stmt = select(Entity).where(Entity.id == change.entity.id).order_by(Entity.created_at.desc()).limit(1)
        result = await self.db_session.execute(stmt)
        existing = result.scalar_one_or_none()
        if not existing:
            # Doesn't exist, create it
            await self._handle_create(change)
            return None
        
        # Check for conflict
        if existing.version != change.entity.parent_versions[0] if change.entity.parent_versions else None:
            # Version conflict
            from inbetweenies.models import SourceType as ST
            remote_entity = Entity(
                id=change.entity.id,
                version=change.entity.version,
                entity_type=EntityType(change.entity.entity_type),
                name=change.entity.name,
                content=change.entity.content,
                source_type=ST(change.entity.source_type),
                user_id=change.entity.user_id,
                parent_versions=change.entity.parent_versions
            )
            
            # Resolve conflict
            resolution = self.conflict_resolver.resolve_conflict(
                existing, remote_entity, ConflictStrategy.MERGE
            )
            
            if resolution.resolved_entity:
                # Update with resolved entity
                existing.version = resolution.resolved_entity.version
                existing.name = resolution.resolved_entity.name
                existing.content = resolution.resolved_entity.content
                existing.parent_versions = resolution.resolved_entity.parent_versions
                existing.updated_at = datetime.now(timezone.utc)
                
                await self.db_session.commit()
                
                return ConflictInfo(
                    entity_id=change.entity.id,
                    local_version=existing.version,
                    remote_version=change.entity.version,
                    resolution_strategy="merge",
                    resolved_version=resolution.resolved_entity.version
                )
        else:
            # No conflict, update
            existing.version = change.entity.version
            existing.name = change.entity.name
            existing.content = change.entity.content
            existing.parent_versions = change.entity.parent_versions
            existing.updated_at = datetime.now(timezone.utc)
            
            await self.db_session.commit()
        
        return None
    
    async def _handle_delete(self, change: SyncChange):
        """Handle entity deletion"""
        if not change.entity:
            return
            
        # Get entity to delete - need to find the latest version
        from sqlalchemy import select
        stmt = select(Entity).where(Entity.id == change.entity.id).order_by(Entity.created_at.desc()).limit(1)
        result = await self.db_session.execute(stmt)
        entity = result.scalar_one_or_none()
        if entity:
            await self.db_session.delete(entity)
            await self.db_session.commit()
    
    def _entity_to_change(self, entity: Entity) -> EntityChange:
        """Convert entity to change format"""
        return EntityChange(
            id=entity.id,
            version=entity.version,
            entity_type=entity.entity_type.value,
            name=entity.name,
            content=entity.content or {},
            source_type=entity.source_type.value,
            user_id=entity.user_id,
            parent_versions=entity.parent_versions
        )
    
    async def _get_all_entities(self, filters: Optional[SyncFilters]) -> List[Entity]:
        """Get all entities with optional filters"""
        from sqlalchemy import select
        
        query = select(Entity)
        
        if filters:
            if filters.entity_types:
                entity_types = [EntityType(et) for et in filters.entity_types]
                query = query.where(Entity.entity_type.in_(entity_types))
            
            if filters.since:
                query = query.where(Entity.updated_at >= filters.since)
            
            if filters.modified_by:
                query = query.where(Entity.user_id.in_(filters.modified_by))
        
        result = await self.db_session.execute(query)
        return list(result.scalars().all())


@router.post("/", response_model=SyncResponse)
async def sync_data(
    request: SyncRequest,
    db: AsyncSession = Depends(get_db)
):
    """Main sync endpoint"""
    handler = SyncHandler(db)
    return await handler.handle_sync_request(request)


@router.get("/status")
async def sync_status(
    device_id: str = Query(..., description="Device ID to check sync status"),
    db: AsyncSession = Depends(get_db)
):
    """Get sync status for a device"""
    delta_engine = DeltaSyncEngine(db)
    last_sync = delta_engine.get_last_sync_time(device_id)
    
    return {
        "device_id": device_id,
        "last_sync": last_sync.isoformat() if last_sync else None,
        "protocol_version": "inbetweenies-v2"
    }


@router.get("/conflicts")
async def get_pending_conflicts(
    db: AsyncSession = Depends(get_db)
):
    """Get all pending manual conflict resolutions"""
    conflict_resolver = ConflictResolver()
    return {
        "conflicts": conflict_resolver.get_pending_resolutions()
    }


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    resolution: Dict,
    db: AsyncSession = Depends(get_db)
):
    """Manually resolve a conflict"""
    conflict_resolver = ConflictResolver()
    success = conflict_resolver.resolve_manual_conflict(conflict_id, resolution)
    
    if not success:
        raise HTTPException(status_code=404, detail="Conflict not found")
    
    return {"status": "resolved", "conflict_id": conflict_id}