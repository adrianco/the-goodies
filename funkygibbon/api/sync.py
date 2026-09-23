"""
Sync API endpoints for the enhanced Inbetweenies protocol.

Handles sync requests, conflict resolution, and delta synchronization
between FunkyGibbon server and clients.
"""

import hashlib
import importlib
import logging
from functools import lru_cache
from typing import List, Dict, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.database import get_db
from funkygibbon.graph.index_service import write_through_applied_changes
from funkygibbon.repositories.graph import next_server_seq, stamp_relationship
from inbetweenies.models import (
    Entity, EntityRelationship,
)
# Interval clamps compare a wire datetime against a stored one, and SQLite
# hands back naive values however they were written (see the helper's docstring).
from inbetweenies.models.relationship import _as_aware
from inbetweenies.sync import (
    BlobChange,
    EntityChange, RelationshipChange, SyncChange,
    SyncRequest, ConflictInfo, SyncStats, SyncResponse,
    ConflictResolver,
)
from inbetweenies.sync.conflict import three_way_merge
from funkygibbon.config import settings


@lru_cache(maxsize=1)
def _manifest():
    """The domain manifest this server enforces (settings.domain_manifest).

    Loaded once: it is the source of the per-type merge rules (ADR-005 §2
    rung 2). Same `package.module:ATTRIBUTE` form `migrate --verify` takes.
    """
    module_name, _, attr = settings.domain_manifest.partition(":")
    return getattr(importlib.import_module(module_name), attr or "MANIFEST")


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
    """Handle sync protocol requests (inbetweenies-v3, see PROTOCOL.md).

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

        if request.protocol_version != "inbetweenies-v3":
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

        # Blobs before relationships and independent of entity ordering: the
        # table has no foreign key to entities, and an attachment entity's
        # content references a blob id that should already resolve by the time
        # anyone reads it. Storing bytes for an entity whose write later loses
        # conflict resolution is harmless -- an unreferenced blob is inert,
        # whereas an entity referencing bytes that never arrived is not.
        for change in request.changes:
            for blob in change.blobs:
                await self._persist_blob(blob)

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
                wanted = set(request.filters.entity_types)
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

        # ADR-005 §3: the delta stream carries edge interval rows, not only
        # entity versions. Without this the pull direction never mentioned a
        # relationship at all -- `SyncChange.relationships` was populated on the
        # way in and left empty on the way out -- so a client could push
        # topology but never learn any, and a fresh replica synced every entity
        # in the house and no edges between them. "Clients hold the whole graph"
        # (README) was true of the nodes only.
        #
        # The page is defined over the union of both tables in server_seq
        # order: a full entity page ends at `page_max`, and this page carries
        # the edges up to that same position, so nothing is skipped or
        # repeated across pages.
        edges_by_source = await self._outgoing_relationships(
            request, page_max=(int(cursor) if cursor else None)
        )

        response_changes = []
        for entity in entities:
            deleted = bool((entity.content or {}).get("deleted"))
            response_changes.append(SyncChange(
                change_type="delete" if deleted else "update",
                entity=self._entity_to_change(entity),
                # Bytes travel with the entity that references them. Without
                # this a client pulls an attachment whose blob_id resolves to
                # nothing locally, and the only way to see the image is to call
                # the server directly -- which is the direct access this exists
                # to remove.
                blobs=await self._blobs_for(entity),
                # §3.1: edges ride the change for their SOURCE entity, which is
                # also what makes §5's apply ordering satisfiable -- the
                # endpoint is in the same batch, ahead of the edge.
                relationships=edges_by_source.pop(entity.id, []),
            ))

        # Edges whose source entity is not in this page still have to travel:
        # the entity may have been synced long ago and only the edge changed.
        # They ride an entity-less change, the same shape a client uses to push
        # an orphan edge (§3.1).
        for orphans in edges_by_source.values():
            response_changes.append(SyncChange(
                change_type="update", entity=None, relationships=orphans,
            ))

        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        return SyncResponse(
            sync_type=request.sync_type,
            changes=response_changes,
            conflicts=conflicts,
            applied=applied,
            applied_relationships=applied_relationships,
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

    async def _outgoing_relationships(
        self, request: SyncRequest, *, page_max: Optional[int] = None
    ) -> Dict[str, List[RelationshipChange]]:
        """Edge intervals this request should receive, grouped by source id.

        ADR-004 §6 / ADR-005 §3: **every immutable row**, not a latest-per-id
        projection -- retired intervals included. A replica that only ever
        received open intervals could answer "where is it now?" and nothing
        else, which is the entire capability the temporal model exists to
        provide. The rows are immutable, so shipping history is idempotent.

        Bounds, in priority order, matching `_outgoing_entities`:

        * ``cursor`` — `server_seq > cursor`, and `<= page_max` when the entity
          page was capped, so the page is one contiguous slice of the shared
          sequence. Exact and clock-independent. Edges used to lack the stamp,
          which forced a translation of the entity cursor into a wall-clock
          instant — and edges are written after entities in the same
          transaction, so every edge was always "newer" and a caught-up client
          re-received the entire edge table on every poll.
        * ``filters.since`` — the wall-clock bound v2 clients persist.
        * neither (a full sync) — everything.
        """
        stmt = select(EntityRelationship)

        if request.sync_type == "delta":
            if request.cursor:
                try:
                    position = int(request.cursor)
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"cursor must be a server_seq integer, got {request.cursor!r}",
                    )
                stmt = stmt.where(EntityRelationship.server_seq > position)
                if page_max is not None:
                    stmt = stmt.where(EntityRelationship.server_seq <= page_max)
            elif request.filters and request.filters.since:
                stmt = stmt.where(
                    EntityRelationship.updated_at > _to_utc(request.filters.since)
                )

        # Replication order, so a client applying in sequence sees each edge's
        # history the way it happened; ties (none, the stamp is unique) fall
        # back to the valid-time axis.
        stmt = stmt.order_by(EntityRelationship.server_seq, EntityRelationship.valid_from)

        grouped: Dict[str, List[RelationshipChange]] = {}
        result = await self.db_session.execute(stmt)
        for row in result.scalars().all():
            grouped.setdefault(row.from_entity_id, []).append(
                self._relationship_to_change(row)
            )
        return grouped

    @staticmethod
    def _relationship_to_change(row: EntityRelationship) -> RelationshipChange:
        """Convert a stored edge interval to its wire RelationshipChange."""
        return RelationshipChange(
            id=row.id,
            from_entity_id=row.from_entity_id,
            to_entity_id=row.to_entity_id,
            relationship_type=getattr(
                row.relationship_type, "value", row.relationship_type
            ),
            properties=row.properties or {},
            # Sent verbatim: these are the client's own edit times on the
            # valid-time axis (ADR-004 §2), and a replica that recomputed them
            # locally would disagree with every other replica about the past.
            valid_from=_to_utc(row.valid_from),
            valid_to=_to_utc(row.valid_to),
        )

    async def _state_digest(self) -> str:
        """sha256 over the current entity versions AND the current edges.

        ADR-011 §4. Divergence between a server and a replica is otherwise
        undetectable: both sides believe they are in sync, because both applied
        every change they were told about. A client compares this against the
        same computation over its own cache and resyncs on mismatch.

        Deliberately the degenerate form of the Merkle tree in the deleted sync
        stack: at this scale one hash over the identifying tuples delivers the
        verification value, and a tree would be machinery without a payload.

        **Edges are in the digest, and that is not incidental.** Hashing only
        entity ids and versions left the graph's entire topology outside the
        convergence check — which mattered little while an edge was a mutable
        row that followed its endpoints, and matters a great deal now that edges
        carry independent history (ADR-004 §1). Two replicas could disagree
        about which room every device is in and still produce identical
        digests, so the one mechanism meant to catch silent divergence was blind
        to exactly the half this protocol version changed.

        Edges contribute `(id, valid_from)` — their primary key, and the pair
        that distinguishes one interval of an edge from the next. Only open
        intervals are hashed: the digest verifies agreement about *state*, and
        replicas legitimately hold different depths of history depending on when
        they first synced.
        """
        digest = hashlib.sha256()

        entities = await self.db_session.execute(
            select(Entity.id, Entity.version)
            .where(Entity.is_latest.is_(True))
            .order_by(Entity.id)
        )
        for entity_id, version in entities.all():
            digest.update(f"{entity_id}\x1f{version}\x1e".encode())

        # The separator keeps the two sections from aliasing: without it an
        # entity id could, in principle, be split so that the byte stream
        # matched a different entity/edge division.
        digest.update(b"\x1d")

        edges = await self.db_session.execute(
            select(EntityRelationship.id, EntityRelationship.valid_from)
            .where(EntityRelationship.valid_to.is_(None))
            .order_by(EntityRelationship.id, EntityRelationship.valid_from)
        )
        for edge_id, valid_from in edges.all():
            stamp = _to_utc(valid_from)
            digest.update(
                f"{edge_id}\x1f{stamp.isoformat() if stamp else ''}\x1e".encode()
            )

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
        """Allocate the next replication stamp — from the ONE shared sequence.

        Gap-free and assigned in apply order, so a delta cursor is exact.
        Wall-clock cannot do this: two rows written in the same microsecond are
        indistinguishable to `updated_at > since`, and a clock adjustment can
        move rows across a cursor a client has already passed. Edge intervals
        draw from the same counter (ADR-005 §3), so the cursor is a position
        in one order over the whole stream.
        """
        return await next_server_seq(self.db_session)

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
            entity_type=change.entity.entity_type,
            name=change.entity.name,
            content=content,
            source_type=change.entity.source_type,
            user_id=change.entity.user_id,
            parent_versions=change.entity.parent_versions or [],
            created_at=now,
            updated_at=now,
            is_latest=becomes_latest,
            server_seq=await self._next_server_seq(),
        )
        self.db_session.add(entity)
        await self.db_session.flush()

    async def _blobs_for(self, entity) -> List[BlobChange]:
        """Blobs referenced by this entity's content, ready to send.

        Reads both shapes ADR-013 §3 leaves live: the top-level ``blob_id`` on
        an attachment entity, and the ordered ``images[]`` list an entity owns
        when the sequence matters. Anything else referencing a blob would be a
        seventh convention, and there is not one.

        A reference that resolves to no row is skipped rather than raised on:
        one missing blob must not make an entity unsyncable, and the verify
        command reports dangling references properly.
        """
        import base64

        from inbetweenies.models.blob import Blob

        content = entity.content or {}
        if not isinstance(content, dict):
            return []

        wanted = [content.get("blob_id")]
        wanted += [img.get("blob_id") for img in (content.get("images") or [])
                   if isinstance(img, dict)]

        out: List[BlobChange] = []
        seen = set()
        for blob_id in filter(None, wanted):
            if blob_id in seen:
                continue
            seen.add(blob_id)
            row = await self.db_session.get(Blob, blob_id)
            if row is None or row.data is None:
                continue
            out.append(BlobChange(
                id=row.id,
                name=row.name,
                blob_type=getattr(row.blob_type, "value", row.blob_type),
                mime_type=row.mime_type,
                size=row.size,
                data=base64.b64encode(row.data).decode("ascii"),
                checksum=row.checksum,
                user_id=row.user_id,
                summary=row.summary,
            ))
        return out

    async def _persist_blob(self, blob) -> bool:
        """Store blob bytes pushed by a client. Idempotent on blob id.

        Blob ids are content-addressed (the SHA-256 of the bytes), so the same
        file pushed by two clients, or re-pushed after a failed ack, resolves to
        one row. Returning early on a hit also keeps a retry cheap: one SELECT
        instead of rewriting megabytes.

        Bytes are trusted no further than the checksum: if the sender supplied
        one and it does not match what arrived, the blob is rejected rather than
        stored corrupt. A silently corrupt blob is worse than a missing one --
        the reference resolves and the image is garbage.
        """
        import base64
        import hashlib

        from inbetweenies.models.blob import Blob, BlobStatus

        existing = await self.db_session.get(Blob, blob.id)
        if existing is not None:
            return False

        try:
            data = base64.b64decode(blob.data, validate=True)
        except Exception:
            return False

        digest = hashlib.sha256(data).hexdigest()
        if blob.checksum and blob.checksum != digest:
            return False

        now = datetime.now(timezone.utc)
        self.db_session.add(Blob(
            id=blob.id,
            name=(blob.name or "blob")[:255],
            blob_type=blob.blob_type,
            mime_type=blob.mime_type,
            size=len(data),
            data=data,
            blob_metadata={},
            checksum=digest,
            sync_status=BlobStatus.UPLOADED,
            user_id=blob.user_id,
            summary=blob.summary[:2000] if blob.summary else None,
            created_at=now,
            updated_at=now,
        ))
        await self.db_session.flush()
        return True

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

        # ADR-012 §1: the sync boundary enforces the domain's vocabulary, as
        # the tool boundary does. A house entity pushed at a vehicles server
        # is a client pointed at the wrong endpoint, and a 400 says so; storing
        # it would fragment the graph silently.
        try:
            _manifest().check_entity_type(change.entity.entity_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # ADR-002 §3: resolve THIS id, not the whole table. Scanning every
        # version of every entity once per pushed change is what made a
        # 50-change push cost O(history x changes).
        existing = await self._current_row(change.entity.id)

        if existing is None:
            await self._insert_version(change)
            return True

        if existing.version == change.entity.version:
            return True  # idempotent re-send: already in the desired state

        parents = list(change.entity.parent_versions or [])

        if not parents:
            # An update that names no parent_versions for an id we already hold is
            # a blind overwrite: the client cannot have seen our version, so this
            # is by definition not a fast-forward. Decide it through the §7 rule
            # like any other concurrent edit instead of letting it through
            # unchallenged. Record the version it supersedes if it wins, so the
            # version DAG stays connected (same repair as the tombstone path).
            #
            # The synthesized parent is for the DAG only. It is NOT history the
            # client had, so it must not make the edit look mergeable: passing
            # the client's real (empty) parents keeps a blind overwrite on the
            # ordering rule, decided whole, as §7.2 says.
            change.entity.parent_versions = [existing.version]
            return await self._resolve_conflict(change, existing, conflicts, claimed_parents=[])

        if existing.version in parents:
            await self._insert_version(change)  # fast-forward
            return True

        # Client edited from a version we have since superseded.
        return await self._resolve_conflict(change, existing, conflicts, claimed_parents=parents)

    async def _resolve_conflict(self, change: SyncChange, existing: Entity,
                                conflicts: List[ConflictInfo],
                                claimed_parents: Optional[List[str]] = None) -> bool:
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

        # ADR-005 §2 rungs 2-3: if the two edits share an ancestor, MERGE them
        # rather than pick one. Rung 4 (clamped LWW) then settles only the keys
        # both sides changed differently. Without an ancestor -- a parentless
        # overwrite -- there is nothing to merge against, and LWW decides whole.
        base = await self._common_ancestor(existing, claimed_parents or [])
        if base is not None and base.version != existing.version:
            merged_version, strategy = await self._merge_versions(
                change, existing, base, remote_wins=remote_wins, resolution=resolution,
            )
            conflicts.append(ConflictInfo(
                entity_id=change.entity.id,
                local_version=existing.version,
                remote_version=change.entity.version,
                resolution_strategy=strategy,
                resolved_version=merged_version,
            ))
            return True

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

    async def _common_ancestor(self, existing: Entity, remote_parents: List[str]) -> Optional[Entity]:
        """The nearest version both edits descend from (ADR-005 §2 rung 3).

        Walks `parent_versions` -- the DAG is already stored, and the deleted
        VersionTree.find_common_ancestor (ADR-008) proved this is cheap at
        this scale. "Nearest" is the greatest version string among the common
        ancestors, which is the newest because versions sort chronologically.
        """
        if not remote_parents:
            return None
        rows = (await self.db_session.execute(
            select(Entity).where(Entity.id == existing.id)
        )).scalars().all()
        by_version = {row.version: row for row in rows}

        def ancestors(start: List[str]) -> set:
            seen, frontier = set(), list(start)
            while frontier:
                v = frontier.pop()
                if v in seen or v not in by_version:
                    continue
                seen.add(v)
                frontier.extend(by_version[v].parent_versions or [])
            return seen

        common = ancestors([existing.version]) & ancestors(list(remote_parents))
        if not common:
            return None
        return by_version[max(common)]

    async def _merge_versions(self, change: SyncChange, existing: Entity, base: Entity, *,
                              remote_wins: bool, resolution) -> tuple:
        """Rungs 2-4: produce a server-authored merge version with both parents.

        The incoming version is stored too, as a non-latest row -- it is a real
        edit in the DAG and a parent of the merge (ADR-011 §2: nothing loses
        existence). Returns (merge version, strategy string).
        """
        base_c = dict(base.content or {})
        local_c = dict(existing.content or {})
        remote_c = dict(change.entity.content or {})
        generic = three_way_merge(base_c, local_c, remote_c)
        content = dict(generic.merged)

        # Rung 4, scoped: only the keys both sides changed differently.
        winner_c = remote_c if remote_wins else local_c
        for key in generic.conflicted:
            if key in winner_c:
                content[key] = winner_c[key]
            else:
                content.pop(key, None)

        # Rung 2: the domain's rule overlays the keys it owns.
        strategy = "three_way_merge"
        entity_type = getattr(existing.entity_type, "value", existing.entity_type)
        rule = _manifest().merge_rules.get(entity_type)
        if rule is not None:
            owned = rule(base_c, local_c, remote_c) or {}
            if owned:
                content.update(owned)
                strategy = f"manifest_rule:{entity_type}+three_way_merge"

        # The name is one more field under the same rule.
        conflicted = set(generic.conflicted)
        if existing.name == base.name:
            name = change.entity.name
        elif change.entity.name == base.name or change.entity.name == existing.name:
            name = existing.name
        else:
            name = change.entity.name if remote_wins else existing.name
            conflicted.add("name")
        if conflicted:
            strategy += "+lww:" + ",".join(sorted(conflicted))

        # Store the incoming edit as history first, then the merge on top.
        # ADR-011's anti-decision: no synthetic "sync-merge" author. The merge
        # version carries the WINNING writer's user id and a `merged: true`
        # marker so history shows who prevailed and that the server merged.
        winner = change.entity.user_id if remote_wins else existing.user_id
        content["merged"] = True
        await self._insert_version(change, becomes_latest=False)
        merge = SyncChange(
            change_type="update",
            entity=EntityChange(
                id=change.entity.id,
                version=Entity.create_version(winner or change.entity.user_id or "sync"),
                entity_type=entity_type,
                name=name,
                content=content,
                source_type=getattr(existing.source_type, "value", existing.source_type),
                user_id=winner or change.entity.user_id,
                parent_versions=[existing.version, change.entity.version],
            ),
        )
        await self._insert_version(merge)
        return merge.entity.version, strategy

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

    @staticmethod
    def _edge_content_differs_impl(current, incoming, rel_type, properties,
                                   user_id=None) -> bool:
        """Would storing `incoming` change what the edge says? (ADR-004 §1)

        Only a real change opens a new interval. Without this, a client that
        re-pushes an unchanged edge on every sync would end and reopen the row
        each time, turning one continuous fact into a chain of slivers and
        making `snapshot(T)` answer correctly but read as churn.

        ``user_id`` is part of what the edge says — it is the attribution the
        audit log and the review queue read back. Leaving it out meant a
        re-attribution (the same edge, now claimed by another user) compared
        equal and was silently dropped.
        """
        return (
            current.from_entity_id != incoming.from_entity_id
            or current.to_entity_id != incoming.to_entity_id
            or getattr(current.relationship_type, "value", current.relationship_type)
            != getattr(rel_type, "value", rel_type)
            or (current.properties or {}) != properties
            or current.user_id != user_id
        )

    async def _persist_relationship(self, relationship: RelationshipChange,
                                    user_id: Optional[str] = None) -> bool:
        """Persist one inbound edge interval; True once it is stored (§3.1).

        ADR-004 §1/§6: an edge is an immutable interval row keyed on
        ``(id, valid_from)``. ``id`` is the logical edge; ``valid_from`` picks
        the interval. Three inbound shapes, all idempotent:

        * **assert** (``valid_to`` null) — the edge is true from ``valid_from``
          onward. Opens a new interval, ending the predecessor at the same
          instant if the content actually changed.
        * **end-event** (``valid_to`` set) — the edge stopped being true. Closes
          the matching row. This is how a client deletes or moves an edge, and
          it is an ordinary change, not a special message type.
        * **backfill** — a closed interval for a row we have never seen. Stored
          as-is, so a replica that missed the live window still converges on the
          same history.

        ADR-004 §2: ``valid_from``/``valid_to`` are **client edit time**, stored
        verbatim. Server time is only the fallback for a peer that sends
        neither, and ``server_seq`` (the replication axis) is never consulted
        here.
        """
        # ADR-012 §1: the domain manifest, not the legacy enum, says what an
        # edge may be called.
        try:
            _manifest().check_relationship_type(relationship.relationship_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown relationship_type: {relationship.relationship_type}",
            )
        rel_type = relationship.relationship_type

        # ADR-004 §1: endpoints are checked by id, not by (id, version).
        #
        # The old check required each endpoint to exist at exactly the pinned
        # version, because the table carried a composite FK. With the pin gone,
        # the question is simply whether the entity is known at all — the
        # version an edge "points at" is now whatever snapshot(T) resolves
        # (§3.4). A dangling endpoint stays skipped rather than fatal: the
        # entity may not have reached us yet, and the caller reports the
        # shortfall via sync_stats.
        for entity_id in (relationship.from_entity_id, relationship.to_entity_id):
            exists = await self.db_session.scalar(
                select(Entity.id).where(Entity.id == entity_id).limit(1)
            )
            if exists is None:
                return False

        now = datetime.now(timezone.utc)
        properties = dict(relationship.properties or {})
        # The client's own interval is the truth about when the edit happened
        # (ADR-004 §2). Only a peer that sends nothing falls back to server time.
        incoming_from = _to_utc(relationship.valid_from) or now
        incoming_to = _to_utc(relationship.valid_to)

        # The open interval for this logical edge, if any: the row that is
        # currently true. Ended rows are history and are never touched again,
        # with the single exception below of closing the row this change ends.
        current = await self.db_session.scalar(
            select(EntityRelationship).where(
                EntityRelationship.id == relationship.id,
                EntityRelationship.valid_to.is_(None),
            )
        )

        if incoming_to is not None:
            return await self._end_edge_interval(
                relationship, rel_type, properties, user_id,
                current=current, incoming_from=incoming_from,
                incoming_to=incoming_to, now=now,
            )

        if current is not None:
            if not self._edge_content_differs_impl(
                current, relationship, rel_type, properties, user_id
            ):
                # Idempotent re-push of an unchanged edge. Returning True without
                # writing keeps the ack contract (the change was processed) while
                # avoiding a spurious interval boundary — otherwise every retried
                # sync would shred the edge's history into adjacent slivers.
                return True

            # ADR-004 §1: end the old row, never mutate it. This is the line that
            # makes prior topology recoverable — the previous implementation
            # assigned over these same fields and the old placement was gone.
            #
            # The boundary is one instant shared by both rows: the predecessor's
            # `valid_to` and the successor's `valid_from`. Because the interval
            # is half-open (§1), that yields exactly one edge current at the
            # handover. Clamped forward past the predecessor's own start so a
            # client with a lagging clock cannot mint a negative-length row.
            incoming_from = max(incoming_from, _as_aware(current.valid_from))
            current.valid_to = incoming_from
            await stamp_relationship(self.db_session, current)

        return await self._insert_edge_interval(
            relationship, rel_type, properties, user_id,
            valid_from=incoming_from, valid_to=None, now=now,
        )

    async def _end_edge_interval(self, relationship, rel_type, properties, user_id,
                                 *, current, incoming_from, incoming_to, now) -> bool:
        """Apply an inbound change whose ``valid_to`` is set (ADR-004 §6).

        "This edge stopped being true at T" travels as an ordinary change. It
        closes a row; it never opens one, which is what distinguishes it from
        the assert path and what makes an edge delete expressible on the wire
        at all.
        """
        if current is not None:
            # Clamp forward: an end can never precede its own start.
            current.valid_to = max(incoming_to, _as_aware(current.valid_from))
            # Re-stamp: ending is the change a replica has to learn about, and
            # it only will if the row moves past the replica's cursor.
            await stamp_relationship(self.db_session, current)
            await self.db_session.flush()
            return True

        # No open row. Either this end-event already landed (a retry), or we
        # never saw the interval it closes.
        existing = await self.db_session.get(
            EntityRelationship, (relationship.id, incoming_from)
        )
        if existing is not None:
            # Retry of an end we already applied. Idempotent: the row is
            # immutable once closed, so nothing is rewritten.
            return True

        # Backfill: store the closed interval verbatim so a replica that missed
        # the live window still converges on the same history.
        return await self._insert_edge_interval(
            relationship, rel_type, properties, user_id,
            valid_from=incoming_from,
            valid_to=max(incoming_to, incoming_from),
            now=now,
        )

    async def _insert_edge_interval(self, relationship, rel_type, properties, user_id,
                                    *, valid_from, valid_to, now) -> bool:
        """Insert one interval row, tolerating a re-pushed identical key.

        ``(id, valid_from)`` is the primary key, so a client replaying a change
        it already sent would otherwise raise IntegrityError and fail the whole
        batch transaction (ADR-011 §3). Rows are immutable, so an existing row
        at that key already *is* the change: acknowledge and move on.
        """
        existing = await self.db_session.get(
            EntityRelationship, (relationship.id, valid_from)
        )
        if existing is not None:
            return True

        self.db_session.add(EntityRelationship(
            id=relationship.id,
            valid_from=valid_from,
            valid_to=valid_to,
            from_entity_id=relationship.from_entity_id,
            to_entity_id=relationship.to_entity_id,
            relationship_type=rel_type,
            properties=properties,
            user_id=user_id,
            created_at=now,
            updated_at=now,
            server_seq=await self._next_server_seq(),
        ))

        # Flush, not commit: this row belongs to the batch transaction opened
        # by handle_sync_request (ADR-011 §3).
        await self.db_session.flush()
        return True

    def _entity_to_change(self, entity: Entity) -> EntityChange:
        """Convert a stored entity to its wire EntityChange."""
        return EntityChange(
            id=entity.id,
            version=entity.version,
            entity_type=getattr(entity.entity_type, "value", entity.entity_type),
            name=entity.name,
            content=entity.content or {},
            source_type=getattr(entity.source_type, "value", entity.source_type),
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
    try:
        return await handler.handle_sync_request(request)
    except LookupError as exc:
        # A stored enum spelling the ORM cannot read (#100: blobs.sync_status
        # holding 'uploaded'). Without this the client saw a bare 500 and the
        # cause was only in the server log; now the response names it and the
        # command that fixes it.
        raise HTTPException(
            status_code=500,
            detail=(f"stored value the server cannot read: {exc}. This is a data "
                    "inconsistency, not a client error -- run `python -m funkygibbon.migrate "
                    "--apply` on the server, then `--verify`."),
        )


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
        "protocol_version": "inbetweenies-v3",
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
