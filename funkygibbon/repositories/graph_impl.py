"""
SQLAlchemy implementation of graph operations for FunkyGibbon.

This module provides the concrete implementation of the abstract
graph operations using SQLAlchemy for database access.
"""

from datetime import datetime, timezone
from typing import List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from inbetweenies.graph import GraphOperations, GraphSearch
from inbetweenies.mcp import MCPTools
from inbetweenies.models import Entity, EntityType, EntityRelationship, RelationshipType, SourceType
from inbetweenies.models.blob import Blob, BlobStatus
from .graph import apply_write_invariants, stamp_relationship


def _current_at_clauses(at: Optional[datetime]):
    """SQL for "this interval is true at `at`" (ADR-004 §1/§3.3).

    Half-open: ``valid_from <= at < coalesce(valid_to, ∞)``. With ``at`` None
    it is the current graph, ``valid_to IS NULL``, which `ix_rel_current`
    serves directly.
    """
    if at is None:
        return (EntityRelationship.valid_to.is_(None),)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return (
        EntityRelationship.valid_from <= at,
        or_(EntityRelationship.valid_to.is_(None), EntityRelationship.valid_to > at),
    )


class SQLGraphOperations(MCPTools):
    """
    SQLAlchemy implementation of graph operations.

    This class provides the concrete implementation of all abstract methods
    from GraphOperations, GraphSearch, and MCPTools using SQLAlchemy.
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session"""
        self.db = db

    async def store_blob(
        self,
        *,
        blob_id: str,
        name: str,
        blob_type: str,
        mime_type: str,
        data: bytes,
        user_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> str:
        """Persist blob bytes, idempotently on blob_id.

        The caller derives blob_id from a SHA-256 of the bytes, so a retried
        upload resolves to the same row rather than a duplicate. Returning
        early on a hit also means re-attaching a file that is already stored
        costs one SELECT instead of rewriting megabytes.
        """
        import hashlib

        existing = await self.db.get(Blob, blob_id)
        if existing is not None:
            return blob_id

        self.db.add(Blob(
            id=blob_id,
            name=name[:255],
            blob_type=blob_type,
            mime_type=mime_type,
            size=len(data),
            data=data,
            blob_metadata={},
            checksum=hashlib.sha256(data).hexdigest(),
            # Server-side storage IS the upload; there is nothing pending.
            sync_status=BlobStatus.UPLOADED,
            user_id=user_id,
            summary=summary[:2000] if summary else None,
        ))
        await self.db.flush()
        return blob_id

    async def get_blob(self, blob_id: str, include_data: bool = False) -> Optional[dict]:
        """Blob metadata, with bytes only when asked."""
        blob = await self.db.get(Blob, blob_id)
        return blob.to_dict(include_data=include_data) if blob else None

    async def store_entity(self, entity: Entity) -> Entity:
        """Store an entity, maintaining is_latest and server_seq (ADR-002 §1-2).

        This is the MCP tools' write path — `create_entity`, `update_entity`
        and attachment creation all land here — and it used to be a bare
        `add()`. Two consequences, both live:

        * `update_entity` left the superseded version marked `is_latest`
          alongside its successor, so two rows claimed to be current.
          `GraphRepository.get_entity` resolves with `where is_latest limit 1`,
          which then returned whichever row the database happened to yield —
          meaning REST and MCP could report different current versions of the
          same entity.
        * No `server_seq`, so the row was invisible to every cursor-based delta
          (`NULL > n` is NULL) and could never replicate to a client.

        Shared with GraphRepository rather than reimplemented, because two
        implementations of an invariant is how they drifted apart the first
        time.
        """
        await apply_write_invariants(self.db, entity)
        self.db.add(entity)
        await self.db.flush()
        return entity

    async def get_entity(self, entity_id: str, version: Optional[str] = None,
                         at: Optional[datetime] = None) -> Optional[Entity]:
        """Get an entity: a specific version, the state as of ``at``, or current."""
        if version:
            stmt = select(Entity).where(
                and_(Entity.id == entity_id, Entity.version == version)
            )
        elif at is not None:
            # ADR-004 §3.2: the greatest version stamped at or before `at`.
            # A tombstone current at `at` means the entity did not exist then.
            stmt = (
                select(Entity)
                .where(Entity.id == entity_id, Entity.version <= Entity.version_key_at(at))
                .order_by(Entity.version.desc())
                .limit(1)
            )
            found = (await self.db.execute(stmt)).scalar_one_or_none()
            return None if found is None or found.is_tombstone else found
        else:
            # ADR-002 §1: the recorded answer, same rule as GraphRepository.
            # This was the last reader still ranking by created_at, which
            # serves a preserved LOSING version (later insert) as current.
            stmt = select(Entity).where(
                Entity.id == entity_id, Entity.is_latest.is_(True)
            ).limit(1)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_entities_by_type(self, entity_type: EntityType,
                                   include_deleted: bool = False) -> List[Entity]:
        """Get all entities of a specific type (latest versions only).

        ``include_deleted`` admits tombstones (PROTOCOL.md §8); the default
        excludes them, matching GraphRepository so the two backends cannot
        answer "what is in this house?" differently.
        """
        # Subquery to get latest version for each entity ID
        subquery = (
            select(Entity.id, Entity.version, Entity.created_at)
            .where(Entity.entity_type == entity_type)
            .subquery()
        )

        # Window function to rank versions by created_at
        from sqlalchemy import func
        ranked = (
            select(
                subquery.c.id,
                subquery.c.version,
                func.row_number().over(
                    partition_by=subquery.c.id,
                    order_by=subquery.c.created_at.desc()
                ).label("rn")
            ).subquery()
        )

        # Get only the latest version (rn=1) for each entity
        latest_versions = (
            select(ranked.c.id, ranked.c.version)
            .where(ranked.c.rn == 1)
            .subquery()
        )

        # Join with Entity table to get full entity data
        stmt = (
            select(Entity)
            .join(
                latest_versions,
                and_(
                    Entity.id == latest_versions.c.id,
                    Entity.version == latest_versions.c.version
                )
            )
            # ADR-004 §1: the entity-side edge collections were version-pinned
            # joins and are gone. Edges are fetched by id (+ T) where needed.
        )

        result = await self.db.execute(stmt)
        # PROTOCOL.md §8: a tombstone is `is_latest` for its id, so it arrives
        # here like any other current row and must not be served as live. See
        # the longer note in GraphRepository.get_entities_by_type.
        entities = list(result.scalars().all())
        if include_deleted:
            return entities
        return [entity for entity in entities if not entity.is_tombstone]

    async def end_relationship(
        self, relationship_id: str, at: Optional[datetime] = None
    ) -> Optional[EntityRelationship]:
        """End an edge's open interval (ADR-004 §1). The row stays; it is history now."""
        current = await self.db.scalar(
            select(EntityRelationship).where(
                EntityRelationship.id == relationship_id,
                EntityRelationship.valid_to.is_(None),
            )
        )
        if current is None:
            return None
        moment = at or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        start = current.valid_from
        if start is not None and start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        # Clamp forward: an end can never precede its own start.
        current.valid_to = max(moment, start) if start else moment
        # Ending is a replicated change (ADR-005 §3): re-stamp so a cursor
        # client learns the edge is gone.
        await stamp_relationship(self.db, current)
        await self.db.flush()
        return current

    async def store_relationship(self, relationship: EntityRelationship) -> EntityRelationship:
        """Store a relationship in the database"""
        from uuid import uuid4

        # Generate ID if not provided
        if not relationship.id:
            relationship.id = str(uuid4())

        # ADR-002 §2: same stamp as the sync path and GraphRepository, from the
        # one shared allocator. This is the MCP write path.
        if relationship.server_seq is None:
            await stamp_relationship(self.db, relationship)

        self.db.add(relationship)
        await self.db.flush()
        return relationship

    async def get_relationships(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        rel_type: Optional[RelationshipType] = None,
        include_all_versions: bool = False,
        at: Optional[datetime] = None
    ) -> List[EntityRelationship]:
        """Get relationships with optional filters.

        ``include_all_versions=True`` returns retired intervals as well as the
        current ones — history, not state. Default is the current graph.
        """
        conditions = []

        if from_id:
            conditions.append(EntityRelationship.from_entity_id == from_id)
        if to_id:
            conditions.append(EntityRelationship.to_entity_id == to_id)
        if rel_type:
            conditions.append(EntityRelationship.relationship_type == rel_type)

        stmt = select(EntityRelationship)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # ADR-004 §1: "current" is a property of the edge's own interval, not
        # of whether its pins happen to match the endpoints' latest versions.
        # The old test was a proxy that broke on every endpoint version bump —
        # an edge whose endpoint gained a version silently stopped being
        # "latest" even though nothing about the edge had changed.
        #
        # The filter is unconditional. It used to be gated on
        # `not hasattr(self, "_include_all_versions") and (from_id or to_id)`:
        # an attribute nothing ever set (so the first half was always true) and
        # an endpoint filter that has no bearing on currency (so the second half
        # let every unfiltered query return retired intervals as live edges).
        if not include_all_versions:
            stmt = stmt.where(*_current_at_clauses(at))

        # ADR-004 §1: endpoints are no longer joinable from the edge row — the
        # pin that made from_entity/to_entity possible is gone, and an as-of
        # graph has no single endpoint version to eager-load. Callers resolve
        # endpoints by id (+ T) instead.

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _fts_search(
        self,
        match_query: str,
        *,
        entity_types: Optional[List[EntityType]],
        limit: int,
        exclude_id: Optional[str] = None,
    ) -> List[Any]:  # Returns List[SearchResult]
        """Run one FTS5 MATCH and hydrate the hits into SearchResults.

        Shared by search_entities and find_similar_entities: the two differ only
        in how the MATCH expression is built (ADR-006 §1 vs §3).
        """
        from sqlalchemy import text as sql_text

        from ..search.fts import FTS_TABLE
        from inbetweenies.graph.search import SearchResult

        if not match_query:
            return []

        # bm25() returns a negative score where more negative is a better match,
        # so ascending order is best-first. snippet() gives a real excerpt from
        # the matched text rather than the old scorer's synthetic
        # "Content matches 2 word(s)" strings.
        rows = (await self.db.execute(
            sql_text(
                f"""
                SELECT entity_id,
                       bm25({FTS_TABLE}) AS rank,
                       snippet({FTS_TABLE}, 1, '', '', '…', 12) AS name_hit,
                       snippet({FTS_TABLE}, 2, '', '', '…', 24) AS content_hit
                FROM {FTS_TABLE}
                WHERE {FTS_TABLE} MATCH :q
                ORDER BY rank
                LIMIT :n
                """
            ),
            # Over-fetch: entity_type filtering and the self-exclusion happen
            # below, and a hit removed there must not cost us a result slot.
            {"q": match_query, "n": limit * 4 if (entity_types or exclude_id) else limit},
        )).all()

        if not rows:
            return []

        ranked = {r.entity_id: r for r in rows if r.entity_id != exclude_id}
        if not ranked:
            return []

        stmt = select(Entity).where(
            and_(Entity.id.in_(list(ranked)), Entity.is_latest.is_(True))
        )
        if entity_types:
            stmt = stmt.where(Entity.entity_type.in_(entity_types))
        entities = list((await self.db.execute(stmt)).scalars().all())

        # Restore BM25 order, which the IN-clause fetch does not preserve.
        entities.sort(key=lambda e: ranked[e.id].rank)

        results = []
        for entity in entities[:limit]:
            row = ranked[entity.id]
            highlights: dict = {}
            if row.name_hit:
                highlights["name"] = [row.name_hit]
            if row.content_hit:
                highlights["content"] = [row.content_hit]
            # Negate so callers keep "higher is better", matching the score
            # contract the hand-rolled scorer established.
            results.append(SearchResult(entity, -row.rank, highlights))
        return results

    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 10
    ) -> List[Any]:  # Returns List[SearchResult]
        """Search entities by name or content, ranked by BM25 (ADR-006 §1).

        Replaces the substring-on-name query plus Python scorer. The old path
        never searched content in SQL at all — it filtered on name, then scored
        content in memory, so an entity whose match lived only in content was
        unreachable unless its name happened to match too.
        """
        from ..search.fts import build_match_query

        return await self._fts_search(
            build_match_query(query),
            entity_types=entity_types,
            limit=limit,
        )

    async def get_entity_versions(self, entity_id: str) -> List[Entity]:
        """Get all versions of an entity"""
        stmt = (
            select(Entity)
            .where(Entity.id == entity_id)
            .order_by(Entity.created_at.asc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_similar_entities(self, entity_id: str, limit: int = 5) -> List[Any]:
        """Find entities similar to this one, via FTS5 more-like-this (ADR-006 §3).

        This is the standing implementation until ADR-006 §2's embeddings have
        an owner; the ADR records that sqlite-vec lands only then, and that this
        fallback is "a real quality improvement over word overlap with no ML
        dependency at all".

        The previous implementation ignored the entity's text entirely and
        returned other entities of the same type — every thermostat was equally
        "similar" to every other thermostat, in storage order.

        Similarity is deliberately not restricted to the source's entity_type:
        a manual is genuinely similar to the device it documents.
        """
        import json as _json

        from ..search.fts import build_more_like_this_query

        entity = await self.get_entity(entity_id)
        if not entity:
            return []

        document = entity.name or ""
        if entity.content:
            document = f"{document} {_json.dumps(entity.content)}"

        return await self._fts_search(
            build_more_like_this_query(document),
            entity_types=None,
            limit=limit,
            exclude_id=entity_id,
        )

    async def update_entity(self, entity_id: str, changes: dict, user_id: str) -> Entity:
        """Update entity by creating new version"""
        current = await self.get_entity(entity_id)
        if not current:
            raise ValueError(f"Entity {entity_id} not found")

        # Create new version
        new_entity = current.create_new_version(user_id, changes)

        # Store new version
        stored = await self.store_entity(new_entity)
        await self.db.commit()

        return stored
