"""
ADR-006 §1/§3 — FTS5 search and more-like-this.

These assert the properties the ADR asks for, and specifically the two the old
implementation could not satisfy: a content-only match being findable at all,
and similarity that depends on the document rather than on entity_type.
"""

import json

import pytest
from sqlalchemy import text

from funkygibbon.search.fts import (
    build_match_query,
    build_more_like_this_query,
    ensure_fts_schema,
)


# --------------------------------------------------------------------------- #
# Query construction — pure, no database
# --------------------------------------------------------------------------- #

class TestMatchQueryConstruction:
    """FTS5 MATCH has a grammar; raw user input must never reach it."""

    @pytest.mark.parametrize(
        "hostile",
        [
            'thermo"stat',        # unbalanced quote
            "living-room",        # bare hyphen reads as NOT
            "AND",                # bare operator
            "NOT OR AND",
            "nest*)(",
            "'; DROP TABLE entities; --",
        ],
    )
    def test_hostile_input_produces_a_quoted_expression(self, hostile):
        q = build_match_query(hostile)
        # Every emitted term is a quoted phrase, so nothing is interpreted.
        assert q == "" or all(
            part.startswith('"') for part in q.split(" OR ")
        ), q

    def test_empty_and_punctuation_only_yield_no_query(self):
        assert build_match_query("") == ""
        assert build_match_query("   ") == ""
        assert build_match_query("!!! ???") == ""

    def test_terms_are_or_ed_with_prefix_expansion(self):
        assert build_match_query("nest thermostat") == '"nest"* OR "thermostat"*'

    def test_more_like_this_drops_stopwords_short_words_and_digits(self):
        q = build_more_like_this_query(
            "The a of 12 thermostat thermostat heating zone"
        )
        assert '"thermostat"' in q
        assert '"heating"' in q
        assert '"the"' not in q and '"a"' not in q and '"of"' not in q
        assert '"12"' not in q

    def test_more_like_this_orders_by_frequency(self):
        q = build_more_like_this_query("alpha beta beta beta gamma gamma")
        assert q.index('"beta"') < q.index('"gamma"') < q.index('"alpha"')

    def test_more_like_this_does_not_prefix_expand(self):
        # Terms come from a real document, so they are whole words already;
        # expanding them would drag in unrelated stems.
        assert "*" not in build_more_like_this_query("thermostat heating")


# --------------------------------------------------------------------------- #
# Index maintenance — the trigger contract
# --------------------------------------------------------------------------- #

class _Result:
    """Minimal stand-in for a SQLAlchemy Result over a sqlite3 cursor.

    ensure_fts_schema takes a SQLAlchemy sync connection in production; these
    tests drive it with raw sqlite3 to keep the trigger assertions independent
    of the ORM, so .scalar() has to be supplied.
    """

    def __init__(self, cursor):
        self._cursor = cursor

    def scalar(self):
        row = self._cursor.fetchone()
        return row[0] if row else None


@pytest.fixture()
def fts_db(tmp_path):
    """A minimal entities table plus the FTS index, on a real SQLite file."""
    import sqlite3

    conn = sqlite3.connect(tmp_path / "fts.db")
    conn.execute(
        """
        CREATE TABLE entities (
            id TEXT, version TEXT, name TEXT, content TEXT,
            entity_type TEXT, is_latest BOOLEAN
        )
        """
    )

    class _Shim:
        """ensure_fts_schema expects .exec_driver_sql (SQLAlchemy sync conn)."""

        def exec_driver_sql(self, sql):
            cur = conn.cursor()
            cur.executescript(sql) if ";" in sql.strip()[:-1] else cur.execute(sql)
            return _Result(cur)

    ensure_fts_schema(_Shim())
    yield conn
    conn.close()


def _add(conn, eid, name, content, *, latest=True, version="v1"):
    conn.execute(
        "INSERT INTO entities VALUES (?,?,?,?,?,?)",
        (eid, version, name, json.dumps(content), "DEVICE", latest),
    )
    conn.commit()


