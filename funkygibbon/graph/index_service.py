"""
Ownership, write-through and drift detection for the in-memory GraphIndex.

ADR-003 in one paragraph
------------------------
The graph index used to be a module-global in ``api/routers/graph.py``, built
lazily on the first request and never invalidated. Sync-applied changes never
touched it and REST ``create_entity`` patched it only halfway, so a freshly
created or freshly synced entity was invisible to ``find_path`` until the
process restarted (design review finding F2). This module replaces that global
with an application-owned service:

1. **Single owner** -- ``create_app()`` builds exactly one ``GraphIndexService``
   and stores it on ``app.state.graph_index``; routers receive it through the
   dependencies in ``funkygibbon.api.dependencies``. Nothing else constructs a
   ``GraphIndex``.
2. **Write-through** -- every mutation path calls ``entity_written`` /
   ``relationship_written`` / ``apply_external_writes`` in the same code path
   that wrote to storage. Updates are O(1) against the live index; the identity
   of ``service.index`` never changes, so long-lived holders (the MCP server,
   the search engine) never end up pointing at a stale object.
3. **Generation-tagged rebuild as the safety net** -- the service remembers a
   cheap storage marker and re-reads it on every indexed read. If storage moved
   without the index being told, that is a write path which bypassed rule 2: the
   service logs loudly and rebuilds.
4. **One worker process** -- asserted at startup, see
   ``assert_single_worker_posture``.
5. **Deleted entities excluded** -- tombstones are dropped at load and removed
   on write-through (see ``GraphIndex.upsert_entity``).

STAGE-C NOTE ON THE GENERATION MARKER
-------------------------------------
ADR-003 decision 3 specifies the ADR-002 ``server_seq`` as the generation tag,
and since Stage C that is what ``StorageMarker`` carries: ``max(server_seq)``
for entities, plus row count and ``max(updated_at)`` for
relationships, which is one cheap aggregate query per table and is enough to
notice any insert, update or tombstone. When ADR-002 lands, replace
``StorageMarker``/``_read_marker`` with a single ``max(server_seq)`` read and
compare monotonically -- the rest of this module does not change.
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Entity, EntityRelationship
from ..repositories.graph import GraphRepository
from .index import GraphIndex

logger = logging.getLogger(__name__)


# Environment switch used by the concurrency assertion. Set it to a falsey value
# ("0"/"false"/"no") to run without the in-memory index, which is the only
# configuration in which more than one worker process is permitted.
GRAPH_INDEX_ENABLED_ENV = "GRAPH_INDEX_ENABLED"

# Worker-count environment variables understood by uvicorn/gunicorn deployments.
_WORKER_ENV_VARS = ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS")


def graph_index_enabled() -> bool:
    """Whether this process should keep an in-memory graph index."""
    raw = os.getenv(GRAPH_INDEX_ENABLED_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def configured_worker_count() -> int:
    """Worker processes this deployment asks for (1 when unset/unparseable)."""
    for name in _WORKER_ENV_VARS:
        raw = os.getenv(name)
        if raw is None or not raw.strip():
            continue
        try:
            return int(raw)
        except ValueError:
            logger.warning("Ignoring non-numeric %s=%r when checking worker count", name, raw)
    return 1


def assert_single_worker_posture() -> None:
    """Refuse to start with more than one worker while the index is enabled.

    ADR-003 decision 4: the index lives in the process's own memory, so N worker
    processes means N independently drifting copies. Today's deployment happens
    to run one worker; this turns that accident into a checked invariant. Run
    with ``GRAPH_INDEX_ENABLED=false`` if you genuinely need multiple workers --
    then no process holds an index and there is nothing to diverge.
    """
    workers = configured_worker_count()
    if workers > 1 and graph_index_enabled():
        raise RuntimeError(
            f"FunkyGibbon is configured for {workers} worker processes, but the "
            f"in-memory graph index (ADR-003) is a per-process structure and "
            f"would diverge between workers. Run a single worker, or set "
            f"{GRAPH_INDEX_ENABLED_ENV}=false to disable the index."
        )


@dataclass(frozen=True)
class StorageMarker:
    """Generation tag for the index: ADR-002's ``server_seq`` (ADR-003 §3).

    ``max(server_seq)`` is the generation the index was built at. It is
    monotonic and assigned in apply order, so a single integer comparison
    answers "has anything been written since?".

    This replaces a stand-in of row counts plus ``max(updated_at)``, used while
    ``server_seq`` did not exist. That stand-in had a real blind spot: an
    in-place update that changed neither the row count nor a timestamp within
    the clock's resolution was invisible to it, so drift could go undetected —
    the exact failure it exists to catch.

    Relationships are not versioned and carry no ``server_seq``, so their count
    and ``max(updated_at)`` are still the best available signal for that table.
    """

    entity_seq: Optional[int] = None
    relationship_rows: int = 0
    latest_relationship_update: Optional[Any] = None


async def _read_marker(db: AsyncSession) -> StorageMarker:
    """Read the generation tag. Two aggregates, no row scan."""
    entity_seq = (await db.execute(select(func.max(Entity.server_seq)))).scalar()
    relationships = (
        await db.execute(
            select(func.count(EntityRelationship.id), func.max(EntityRelationship.updated_at))
        )
    ).one()
    return StorageMarker(
        entity_seq=entity_seq,
        relationship_rows=relationships[0] or 0,
        latest_relationship_update=_as_marker_value(relationships[1]),
    )


def _as_marker_value(value: Any) -> Any:
    """Normalise a timestamp aggregate so equality is stable across drivers."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class GraphIndexService:
    """The application's single owner of a :class:`GraphIndex`.

    Concurrency posture (ADR-003 decision 4): one worker process, and within it
    the index is mutated only from request handlers running on the event loop.
    There is no lock -- every mutation below is a synchronous, non-awaiting
    critical section, so it cannot interleave with another coroutine.
    """

    def __init__(self, index: Optional[GraphIndex] = None, *, enabled: Optional[bool] = None):
        # The index instance is created once and mutated in place forever after:
        # rebuilds clear and refill *this* object rather than replacing it, so
        # references handed out earlier stay valid.
        self.index = index if index is not None else GraphIndex()
        self.enabled = graph_index_enabled() if enabled is None else enabled
        self.loaded = False
        # Monotonic counter bumped on every write-through and every rebuild.
        # Purely an observability hook (tests assert on it, logs report it) —
        # drift detection uses StorageMarker's server_seq, not this.
        self.generation = 0
        self.rebuild_count = 0
        self._marker: Optional[StorageMarker] = None

    # ------------------------------------------------------------------
    # Load / rebuild
    # ------------------------------------------------------------------

    async def rebuild(self, db: AsyncSession, *, reason: str) -> None:
        """Reload the whole index from storage, in place."""
        if not self.enabled:
            return
        await self.index.load_from_storage(GraphRepository(db))
        self._marker = await _read_marker(db)
        self.loaded = True
        self.generation += 1
        self.rebuild_count += 1
        logger.info(
            "GraphIndex rebuilt (%s): %d entities, %d edges, generation=%d",
            reason,
            len(self.index.entities),
            len(self.index.relationships_by_id),
            self.generation,
        )

    async def ensure_current(self, db: AsyncSession) -> GraphIndex:
        """Return an index that reflects storage.

        Loads on first use, then compares the recorded marker with storage on
        every read. A mismatch means some write path bypassed write-through
        (ADR-003 decision 3), which is a bug worth shouting about -- but the read
        still gets correct data because we rebuild before returning.
        """
        if not self.enabled:
            return self.index

        if not self.loaded:
            await self.rebuild(db, reason="initial load")
            return self.index

        current = await _read_marker(db)
        if current != self._marker:
            logger.warning(
                "GraphIndex drift detected (recorded=%s storage=%s) -- a write path "
                "bypassed write-through (ADR-003). Rebuilding.",
                self._marker,
                current,
            )
            await self.rebuild(db, reason="drift detected")
        return self.index

    # ------------------------------------------------------------------
    # Write-through
    # ------------------------------------------------------------------

    async def entity_written(self, db: AsyncSession, entity: Entity) -> None:
        """Record an entity that was just written to storage.

        Call this in the same code path as the write, after the commit. A
        tombstone (``content["deleted"]``) removes the entity from the index.
        """
        if not self.enabled:
            return
        if not self.loaded:
            # Nothing to patch yet: the index has never been loaded, so the
            # first read pulls this write in with everything else.
            return
        self.index.upsert_entity(entity)
        self.generation += 1
        await self._sync_marker(db)

    async def relationship_written(self, db: AsyncSession, rel: EntityRelationship) -> None:
        """Record a relationship that was just written to storage."""
        if not self.enabled:
            return
        if not self.loaded:
            return
        # An edge is only useful once both endpoints are in the index; if one is
        # missing (tombstoned, or not yet synced) the edge is dropped, matching
        # what load_from_storage does.
        if (rel.from_entity_id in self.index.entities
                and rel.to_entity_id in self.index.entities):
            self.index.upsert_relationship(rel)
        self.generation += 1
        await self._sync_marker(db)

    async def apply_external_writes(
        self,
        db: AsyncSession,
        *,
        entity_ids: Sequence[str] = (),
        relationship_ids: Sequence[str] = (),
    ) -> None:
        """Write-through for a batch of ids that another component just persisted.

        This is the entry point for the sync-apply path (ADR-003 decision 2):
        sync knows *which* entities and relationships it applied but not the ORM
        objects the index wants, so the ids are re-read here (latest version per
        entity) and folded into the index. Ids that no longer resolve, or that
        resolve to a tombstone, are removed from the index.

        Cost is O(len(ids)) queries, not a rebuild.
        """
        if not self.enabled:
            return
        if not entity_ids and not relationship_ids:
            return
        if not self.loaded:
            # First read will load everything, including these writes.
            return

        repo = GraphRepository(db)

        for entity_id in _unique(entity_ids):
            entity = await repo.get_entity(entity_id)
            if entity is None:
                self.index.remove_entity(entity_id)
            else:
                # upsert_entity removes tombstones and adds/replaces anything else
                self.index.upsert_entity(entity)

        if relationship_ids:
            wanted = set(_unique(relationship_ids))
            found = (
                await db.execute(
                    select(EntityRelationship).where(EntityRelationship.id.in_(wanted))
                )
            ).scalars().all()
            for rel in found:
                wanted.discard(rel.id)
                if (rel.from_entity_id in self.index.entities
                        and rel.to_entity_id in self.index.entities):
                    self.index.upsert_relationship(rel)
                else:
                    self.index.remove_relationship(rel.id)
            for missing_id in wanted:
                self.index.remove_relationship(missing_id)

        self.generation += 1
        await self._sync_marker(db)
        logger.debug(
            "GraphIndex write-through: %d entities, %d relationships, generation=%d",
            len(tuple(_unique(entity_ids))),
            len(tuple(_unique(relationship_ids))),
            self.generation,
        )

    async def _sync_marker(self, db: AsyncSession) -> None:
        """Re-record the storage marker after a write-through.

        Without this the very next read would see storage ahead of the recorded
        marker and rebuild -- the drift net firing on our own writes.
        """
        self._marker = await _read_marker(db)


