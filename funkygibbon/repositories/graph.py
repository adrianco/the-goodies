"""
Graph Repository for Entity and Relationship Operations

This module provides the repository pattern implementation for graph operations,
handling storage and retrieval of entities and relationships.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity, EntityType, EntityRelationship, RelationshipType
from .base import BaseRepository


async def next_server_seq(db: AsyncSession) -> int:
    """Allocate the next replication stamp (ADR-002 §2).

    ONE sequence over entities AND edge intervals. The delta cursor is a
    position in this order, so both tables must draw from the same counter —
    two allocators would collide, and a client would skip whichever row lost
    the tie. Gap-free and in apply order; wall-clock cannot do this.
    """
    entity_max = (await db.execute(select(func.max(Entity.server_seq)))).scalar() or 0
    edge_max = (await db.execute(select(func.max(EntityRelationship.server_seq)))).scalar() or 0
    return max(entity_max, edge_max) + 1


async def stamp_relationship(db: AsyncSession, rel: EntityRelationship) -> EntityRelationship:
    """Give an edge interval its replication stamp, or a NEW one if re-stamping.

    Called on insert and again when an interval is ended: ending is the
    change a replica must learn about, and it only will if the row moves
    past the replica's cursor.
    """
    rel.server_seq = await next_server_seq(db)
    return rel


async def apply_write_invariants(db: AsyncSession, entity: Entity) -> Entity:
    """Maintain `is_latest` and `server_seq` for one entity row (ADR-002 §1-2).

    Extracted so that EVERY write path shares one implementation. It previously
    lived only inside ``GraphRepository.store_entity``, whose own docstring
    warned that "a column that only one writer maintains is worse than no
    column: readers trust it, and the paths that skip it leave two rows claiming
    to be current with nothing to say which is right." That is precisely what
    ``SQLGraphOperations.store_entity`` — the MCP tools' write path — did: an
    entity updated through `update_entity` left the old and the new version both
    marked `is_latest`, both unstamped. `GraphRepository.get_entity` resolves
    the current row with `where is_latest limit 1`, so REST and MCP could
    disagree about which version of an entity is current, and a delta cursor
    skipped the row entirely because `NULL > n` is NULL.

    Idempotent, and safe to call on a row that already carries a stamp.
    """
    # `is not False`, not a truth test: a freshly constructed Entity has
    # is_latest=None until flush, because the column default is applied by
    # the INSERT rather than by __init__. A plain `if entity.is_latest:`
    # therefore skips the demotion for exactly the common case — a new
    # version — and leaves two rows marked current.
    if entity.is_latest is not False:
        entity.is_latest = True
        # Demote the incumbent in the same transaction as the insert.
        await db.execute(
            update(Entity)
            .where(Entity.id == entity.id,
                   Entity.version != entity.version,
                   Entity.is_latest.is_(True))
            .values(is_latest=False)
        )

    if entity.server_seq is None:
        entity.server_seq = await next_server_seq(db)

    return entity


class GraphRepository(BaseRepository[Entity]):
    """Repository for graph operations on entities and relationships"""

    model = Entity

    def __init__(self, db: AsyncSession):
        """Initialize with database session"""
        super().__init__(Entity)
        self.db = db

    async def store_entity(self, entity: Entity) -> Entity:
        """
        Store entity with version tracking.

        Maintains is_latest and server_seq (ADR-002 §1-2), so every write path
        keeps the invariant "exactly one current row per id" — not just the sync
        apply path. A column that only one writer maintains is worse than no
        column: readers trust it, and the paths that skip it leave two rows
        claiming to be current with nothing to say which is right.

        Args:
            entity: Entity to store

        Returns:
            Stored entity
        """
        await apply_write_invariants(self.db, entity)
        self.db.add(entity)
        await self.db.flush()
        return entity

    async def get_entity(self, entity_id: str, version: Optional[str] = None,
                         at: Optional[datetime] = None) -> Optional[Entity]:
        """
        Get specific version, the state as of ``at``, or the latest entity.

        Args:
            entity_id: Entity ID
            version: Specific version to retrieve (optional)
            at: ADR-004 §3.2 -- the greatest version stamped at or before this
                instant; None if it did not exist, or was tombstoned, then.

        Returns:
            Entity if found, None otherwise
        """
        if at is not None and not version:
            stmt = (
                select(Entity)
                .where(Entity.id == entity_id, Entity.version <= Entity.version_key_at(at))
                .order_by(Entity.version.desc())
                .limit(1)
            )
            found = (await self.db.execute(stmt)).scalar_one_or_none()
            return None if found is None or found.is_tombstone else found
        if version:
            # Get specific version
            stmt = select(Entity).where(
                and_(Entity.id == entity_id, Entity.version == version)
            )
        else:
            # ADR-002 §1: read the recorded answer.
            #
            # This has now been three rules in three commits — created_at, then
            # the version string, now is_latest — which is the argument for the
            # column. The first two INFERRED which version won; only conflict
            # resolution knows, and it now writes it down.
            stmt = select(Entity).where(
                Entity.id == entity_id, Entity.is_latest.is_(True)
            ).limit(1)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_entities_by_ids(self, entity_ids) -> Dict[str, Entity]:
        """Current row for each of ``entity_ids``, keyed by id.

        The batched form of :meth:`get_entity`, and it reads the same recorded
        answer (``is_latest``, ADR-002 §1) so the two can never disagree. Ids
        with no current row are simply absent from the result — the caller
        decides whether that is a dangling edge or a not-yet-synced entity.
        """
        ids = list(entity_ids)
        if not ids:
            return {}

        result = await self.db.execute(
            select(Entity).where(Entity.id.in_(ids), Entity.is_latest.is_(True))
        )
        return {entity.id: entity for entity in result.scalars().all()}

    async def get_entities_by_type(self, entity_type: EntityType,
                                   include_deleted: bool = False) -> List[Entity]:
        """
        Get all entities of a specific type (latest versions only).

        Args:
            entity_type: Type of entities to retrieve
            include_deleted: include tombstone versions (PROTOCOL.md §8).
                Default False -- a deleted entity is not part of the house.

        Returns:
            List of entities
        """
        # ADR-002 §1: is_latest, not a window function over created_at.
        #
        # This was the FOURTH place inferring "latest", and the last one still
        # using created_at — the rule Stage A already had to correct in
        # get_entity(). It matters more now than it did then: a losing version
        # is preserved with a later created_at than the winner it lost to
        # (ADR-011 §2), so ranking by insert time would load the LOSER into the
        # graph index and serve it from every traversal.
        stmt = (
            select(Entity)
            .where(Entity.entity_type == entity_type, Entity.is_latest.is_(True))
            # ADR-004 §1: no eager load of edges here. The entity-side
            # relationship attributes were joins onto version-pinned edges and
            # are gone; edges are fetched by id (+ T) when needed.
        )

        result = await self.db.execute(stmt)
        # PROTOCOL.md §8: a tombstone is a version, so it is `is_latest` for
        # its id and comes back from the query above like any other current
        # row. It must not be served as a live entity.
        #
        # GraphIndex.load_from_storage already skipped tombstones on its own,
        # which is why traversal and /graph/statistics were right while
        # GET /graph/entities and find_similar served deleted entities as
        # though they still existed -- two readers of the same table
        # disagreeing about what the house contains. Filtering here makes the
        # default correct for every caller and leaves the index's own check as
        # belt and braces.
        entities = list(result.scalars().all())
        if include_deleted:
            return entities
        return [entity for entity in entities if not entity.is_tombstone]

    async def get_entity_versions(self, entity_id: str) -> List[Entity]:
        """
        Get all versions of an entity.

        Args:
            entity_id: Entity ID

        Returns:
            List of all entity versions ordered by creation time
        """
        stmt = (
            select(Entity)
            .where(Entity.id == entity_id)
            .order_by(Entity.created_at.asc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def store_relationship(self, relationship: EntityRelationship) -> EntityRelationship:
        """
        Store relationship between entities.

        Args:
            relationship: Relationship to store

        Returns:
            Stored relationship
        """
        # Generate ID if not provided
        if not relationship.id:
            relationship.id = str(uuid4())

        # ADR-002 §2: every stored row is replicable, or it is invisible to a
        # cursor client (`server_seq > :cursor` is NULL for NULL).
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
        """
        Query relationships with filters.

        Args:
            from_id: Source entity ID (optional)
            to_id: Target entity ID (optional)
            rel_type: Relationship type filter (optional)
            include_all_versions: Include relationships from all entity versions

        Returns:
            List of matching relationships
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

        # ADR-004 §1: currency is the edge's OWN interval, and the filter is
        # unconditional — not gated on whether an endpoint filter was supplied.
        #
        # The gate used to read `if not include_all_versions and (from_id or
        # to_id)`, so any query without an endpoint filter silently returned
        # ended intervals as though they were current. That is the path
        # GraphIndex.load_from_storage takes (no from_id, no to_id), so a device
        # that moved rooms stayed in both rooms for the life of the index.
        #
        # Pushed into SQL rather than applied in Python: `ix_rel_current` exists
        # for exactly this predicate, and history is unbounded by design (§5) —
        # loading every retired interval just to discard it is the one query
        # here that gets worse as the house accumulates edits.
        if not include_all_versions:
            if at is None:
                stmt = stmt.where(EntityRelationship.valid_to.is_(None))
            else:
                moment = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
                stmt = stmt.where(
                    EntityRelationship.valid_from <= moment,
                    or_(EntityRelationship.valid_to.is_(None),
                        EntityRelationship.valid_to > moment),
                )

        # ADR-004 §1: endpoints are no longer joinable from the edge row — the
        # pin that made from_entity/to_entity possible is gone. get_connected()
        # resolves them by id instead.

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 10
    ) -> List[Entity]:
        """
        Search entities by name or content.

        Args:
            query: Search query
            entity_types: Filter by entity types (optional)
            limit: Maximum results to return

        Returns:
            List of matching entities (latest versions only)
        """
        conditions = []

        # Search in name
        conditions.append(Entity.name.ilike(f"%{query}%"))

        # For SQLite JSON search, we need to cast to text
        # This is a simplified search - in production you might want FTS
        # Note: JSON search in SQLite is limited, consider using PostgreSQL for better JSON support

        stmt = select(Entity).where(or_(*conditions))

        if entity_types:
            stmt = stmt.where(Entity.entity_type.in_(entity_types))

        # Get latest versions only - simplified approach
        # In production, you'd want to use the window function approach
        stmt = stmt.order_by(Entity.created_at.desc()).limit(limit * 3)

        result = await self.db.execute(stmt)
        entities = list(result.scalars().all())

        # Simple deduplication - keep only latest version of each entity
        seen_ids = set()
        unique_entities = []

        for entity in entities:
            if entity.id not in seen_ids:
                seen_ids.add(entity.id)
                unique_entities.append(entity)
                if len(unique_entities) >= limit:
                    break

        return unique_entities

    async def get_connected_entities(
        self,
        entity_id: str,
        rel_type: Optional[RelationshipType] = None,
        direction: str = "both"
    ) -> List[Dict[str, Any]]:
        """
        Get all entities connected to a given entity.

        Args:
            entity_id: Center entity ID
            rel_type: Filter by relationship type (optional)
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of connected entities with relationship info
        """
        outgoing = incoming = []
        if direction in ("outgoing", "both"):
            outgoing = await self.get_relationships(
                from_id=entity_id,
                rel_type=rel_type
            )
        if direction in ("incoming", "both"):
            incoming = await self.get_relationships(
                to_id=entity_id,
                rel_type=rel_type
            )

        # ADR-004 §1: the endpoints used to arrive free, eager-loaded through
        # the version-pinned join that the interval model removed. Resolving
        # them one `get_entity()` at a time inside the loops below replaced one
        # query with one per edge — invisible on a test fixture, O(degree) round
        # trips on a hub entity like a room. One batched read instead, which is
        # what the eager load was doing anyway.
        endpoint_ids = (
            {rel.to_entity_id for rel in outgoing}
            | {rel.from_entity_id for rel in incoming}
        )
        endpoints = await self.get_entities_by_ids(endpoint_ids)

        connected = []

        if direction in ("outgoing", "both"):
            for rel in outgoing:
                # ADR-004 §1: resolve the endpoint by id rather than reading a
                # pinned join. The latest version is the right answer for
                # `at = now`; the `at` parameter threads through here when
                # snapshot() lands (ADR-004 §3.4).
                target = endpoints.get(rel.to_entity_id)
                if target:
                    connected.append({
                        "entity": target,
                        "relationship": rel,
                        "direction": "outgoing"
                    })

        if direction in ("incoming", "both"):
            for rel in incoming:
                source = endpoints.get(rel.from_entity_id)
                if source:
                    connected.append({
                        "entity": source,
                        "relationship": rel,
                        "direction": "incoming"
                    })

        return connected