def _search(conn, expr):
    return [
        r[0]
        for r in conn.execute(
            "SELECT entity_id FROM entities_fts WHERE entities_fts MATCH ? ORDER BY bm25(entities_fts)",
            (expr,),
        )
    ]


class TestIndexMaintenance:
    def test_insert_is_indexed(self, fts_db):
        _add(fts_db, "e1", "Hall Thermostat", {"model": "Nest"})
        assert _search(fts_db, '"thermostat"') == ["e1"]

    def test_content_only_match_is_findable(self, fts_db):
        """The defect the old implementation could not fix.

        Its SQL filtered on name alone, so a term appearing only in content was
        unreachable however well the Python scorer would have ranked it.
        """
        _add(fts_db, "e1", "Hall Unit", {"manufacturer": "Ecobee"})
        assert _search(fts_db, '"ecobee"') == ["e1"]

    def test_non_latest_versions_are_not_indexed(self, fts_db):
        """ADR-002 §1: is_latest is the authority on which version won."""
        _add(fts_db, "e1", "Superseded Widget", {}, latest=False, version="v1")
        assert _search(fts_db, '"superseded"') == []

    def test_losing_a_conflict_removes_the_row_from_search(self, fts_db):
        """is_latest flips without the row's own text changing (ADR-011 §2)."""
        _add(fts_db, "e1", "Contested Widget", {})
        assert _search(fts_db, '"contested"') == ["e1"]

        fts_db.execute("UPDATE entities SET is_latest = 0 WHERE id = 'e1'")
        fts_db.commit()
        assert _search(fts_db, '"contested"') == []

    def test_tombstoned_entities_are_not_searchable(self, fts_db):
        _add(fts_db, "e1", "Removed Sensor", {"deleted": True})
        assert _search(fts_db, '"removed"') == []

    def test_undeleting_restores_searchability(self, fts_db):
        _add(fts_db, "e1", "Flappy Sensor", {"deleted": True})
        assert _search(fts_db, '"flappy"') == []

        fts_db.execute("UPDATE entities SET content = ? WHERE id = 'e1'", (json.dumps({}),))
        fts_db.commit()
        assert _search(fts_db, '"flappy"') == ["e1"]

    def test_delete_removes_from_index(self, fts_db):
        _add(fts_db, "e1", "Doomed Widget", {})
        fts_db.execute("DELETE FROM entities WHERE id = 'e1'")
        fts_db.commit()
        assert _search(fts_db, '"doomed"') == []

    def test_one_row_per_entity_across_versions(self, fts_db):
        """Resync, not append: a new latest version must not duplicate the row."""
        _add(fts_db, "e1", "Widget", {}, latest=False, version="v1")
        _add(fts_db, "e1", "Widget", {}, latest=True, version="v2")
        rows = fts_db.execute(
            "SELECT count(*) FROM entities_fts WHERE entity_id = 'e1'"
        ).fetchone()[0]
        assert rows == 1

    def test_bm25_ranks_denser_matches_first(self, fts_db):
        _add(fts_db, "weak", "Notes", {"body": "thermostat mentioned once"})
        _add(fts_db, "strong", "Thermostat Manual",
             {"body": "thermostat thermostat thermostat"})
        assert _search(fts_db, '"thermostat"')[0] == "strong"


class TestSchemaIsIdempotent:
    def test_second_call_does_not_duplicate_the_backfill(self, fts_db, tmp_path):
        _add(fts_db, "e1", "Solo Widget", {})
        before = fts_db.execute("SELECT count(*) FROM entities_fts").fetchone()[0]

        class _Shim:
            def exec_driver_sql(self, sql):
                cur = fts_db.cursor()
                cur.executescript(sql) if ";" in sql.strip()[:-1] else cur.execute(sql)
                return _Result(cur)

        ensure_fts_schema(_Shim())
        after = fts_db.execute("SELECT count(*) FROM entities_fts").fetchone()[0]
        assert after == before
