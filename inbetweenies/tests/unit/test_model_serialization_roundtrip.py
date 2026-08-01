"""Test that model serialization survives a JSON round-trip.

REGRESSION CONTEXT:
`LocalGraphStorage` (blowing-off) persists the graph as JSON and reloads it with
`Entity(**v)` / `EntityRelationship(**r)`. A reloaded instance therefore carries
*strings* where a freshly-constructed one carries `datetime` objects and enum
members — SQLAlchemy only coerces those on a DB round-trip, not on __init__.

`to_dict()` used to assume the rich types unconditionally, so calling it on a
reloaded object raised AttributeError:
    'str' object has no attribute 'isoformat'
    'str' object has no attribute 'value'

That forced blowing-off to hand-roll a duplicate serializer
(`LocalGraphStorage._entity_to_dict`) purely to work around the shared model.
These tests pin the invariant that makes the duplicate unnecessary:
to_dict() must be *total* and *idempotent* over its own output.
"""

import json
from datetime import datetime, timezone

import pytest

from inbetweenies.models import (
    Entity,
    EntityRelationship,
    EntityType,
    RelationshipType,
    SourceType,
)


def _reload(model_cls, instance):
    """Round-trip an instance through JSON exactly as LocalGraphStorage does."""
    return model_cls(**json.loads(json.dumps(instance.to_dict())))


class TestEntitySerializationRoundTrip:
    """Entity.to_dict() must survive being fed its own reloaded output."""

    def _entity(self):
        entity = Entity(
            id="entity-1",
            version="v1",
            entity_type=EntityType.HOME,
            name="Test Home",
            content={"nested": {"value": 1}},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[],
        )
        entity.created_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        entity.updated_at = datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        return entity

    def test_roundtrip_does_not_raise(self):
        """Reloaded entity serializes without AttributeError."""
        reloaded = _reload(Entity, self._entity())
        reloaded.to_dict()  # regression: used to raise AttributeError

    def test_roundtrip_is_idempotent(self):
        """to_dict() -> reload -> to_dict() must be a fixed point."""
        original = self._entity().to_dict()
        reloaded = _reload(Entity, self._entity()).to_dict()
        assert reloaded == original

    def test_string_timestamps_pass_through_unchanged(self):
        """A pre-serialized timestamp is preserved verbatim, not re-formatted."""
        entity = self._entity()
        entity.created_at = "2025-01-01T10:00:00+00:00"
        entity.updated_at = "2025-01-01T11:00:00+00:00"

        result = entity.to_dict()
        assert result["created_at"] == "2025-01-01T10:00:00+00:00"
        assert result["updated_at"] == "2025-01-01T11:00:00+00:00"

    def test_datetime_timestamps_still_serialize(self):
        """Regression guard: the normal datetime path is unchanged."""
        result = self._entity().to_dict()
        assert result["created_at"] == "2025-01-01T10:00:00+00:00"
        assert result["updated_at"] == "2025-01-01T11:00:00+00:00"

    def test_none_timestamps_still_none(self):
        """Regression guard: None must stay None, not become the string 'None'."""
        entity = self._entity()
        entity.created_at = None
        entity.updated_at = None

        result = entity.to_dict()
        assert result["created_at"] is None
        assert result["updated_at"] is None


class TestRelationshipSerializationRoundTrip:
    """EntityRelationship.to_dict()/__repr__ must tolerate reloaded values."""

    def _relationship(self):
        relationship = EntityRelationship(
            id="rel-1",
            from_entity_id="device-1",
            from_entity_version="v1",
            to_entity_id="room-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={"position": "ceiling"},
            user_id="test-user",
        )
        relationship.created_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        relationship.updated_at = datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        return relationship

    def test_roundtrip_does_not_raise(self):
        """Reloaded relationship serializes without AttributeError."""
        reloaded = _reload(EntityRelationship, self._relationship())
        reloaded.to_dict()  # regression: used to raise AttributeError

    def test_roundtrip_is_idempotent(self):
        """to_dict() -> reload -> to_dict() must be a fixed point."""
        original = self._relationship().to_dict()
        reloaded = _reload(EntityRelationship, self._relationship()).to_dict()
        assert reloaded == original

    def test_string_relationship_type_passes_through(self):
        """A plain-string relationship_type serializes to itself."""
        relationship = self._relationship()
        relationship.relationship_type = "located_in"

        assert relationship.to_dict()["relationship_type"] == "located_in"

    def test_enum_relationship_type_still_serializes_to_value(self):
        """Regression guard: enum members still serialize to their .value."""
        assert self._relationship().to_dict()["relationship_type"] == "located_in"

    def test_repr_tolerates_string_relationship_type(self):
        """__repr__ had the same unguarded .value as to_dict()."""
        relationship = self._relationship()
        relationship.relationship_type = "located_in"

        assert "located_in" in repr(relationship)  # regression: used to raise

    def test_repr_tolerates_enum_and_none(self):
        """Regression guard: __repr__ still handles enums and None."""
        relationship = self._relationship()
        assert "located_in" in repr(relationship)

        relationship.relationship_type = None
        assert "None" in repr(relationship)
