"""
Sync API endpoints for the enhanced Inbetweenies protocol.

Handles sync requests, conflict resolution, and delta synchronization
between FunkyGibbon server and clients.
"""

import hashlib
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.database import get_db
from funkygibbon.graph.index_service import write_through_applied_changes
from inbetweenies.models import (
    Entity, EntityRelationship, EntityType, RelationshipType, SourceType,
)
from inbetweenies.sync import (
    VectorClock, EntityChange, RelationshipChange, SyncChange,
    SyncFilters, SyncRequest, ConflictInfo, SyncStats, SyncResponse,
    ConflictResolver,
)


# Router
logger = logging.getLogger(__name__)

# ADR-002 §4. Sized so a first full sync of a house-scale graph is one or two
# pages rather than one unbounded body; the loop is what matters, not the number.
PAGE_SIZE = 500

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

        # ADR-011 §3: ONE transaction for the whole push. _insert_version and
        # _persist_relationship only flush, so nothing above this line is
        # durable yet. Committing per change — as this did — meant a crash
        # mid-batch left the server half-updated with no record of how far it
        # got, and the client holding acknowledgements for work that had been
        # rolled back around it. Either the batch lands or none of it does.
        try:
            await self.db_session.commit()
        except Exception:
            await self.db_session.rollback()
            raise

        # ADR-003 decision 2: sync apply is a mutation path, so it writes through
        # to the graph index in the same code path as the storage write. Without
        # this, entities arriving by sync were invisible to find_path until the
        # process restarted (finding F2). Runs after both loops so `applied` and
        # `applied_relationships` are complete; ids that lost conflict resolution
        # are absent from them and are correctly not indexed.
        await write_through_applied_changes(
            self.db_session,
            entity_ids=applied,
            relationship_ids=applied_relationships,
        )

        # server_time is the watermark the client persists and sends back as the
        # next `since`. Capture it now; everything applied above is <= it.
        server_time = datetime.now(timezone.utc)

        # --- Compute outgoing (server -> client) changes ---
        entities = await self._outgoing_entities(request)

        # Filters (apply to both full and delta).
        if request.filters:
            if request.filters.entity_types:
                wanted = {EntityType(et) for et in request.filters.entity_types}
                entities = [e for e in entities if e.entity_type in wanted]
            if request.filters.modified_by:
                wanted_users = set(request.filters.modified_by)
                entities = [e for e in entities if e.user_id in wanted_users]

        # ADR-002 §4: cap the page and hand back a resume point. Responses were
        # unbounded — a first full sync returned the entire graph in one body.
        # `cursor` is the highest server_seq in this page; the client loops
        # until it comes back null.
        more_remain = len(entities) > PAGE_SIZE
        entities = entities[:PAGE_SIZE]
        cursor = None
        if more_remain and entities:
            cursor = str(max(e.server_seq or 0 for e in entities))

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
            cursor=cursor,
            state_digest=await self._state_digest(),
            sync_stats=SyncStats(
                # Counts stay consistent with the acknowledgement lists: they
                # report what landed, not what was merely attempted.
                entities_synced=len(applied),
                relationships_synced=len(applied_relationships),
                conflicts_resolved=len(conflicts),
                duration_ms=duration_ms,
            ),
        )

    async def _outgoing_entities(self, request: SyncRequest) -> List[Entity]:
        """The current rows this request should receive, in replication order.

        Two delta mechanisms, deliberately:

        * `cursor` — a server_seq watermark. Exact, clock-independent, and the
          only one that can paginate, since it defines a total order over rows.
        * `filters.since` — the original wall-clock bound, kept working because
          KittenKong and blowing-off both persist `server_time` today
          (PROTOCOL.md §4). Breaking it would strand a live client mid-upgrade.

        A client sending both gets the cursor: it is the stronger statement, and
        `updated_at` cannot separate rows written in the same microsecond.
        """
        stmt = select(Entity).where(Entity.is_latest.is_(True))

        if request.sync_type == "delta":
            if request.cursor:
                try:
                    stmt = stmt.where(Entity.server_seq > int(request.cursor))
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"cursor must be a server_seq integer, got {request.cursor!r}",
                    )
            elif request.filters and request.filters.since:
                since = _to_utc(request.filters.since)
                # Strictly greater than `since` (exclusive lower bound, §4).
                stmt = stmt.where(Entity.updated_at > since)

        # Ordered by the replication axis so paging is stable: without this the
        # page boundary is whatever order the database happened to return, and a
        # row can be skipped or repeated across pages.
        stmt = stmt.order_by(Entity.server_seq)
        result = await self.db_session.execute(stmt)
        return list(result.scalars().all())

    async def _state_digest(self) -> str:
        """sha256 over the sorted (id, version) set of every current row.

        ADR-011 §4. Divergence between a server and a replica is otherwise
        undetectable: both sides believe they are in sync, because both applied
        every change they were told about. A client compares this against the
        same computation over its own cache and resyncs on mismatch.

        Deliberately the degenerate form of the Merkle tree in the deleted sync
        stack: at this scale one hash over the id/version pairs delivers the
        verification value, and a tree would be machinery without a payload.
        """
        result = await self.db_session.execute(
            select(Entity.id, Entity.version)
            .where(Entity.is_latest.is_(True))
            .order_by(Entity.id)
        )
        digest = hashlib.sha256()
        for entity_id, version in result.all():
            digest.update(f"{entity_id}\x1f{version}\x1e".encode())
        return digest.hexdigest()

    async def _latest_entities(self) -> Dict[str, Entity]:
        """Return the current row per entity id, read from is_latest (ADR-002 §1).

        Was `select(Entity)` — every version of every entity — reduced to
        latest-per-id in Python, once per sync request AND once per pushed
        change. Now the database answers the question it is asked.

        This also ends the disagreement over what "latest" meant: three call
        sites inferred it independently (lexically greatest version here,
        greatest created_at in GraphRepository, LWW on updated_at in conflict
        resolution), so a preserved losing version could be served as current
        by one and not the other. Resolution now records its outcome.
        """
        result = await self.db_session.execute(
            select(Entity).where(Entity.is_latest.is_(True))
        )
        return {entity.id: entity for entity in result.scalars().all()}

    async def _current_row(self, entity_id: str) -> Optional[Entity]:
        """The current row for one id — the push path's version of the above.

        ADR-002 §3: applying a change needs the latest row for that id, not a
        table scan. This is what made a 50-change push O(history x changes).
        """
        result = await self.db_session.execute(
            select(Entity).where(Entity.id == entity_id, Entity.is_latest.is_(True))
        )
        return result.scalars().first()

    async def _next_server_seq(self) -> int:
        """Allocate the next replication stamp.

        Gap-free and assigned in apply order, so a delta cursor is exact.
        Wall-clock cannot do this: two rows written in the same microsecond are
        indistinguishable to `updated_at > since`, and a clock adjustment can
        move rows across a cursor a client has already passed.
        """
        result = await self.db_session.execute(select(func.max(Entity.server_seq)))
        return (result.scalar() or 0) + 1

    async def _insert_version(
        self, change: SyncChange, *, deleted: bool = False, becomes_latest: bool = True
    ) -> None:
        """Insert a new immutable version row (idempotent on (id, version)).

        Args:
            becomes_latest: whether this version is the resolution winner. False
                stores it as history — a losing version preserved per ADR-011
                §2, which must never be served as current.

        Does NOT commit: the whole push batch is one transaction (ADR-011 §3),
        so a crash leaves nothing applied and nothing acknowledged rather than
        a half-applied batch.
        """
        existing_row = await self.db_session.get(
            Entity, (change.entity.id, change.entity.version)
        )
        if existing_row is not None:
            return  # already applied this exact version

        if becomes_latest:
            # Demote the incumbent in the same transaction, so there is never a
            # moment with two current rows for one id.
            await self.db_session.execute(
                update(Entity)
                .where(Entity.id == change.entity.id, Entity.is_latest.is_(True))
                .values(is_latest=False)
            )

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
            is_latest=becomes_latest,
            server_seq=await self._next_server_seq(),
        )
        self.db_session.add(entity)
        await self.db_session.flush()

    async def _apply_incoming(self, change: SyncChange, conflicts: List[ConflictInfo]) -> bool:
        """Apply a create/update: fast-forward if based on our latest, else resolve.

        Returns True when the change reached a terminal outcome and the client
        may drop its pending mark: it persisted, it was already in the desired
        state, or it lost resolution and was preserved as a non-latest row
        (ADR-011 §2 — losing is terminal; retrying cannot change it).

        False means retry. The only such case here is a change carrying no
        entity to apply.
        """
        if not change.entity:
            return False  # relationships-only change; nothing to apply here

        # ADR-002 §3: resolve THIS id, not the whole table. Scanning every
        # version of every entity once per pushed change is what made a
        # 50-change push cost O(history x changes).
        existing = await self._current_row(change.entity.id)

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

        Always returns True: the change was *processed*, which is what an ack
        means (ADR-011 §2). Winning and losing are both terminal outcomes, so
        neither should be retried.

        Withholding the ack from a loser — the previous behaviour — livelocks
        any client that guards its pending ids against pull-apply (ADR-011 §1,
        which KittenKong now implements): the guard blocks our version because
        the id is pending, the push loses and is not acked, the pending mark
        survives, and every subsequent sync repeats identically. The entity
        never converges on that client.

        Acking is only safe because the loser's content is preserved first —
        see _preserve_losing_version. An ack without preservation would be
        worse than the livelock: the client would drop its pending mark and
        later overwrite its own edit with our winner, losing it everywhere.
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
            await self._preserve_losing_version(change, existing)

        conflicts.append(ConflictInfo(
            entity_id=change.entity.id,
            local_version=existing.version,
            remote_version=change.entity.version,
            resolution_strategy=resolution.reason,
            resolved_version=resolved_version,
        ))
        return True

    async def _preserve_losing_version(self, change: SyncChange, existing: Entity) -> None:
        """Store a losing version as a non-latest row so its content survives.

        ADR-011 §2: a write may lose *prominence* but never *existence*. The
        row is already parented into the DAG, so preserving it is one insert
        and any human can recover the content from history.

        Unconditional since ADR-002 §1. It used to be guarded: "latest" was
        inferred from the version string, so a losing version that happened to
        sort above the winner would be promoted by the very act of preserving
        it, and such rows had to be dropped instead. is_latest records the
        resolution outcome, so a loser can be stored as history without any
        risk of being served — every version is preserved now, not just the
        conveniently-sorted ones.
        """
        await self._insert_version(change, becomes_latest=False)

    async def _handle_delete(self, change: SyncChange) -> bool:
        """Apply a delete as a tombstone version (content.deleted = true, §8).

        Returns True whenever the entity is deleted server-side afterwards —
        including "nothing to delete" and "already tombstoned", since the client's
        intent holds in both cases and withholding the acknowledgement would make
        it retry forever.
        """
        if not change.entity:
            return False
        # ADR-002 §3: resolve THIS id, not the whole table. Scanning every
        # version of every entity once per pushed change is what made a
        # 50-change push cost O(history x changes).
        existing = await self._current_row(change.entity.id)
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

        # Flush, not commit: this row belongs to the batch transaction opened
        # by handle_sync_request (ADR-011 §3).
        await self.db_session.flush()
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
