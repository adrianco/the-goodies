"""
FTS5 index over entity name and content (ADR-006 §1).

Why triggers rather than the repository write path
--------------------------------------------------
ADR-006 §1 allows either. Triggers win here because entities are written from
more than one place: ``SQLGraphOperations.store_entity`` (REST/MCP),
``api/sync.py::_insert_version`` (sync apply, including losing versions), and
``migrate.py``. A write path that forgets to update the index produces a silent
recall bug — the entity exists and is invisible to search, which is exactly the
failure mode ADR-003 documents for the graph index. A trigger cannot be
forgotten by a new call site.

What is indexed
---------------
Exactly the rows a reader can see: ``is_latest = 1`` and not tombstoned.
ADR-002 gave us ``is_latest`` as the authoritative record of which version won,
so the index follows it rather than re-deriving "latest" from version strings —
the same mistake ADR-002 §1 called out in the old ``_preserve_losing_version``.
Losing and superseded versions stay in ``entities`` (ADR-011 §2) and stay out of
search.

Content is indexed as its raw JSON text. The unicode61 tokenizer splits on
non-alphanumerics, so ``{"model": "Nest Thermostat"}`` yields the tokens
``model``, ``Nest``, ``Thermostat``. Keys become searchable, which is mild noise
that BM25 discounts naturally — a key appearing in every document carries almost
no inverse document frequency.
"""

from __future__ import annotations

import logging
import re
from typing import List

logger = logging.getLogger(__name__)

FTS_TABLE = "entities_fts"

# A tombstone is content.deleted == true (funkygibbon/api/sync.py §8). SQLite's
# json_extract returns 1 for a JSON true, but a string "true" is possible from
# older rows, so both are excluded.
_VISIBLE_PREDICATE = """
    e.is_latest = 1
    AND COALESCE(json_extract(e.content, '$.deleted'), 0) NOT IN (1, 'true')
"""

_CREATE_TABLE = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5(
    entity_id UNINDEXED,
    name,
    content,
    tokenize = 'unicode61'
)
"""

# Each trigger resyncs one entity id: delete then re-insert if it is currently
# visible. Resync rather than incremental patching because is_latest flips
# during conflict resolution — a version that was latest can stop being latest
# without that row itself changing.
_RESYNC = f"""
    DELETE FROM {FTS_TABLE} WHERE entity_id = %(id)s;
    INSERT INTO {FTS_TABLE}(entity_id, name, content)
        SELECT e.id, e.name, COALESCE(e.content, '')
        FROM entities e
        WHERE e.id = %(id)s AND {_VISIBLE_PREDICATE};
"""

_TRIGGERS = [
    f"""
    CREATE TRIGGER IF NOT EXISTS {FTS_TABLE}_ai AFTER INSERT ON entities BEGIN
        {_RESYNC % {'id': 'NEW.id'}}
    END
    """,
    f"""
    CREATE TRIGGER IF NOT EXISTS {FTS_TABLE}_au AFTER UPDATE ON entities BEGIN
        {_RESYNC % {'id': 'NEW.id'}}
    END
    """,
    f"""
    CREATE TRIGGER IF NOT EXISTS {FTS_TABLE}_ad AFTER DELETE ON entities BEGIN
        {_RESYNC % {'id': 'OLD.id'}}
    END
    """,
]

_BACKFILL = f"""
INSERT INTO {FTS_TABLE}(entity_id, name, content)
    SELECT e.id, e.name, COALESCE(e.content, '')
    FROM entities e
    WHERE {_VISIBLE_PREDICATE}
