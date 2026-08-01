"""
Sync API endpoints for the enhanced Inbetweenies protocol.

Handles sync requests, conflict resolution, and delta synchronization
between FunkyGibbon server and clients.
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.database import get_db
from inbetweenies.models import (
    Entity, EntityRelationship, EntityType, RelationshipType, SourceType,
)
from inbetweenies.sync import (
    VectorClock, EntityChange, RelationshipChange, SyncChange,
    SyncFilters, SyncRequest, ConflictInfo, SyncStats, SyncResponse,
    ConflictResolver,
)


# Router
router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to timezone-aware UTC (None passes through)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SyncHandler:
    """Handle sync protocol requests (inbetweenies-v2, see PROTOCOL.md).

    Entities are immutable and versioned: every change is a new version row, a
    delete is a tombstone version (``content.deleted = true``). Delta sync is
    stateless — the client supplies ``filters.since`` (the ``server_time`` it
    persisted from the previous response) and the server returns the current
    state of everything with ``updated_at`` strictly greater than it.
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def handle_sync_request(self, request: SyncRequest) -> SyncResponse:
        """Process sync request and return changes."""
        start_time = datetime.now(timezone.utc)

        if request.protocol_version != "inbetweenies-v2":
            raise HTTPException(status_code=400, detail="Unsupported protocol version")

        # --- Apply incoming (client -> server) changes ---
        conflicts: List[ConflictInfo] = []
        # Per-id acknowledgement. The client clears its pending marks from these,
        # so an id may only appear once its change is genuinely persisted (or was
        # already in the desired state). Anything omitted here is retried on the
        # next sync — aggregate counts cannot express a partially-applied batch.
        applied: List[str] = []
        applied_relationships: List[str] = []

        for change in request.changes:
            if change.change_type in ("create", "update"):
                persisted = await self._apply_incoming(change, conflicts)
            elif change.change_type == "delete":
                persisted = await self._handle_delete(change)
            else:
                persisted = False
            # `change.entity` is optional: a change may carry only relationships
            # (its endpoints are already in sync), in which case there is no
            # entity id to acknowledge.
            if persisted and change.entity and change.entity.id not in applied:
                applied.append(change.entity.id)

        # Relationships only after every entity in the batch has been applied:
        # an edge references its endpoints at a specific version and the table
        # carries a composite FK on (entity_id, entity_version), so the endpoints
        # must already exist (PROTOCOL.md §5, entities before relationships).
        for change in request.changes:
            for relationship in change.relationships:
                if await self._persist_relationship(relationship, request.user_id):
                    if relationship.id not in applied_relationships:
                        applied_relationships.append(relationship.id)

        # server_time is the watermark the client persists and sends back as the
        # next `since`. Capture it now; everything applied above is <= it.
        server_time = datetime.now(timezone.utc)

        # --- Compute outgoing (server -> client) changes ---
        latest = await self._latest_entities()
        entities = list(latest.values())

        if request.sync_type == "delta":
            since = _to_utc(request.filters.since) if (request.filters and request.filters.since) else None
            if since is not None:
                # Strictly greater than `since` (exclusive lower bound, §4).
                entities = [e for e in entities
                            if (_to_utc(e.updated_at) or datetime.min.replace(tzinfo=timezone.utc)) > since]

        # Filters (apply to both full and delta).
        if request.filters:
            if request.filters.entity_types:
                wanted = {EntityType(et) for et in request.filters.entity_types}
                entities = [e for e in entities if e.entity_type in wanted]
            if request.filters.modified_by:
                wanted_users = set(request.filters.modified_by)
                entities = [e for e in entities if e.user_id in wanted_users]

        response_changes = []
        for entity in entities:
            deleted = bool((entity.content or {}).get("deleted"))
            response_changes.append(SyncChange(
                change_type="delete" if deleted else "update",
                entity=self._entity_to_change(entity),
            ))

        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        return SyncResponse(
            sync_type=request.sync_type,
            changes=response_changes,
            conflicts=conflicts,
            applied=applied,
            applied_relationships=applied_relationships,
            vector_clock=request.vector_clock,  # RESERVED — echoed, never read
            server_time=server_time.isoformat(),
            sync_stats=SyncStats(
                # Counts stay consistent with the acknowledgement lists: they
                # report what landed, not what was merely attempted.
                entities_synced=len(applied),
                relationships_synced=len(applied_relationships),
                conflicts_resolved=len(conflicts),
                duration_ms=duration_ms,
            ),
        )

    async def _latest_entities(self) -> Dict[str, Entity]:
        """Return the latest (lexically greatest version) row per entity id."""
        result = await self.db_session.execute(select(Entity))
        latest: Dict[str, Entity] = {}
        for entity in result.scalars().all():
            current = latest.get(entity.id)
            if current is None or entity.version > current.version:
                latest[entity.id] = entity
        return latest

    async def _insert_version(self, change: SyncChange, *, deleted: bool = False) -> None:
        """Insert a new immutable version row (idempotent on (id, version))."""
        existing_row = await self.db_session.get(
            Entity, (change.entity.id, change.entity.version)
        )
        if existing_row is not None:
            return  # already applied this exact version

        content = dict(change.entity.content or {})
        if deleted:
            content["deleted"] = True
        now = datetime.now(timezone.utc)
        entity = Entity(
            id=change.entity.id,
            version=change.entity.version,
            entity_type=EntityType(change.entity.entity_type),
            name=change.entity.name,
            content=content,
            source_type=SourceType(change.entity.source_type),
            user_id=change.entity.user_id,
            parent_versions=change.entity.parent_versions or [],
            created_at=now,
            updated_at=now,
        )
        self.db_session.add(entity)
        await self.db_session.commit()

    async def _apply_incoming(self, change: SyncChange, conflicts: List[ConflictInfo]) -> bool:
        """Apply a create/update: fast-forward if based on our latest, else resolve.

        Returns True when our stored state now reflects this change — either it
        persisted, or it was already in the desired state. False means the client
        must keep its pending mark and retry (it lost conflict resolution, or the
        change carried no entity to apply).
        """
        if not change.entity:
            return False  # relationships-only change; nothing to apply here

        latest = await self._latest_entities()
        existing = latest.get(change.entity.id)

        if existing is None:
            await self._insert_version(change)
            return True

        if existing.version == change.entity.version:
            return True  # idempotent re-send: already in the desired state

        parents = change.entity.parent_versions or []

        if not parents:
            # An update that names no parent_versions for an id we already hold is
            # a blind overwrite: the client cannot have seen our version, so this
            # is by definition not a fast-forward. Decide it through the §7 rule
            # like any other concurrent edit instead of letting it through
            # unchallenged. Record the version it supersedes if it wins, so the
            # version DAG stays connected (same repair as the tombstone path).
            change.entity.parent_versions = [existing.version]
            return await self._resolve_conflict(change, existing, conflicts)

        if existing.version in parents:
            await self._insert_version(change)  # fast-forward
            return True

        # Client edited from a version we have since superseded.
        return await self._resolve_conflict(change, existing, conflicts)

    async def _resolve_conflict(self, change: SyncChange, existing: Entity,
                                conflicts: List[ConflictInfo]) -> bool:
        """Resolve a concurrent edit canonically (LWW + version tiebreak, §7).

        Returns True only if the remote version won and was stored; a losing
        remote is deliberately not acknowledged, so the client retries it.
        """
        local = {"updated_at": _to_utc(existing.updated_at), "version": existing.version}
        remote = {
            "updated_at": Entity.version_timestamp(change.entity.version) or _to_utc(existing.updated_at),
            "version": change.entity.version,
        }
        resolution = ConflictResolver.resolve(local, remote)
        remote_wins = resolution.winner.get("version") == change.entity.version

        if remote_wins:
            await self._insert_version(change)
            resolved_version = change.entity.version
        else:
            resolved_version = existing.version

        conflicts.append(ConflictInfo(
            entity_id=change.entity.id,
            local_version=existing.version,
            remote_version=change.entity.version,
            resolution_strategy=resolution.reason,
            resolved_version=resolved_version,
        ))
        return remote_wins

    async def _handle_delete(self, change: SyncChange) -> bool:
        """Apply a delete as a tombstone version (content.deleted = true, §8).

        Returns True whenever the entity is deleted server-side afterwards —
        including "nothing to delete" and "already tombstoned", since the client's
        intent holds in both cases and withholding the acknowledgement would make
        it retry forever.
        """
        if not change.entity:
            return False
        latest = await self._latest_entities()
        existing = latest.get(change.entity.id)
        if existing is None:
            return True  # nothing to delete - the desired state already holds
        if bool((existing.content or {}).get("deleted")):
            return True  # already tombstoned
        # If the client didn't set the prior version as a parent, record it so the
        # tombstone supersedes the latest known version.
        if existing.version not in (change.entity.parent_versions or []):
            change.entity.parent_versions = [existing.version]
        await self._insert_version(change, deleted=True)
        return True

    async def _persist_relationship(self, relationship: RelationshipChange,
                                    user_id: Optional[str] = None) -> bool:
        """Persist one inbound edge; returns True if it is now stored (§3.1).

        Idempotent on the relationship ``id`` (the primary key): re-pushing the
        same edge updates that row rather than inserting a duplicate. Unlike
        entities, relationships are not versioned — the row itself carries the
        endpoint versions, so an edge that follows its endpoints onto a new
        entity version is the same row with new ``*_entity_version`` values.
        """
        try:
            rel_type = RelationshipType(relationship.relationship_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown relationship_type: {relationship.relationship_type}",
            )

        # Both endpoints must exist at exactly the referenced version — the table
        # has a composite FK on (entity_id, entity_version). A dangling endpoint
        # is skipped rather than fatal: the entity may simply not have reached us
        # yet, and the caller reports the shortfall via sync_stats.
        for entity_id, entity_version in (
            (relationship.from_entity_id, relationship.from_entity_version),
            (relationship.to_entity_id, relationship.to_entity_version),
        ):
            if await self.db_session.get(Entity, (entity_id, entity_version)) is None:
                return False

        now = datetime.now(timezone.utc)
        properties = dict(relationship.properties or {})
        existing = await self.db_session.get(EntityRelationship, relationship.id)

        if existing is None:
            self.db_session.add(EntityRelationship(
                id=relationship.id,
                from_entity_id=relationship.from_entity_id,
                from_entity_version=relationship.from_entity_version,
                to_entity_id=relationship.to_entity_id,
                to_entity_version=relationship.to_entity_version,
                relationship_type=rel_type,
                properties=properties,
                user_id=user_id,
                created_at=now,
                updated_at=now,
            ))
        else:
            existing.from_entity_id = relationship.from_entity_id
            existing.from_entity_version = relationship.from_entity_version
            existing.to_entity_id = relationship.to_entity_id
            existing.to_entity_version = relationship.to_entity_version
            existing.relationship_type = rel_type
            existing.properties = properties
            existing.user_id = user_id
            existing.updated_at = now

        await self.db_session.commit()
        return True

    def _entity_to_change(self, entity: Entity) -> EntityChange:
        """Convert a stored entity to its wire EntityChange."""
        return EntityChange(
            id=entity.id,
            version=entity.version,
            entity_type=entity.entity_type.value,
            name=entity.name,
            content=entity.content or {},
            source_type=entity.source_type.value,
            user_id=entity.user_id,
            parent_versions=entity.parent_versions or [],
        )


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
    device_id: str = Query(..., description="Device ID (informational)"),
    db: AsyncSession = Depends(get_db)
):
    """Sync status. Delta sync is stateless (the client holds its own watermark
    via the response `server_time`), so this just reports the current server time
    the client can use as a `since` baseline."""
    return {
        "device_id": device_id,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "protocol_version": "inbetweenies-v2",
    }


@router.get("/conflicts")
async def get_pending_conflicts(db: AsyncSession = Depends(get_db)):
    """Conflicts are resolved automatically and deterministically during sync
    (PROTOCOL.md §7); there is no manual-resolution queue. Always empty."""
    return {"conflicts": []}


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    resolution: Dict,
    db: AsyncSession = Depends(get_db)
):
    """Manual conflict resolution is not supported — conflicts auto-resolve."""
    raise HTTPException(
        status_code=404,
        detail="No manual conflict queue; conflicts auto-resolve during sync.",
    )