def _unique(values: Iterable[str]) -> Iterable[str]:
    """Order-preserving de-duplication."""
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            yield value


# ----------------------------------------------------------------------
# Request-scoped access for code that cannot take a FastAPI dependency
# ----------------------------------------------------------------------
#
# ``funkygibbon/api/sync.py`` applies changes deep inside ``SyncHandler``, which
# only ever gets a database session. Rather than thread the service through
# every call site, ``create_app()`` installs an ASGI middleware that binds the
# application's service to this ContextVar for the duration of each request.
# This is *not* a second owner: it is a pointer to the one object on
# ``app.state``, scoped to the request, and it resolves to None outside a request
# (unit tests driving SyncHandler directly), where the write-through is a no-op.

_current_service: ContextVar[Optional["GraphIndexService"]] = ContextVar(
    "funkygibbon_graph_index_service", default=None
)


def bind_graph_index_service(service: Optional["GraphIndexService"]):
    """Bind the service for the current context. Returns the ContextVar token."""
    return _current_service.set(service)


def unbind_graph_index_service(token) -> None:
    """Undo :func:`bind_graph_index_service`."""
    _current_service.reset(token)


def current_graph_index_service() -> Optional["GraphIndexService"]:
    """The service serving the in-flight request, if any."""
    return _current_service.get()


async def write_through_applied_changes(
    db: AsyncSession,
    *,
    entity_ids: Sequence[str] = (),
    relationship_ids: Sequence[str] = (),
) -> None:
    """Write-through hook for mutation paths outside the dependency graph.

    Used by the sync-apply path. No-op when no index is bound to the current
    request (index disabled, or called outside a request), in which case the
    drift check on the next read is the backstop.
    """
    service = current_graph_index_service()
    if service is None:
        return
    await service.apply_external_writes(
        db, entity_ids=entity_ids, relationship_ids=relationship_ids
    )