"""


def register_fts_ddl() -> None:
    """Attach FTS creation to ``entities`` table creation.

    Binding to the metadata event rather than to ``init_db`` is the same
    argument as using triggers over write-path hooks, one level up: tests,
    ``populate_graph_db.py`` and any future tool call ``create_all`` directly
    and never touch ``init_db``. Hanging the index off ``init_db`` meant every
    such caller got an entities table with no index and a search endpoint that
    raised "no such table" — found exactly that way, by ADR-003's lifecycle
    tests.

    Idempotent and import-safe: SQLAlchemy de-duplicates identical listeners,
    and the DDL is guarded by IF NOT EXISTS.
    """
    from sqlalchemy import event

    from inbetweenies.models.entity import Entity

    def _after_create(target, connection, **kw):
        # Non-SQLite backends have no FTS5; ADR-001 keeps us on SQLite, and if
        # that exit criterion ever triggers this becomes a tsvector column.
        if connection.dialect.name != "sqlite":
            return
        # DDL only, deliberately not the backfill: the entities table was just
        # created and is empty, so there is nothing to backfill — and an INSERT
        # here would open a write transaction inside create_all's, which makes
        # the following `PRAGMA synchronous` fail with "Safety level may not be
        # changed inside a transaction".
        create_fts_objects(connection)

    event.listen(Entity.__table__, "after_create", _after_create)


def create_fts_objects(conn) -> None:
    """Create the FTS table and its triggers. Idempotent, no data written."""
    conn.exec_driver_sql(_CREATE_TABLE)
    for trigger in _TRIGGERS:
        conn.exec_driver_sql(trigger)


def ensure_fts_schema(conn) -> None:
    """Create the FTS table and triggers, and backfill once. Idempotent.

    Takes a raw DBAPI-ish connection exposing ``exec_driver_sql`` (SQLAlchemy
    sync connection inside ``run_sync``). Safe to call on every startup: the
    table and triggers use IF NOT EXISTS, and the backfill only runs when the
    index is empty, so an existing index is never duplicated.
    """
    create_fts_objects(conn)

    already = conn.exec_driver_sql(f"SELECT count(*) FROM {FTS_TABLE}").scalar()
    if not already:
        conn.exec_driver_sql(_BACKFILL)
        count = conn.exec_driver_sql(f"SELECT count(*) FROM {FTS_TABLE}").scalar()
        logger.info("FTS5 index built over %d visible entities (ADR-006 §1)", count)


# --------------------------------------------------------------------------- #
# Query construction
# --------------------------------------------------------------------------- #

# FTS5 MATCH has its own grammar: bare user input containing a quote, a hyphen
# or a bare AND/OR/NOT is a syntax error, not a zero-result search. Every term
# is therefore stripped to alphanumerics and re-quoted as a phrase.
_TERM = re.compile(r"[^\w]+", re.UNICODE)

# Terms carrying no signal in a query built from an entity's own text.
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the
    to was were will with true false null""".split()
)


def build_match_query(text: str, *, prefix: bool = True) -> str:
    """Turn free text into a safe FTS5 MATCH expression, or "" if nothing usable.

    Terms are OR-ed rather than AND-ed: BM25 already ranks a document matching
    every term above one matching a single term, so OR keeps recall (the old
    substring scorer was forgiving) without giving up precision in the ordering.
    """
    terms = [t for t in _TERM.split(text or "") if t]
    if not terms:
        return ""
    suffix = "*" if prefix else ""
    return " OR ".join(f'"{t}"{suffix}' for t in terms)


def build_more_like_this_query(text: str, *, max_terms: int = 12) -> str:
    """Build a more-like-this query from a document's own text (ADR-006 §3).

    This is the standing behaviour for ``find_similar_entities`` until §2's
    embeddings have an owner. Top terms are selected by frequency after
    stopword removal — crude next to a vector, and a large improvement on the
    shared-word count it replaces.
    """
    counts: dict[str, int] = {}
    for raw in _TERM.split(text or ""):
        term = raw.lower()
        if len(term) < 3 or term in _STOPWORDS or term.isdigit():
            continue
        counts[term] = counts.get(term, 0) + 1
    if not counts:
        return ""
    top: List[str] = sorted(counts, key=lambda t: (-counts[t], t))[:max_terms]
    # No prefix expansion here: these terms come from a real document, so they
    # are already whole words, and expanding them would drag in unrelated stems.
    return " OR ".join(f'"{t}"' for t in top)
