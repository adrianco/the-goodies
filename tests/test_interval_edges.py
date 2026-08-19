"""
ADR-004 §1 — edges as immutable interval rows.

The property under test is the one the review's C4 finding says is missing
today: after an edge changes, the *prior* topology is still recoverable. These
cover the interval predicate itself; the end-and-insert write path and
snapshot(T) build on it.
"""

from datetime import UTC, datetime, timedelta

import pytest

from inbetweenies.models.relationship import EntityRelationship


T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _edge(valid_from=None, valid_to=None):
    return EntityRelationship(
        id="r1",
        from_entity_id="a",
        to_entity_id="b",
        relationship_type="located_in",
        valid_from=valid_from,
        valid_to=valid_to,
    )


class TestIntervalPredicate:
    def test_open_interval_is_current_now_and_later(self):
        edge = _edge(valid_from=T0)
        assert edge.is_current_at(T1)
        assert edge.is_current_at()  # now

    def test_not_yet_valid_before_its_start(self):
        assert _edge(valid_from=T1).is_current_at(T0) is False

    def test_ended_edge_is_not_current_after_its_end(self):
        assert _edge(valid_from=T0, valid_to=T1).is_current_at(T2) is False

    def test_ended_edge_is_still_current_inside_its_interval(self):
        """The C4 property: history stays answerable after the edge ends."""
        edge = _edge(valid_from=T0, valid_to=T2)
        assert edge.is_current_at(T1)

    def test_interval_is_half_open_at_the_start(self):
        assert _edge(valid_from=T1, valid_to=T2).is_current_at(T1)

    def test_interval_is_half_open_at_the_end(self):
        """Closed-open, so a handover instant yields exactly one live edge."""
        assert _edge(valid_from=T0, valid_to=T1).is_current_at(T1) is False

    def test_handover_instant_yields_exactly_one_current_edge(self):
        """End-and-insert at the same instant must not double-count or gap."""
        old = _edge(valid_from=T0, valid_to=T1)
        new = _edge(valid_from=T1)
        live = [e for e in (old, new) if e.is_current_at(T1)]
        assert len(live) == 1
        assert live[0] is new

    def test_null_valid_from_reads_as_always_true(self):
        """Pre-migration rows must not silently vanish from every snapshot."""
        assert _edge().is_current_at(T0)
        assert _edge(valid_to=T2).is_current_at(T1)


class TestNaiveDatetimeHandling:
    """SQLite round-trips DateTime(timezone=True) as naive; comparison must not raise."""

    def test_naive_bounds_are_treated_as_utc(self):
        edge = _edge(
            valid_from=datetime(2026, 3, 1, 12, 0),
            valid_to=datetime(2026, 9, 1, 12, 0),
        )
        assert edge.is_current_at(T1)
        assert edge.is_current_at(T2) is False

    def test_mixed_naive_and_aware_does_not_raise(self):
        edge = _edge(valid_from=datetime(2026, 3, 1, 12, 0), valid_to=T2)
        assert edge.is_current_at(T1)


class TestSerialization:
    def test_interval_bounds_are_emitted(self):
        d = _edge(valid_from=T0, valid_to=T1).to_dict()
        assert d["valid_from"] == T0.isoformat()
        assert d["valid_to"] == T1.isoformat()

    def test_open_interval_emits_null_rather_than_omitting(self):
        """None distinguishes "still true" from a peer that lacks the field."""
        d = _edge(valid_from=T0).to_dict()
        assert "valid_to" in d and d["valid_to"] is None
