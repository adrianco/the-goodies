"""Test EntityRelationship model functionality."""

import pytest
import json
from datetime import datetime, timezone

from inbetweenies.models import EntityRelationship, RelationshipType


class TestEntityRelationshipModel:
    """Test EntityRelationship model methods and validation."""

    def test_relationship_creation(self, sample_relationship):
        """Test basic relationship creation."""
        assert sample_relationship.id == "rel-1"
        assert sample_relationship.from_entity_id == "device-1"
        assert sample_relationship.from_entity_version == "v1"
        assert sample_relationship.to_entity_id == "room-1"
        assert sample_relationship.to_entity_version == "v1"
        assert sample_relationship.relationship_type == RelationshipType.LOCATED_IN
        assert sample_relationship.properties == {"position": "ceiling"}
        assert sample_relationship.user_id == "test-user"
        assert isinstance(sample_relationship.created_at, datetime)
        assert isinstance(sample_relationship.updated_at, datetime)

    def test_relationship_to_dict(self, sample_relationship):
        """Test relationship serialization to dictionary."""
        rel_dict = sample_relationship.to_dict()

        assert rel_dict["id"] == "rel-1"
        assert rel_dict["from_entity_id"] == "device-1"
        assert rel_dict["from_entity_version"] == "v1"
        assert rel_dict["to_entity_id"] == "room-1"
        assert rel_dict["to_entity_version"] == "v1"
        assert rel_dict["relationship_type"] == "located_in"
        assert rel_dict["properties"] == {"position": "ceiling"}
        assert rel_dict["user_id"] == "test-user"
        assert "created_at" in rel_dict
        assert "updated_at" in rel_dict

    def test_relationship_construction(self):
        """Test relationship construction from parameters."""
        relationship = EntityRelationship(
            id="rel-2",
            from_entity_id="automation-1",
            from_entity_version="v2",
            to_entity_id="device-1",
            to_entity_version="v3",
            relationship_type=RelationshipType.CONTROLS,
            properties={"action": "toggle"},
            user_id="user-2"
        )

        assert relationship.id == "rel-2"
        assert relationship.from_entity_id == "automation-1"
        assert relationship.from_entity_version == "v2"
        assert relationship.to_entity_id == "device-1"
        assert relationship.to_entity_version == "v3"
        assert relationship.relationship_type == RelationshipType.CONTROLS
        assert relationship.properties == {"action": "toggle"}
        assert relationship.user_id == "user-2"

    def test_relationship_json_serialization(self, sample_relationship):
        """Test relationship JSON serialization."""
        # Serialize to JSON
        json_str = json.dumps(sample_relationship.to_dict())

        # Parse JSON back
        rel_dict = json.loads(json_str)

        assert rel_dict["id"] == sample_relationship.id
        assert rel_dict["from_entity_id"] == sample_relationship.from_entity_id
        assert rel_dict["to_entity_id"] == sample_relationship.to_entity_id
        assert rel_dict["relationship_type"] == "located_in"
        assert rel_dict["properties"] == sample_relationship.properties

    def test_relationship_identity(self):
        """Test relationship identity comparison."""
        rel1 = EntityRelationship(
            id="rel-test",
            from_entity_id="e1",
            from_entity_version="v1",
            to_entity_id="e2",
            to_entity_version="v1",
            relationship_type=RelationshipType.CONTAINED_IN,
            properties={},
            user_id="user"
        )

        rel2 = EntityRelationship(
            id="rel-test",  # Same ID
            from_entity_id="e1",
            from_entity_version="v1",
            to_entity_id="e2",
            to_entity_version="v1",
            relationship_type=RelationshipType.CONTAINED_IN,
            properties={},
            user_id="user"
        )

        rel3 = EntityRelationship(
            id="rel-different",  # Different ID
            from_entity_id="e1",
            from_entity_version="v1",
            to_entity_id="e2",
            to_entity_version="v1",
            relationship_type=RelationshipType.CONTAINED_IN,
            properties={},
            user_id="user"
        )

        # Same ID means same relationship
        assert rel1.id == rel2.id

        # Different IDs mean different relationships
        assert rel1.id != rel3.id

    def test_relationship_unique_id(self):
        """Test relationship unique identification."""
        rel1 = EntityRelationship(
            id="rel-test-1",
            from_entity_id="e1",
            from_entity_version="v1",
            to_entity_id="e2",
            to_entity_version="v1",
            relationship_type=RelationshipType.CONTAINED_IN,
            properties={},
            user_id="user"
        )

        rel2 = EntityRelationship(
            id="rel-test-2",
            from_entity_id="e1",
            from_entity_version="v1",
            to_entity_id="e2",
            to_entity_version="v1",
            relationship_type=RelationshipType.CONTAINED_IN,
            properties={},
            user_id="user"
        )

        # Different IDs even with same connections
        assert rel1.id != rel2.id

        # Can track multiple relationships
        relationships = [rel1, rel2]
        assert len(relationships) == 2

    def test_relationship_types(self):
        """Test all relationship types."""
        types = [
            RelationshipType.LOCATED_IN,
            RelationshipType.CONTROLS,
            RelationshipType.CONNECTS_TO,
            RelationshipType.PART_OF,
            RelationshipType.MANAGES,
            RelationshipType.DOCUMENTED_BY,
            RelationshipType.PROCEDURE_FOR,
            RelationshipType.TRIGGERED_BY,
            RelationshipType.DEPENDS_ON,
            RelationshipType.CONTAINED_IN,
            RelationshipType.MONITORS,
            RelationshipType.AUTOMATES
        ]

        for rel_type in types:
            relationship = EntityRelationship(
                id=f"rel-{rel_type.value}",
                from_entity_id="e1",
                from_entity_version="v1",
                to_entity_id="e2",
                to_entity_version="v1",
                relationship_type=rel_type,
                properties={},
                user_id="user"
            )

            assert relationship.relationship_type == rel_type
            rel_dict = relationship.to_dict()
            assert rel_dict["relationship_type"] == rel_type.value

    def test_relationship_with_null_timestamps(self):
        """Test relationship with None timestamps."""
        relationship = EntityRelationship(
            id="rel-test",
            from_entity_id="e1",
            from_entity_version="v1",
            to_entity_id="e2",
            to_entity_version="v1",
            relationship_type=RelationshipType.CONTAINED_IN,
            properties={},
            user_id="user",
            created_at=None,
            updated_at=None
        )

        rel_dict = relationship.to_dict()
        assert rel_dict["created_at"] is None
        assert rel_dict["updated_at"] is None

        # Verify None timestamps are handled
        assert rel_dict["created_at"] is None
        assert rel_dict["updated_at"] is None

    def test_relationship_properties(self):
        """Test various property types."""
        test_properties = [
            {},  # Empty dict
            {"key": "value"},  # Simple string
            {"count": 42},  # Number
            {"enabled": True},  # Boolean
            {"nested": {"inner": "value"}},  # Nested dict
            {"list": [1, 2, 3]},  # List
            {  # Complex mixed types
                "position": "ceiling",
                "distance": 3.5,
                "active": False,
                "tags": ["smart", "light"],
                "config": {"brightness": 80, "color": "warm"}
            }
        ]

        for props in test_properties:
            relationship = EntityRelationship(
                id="rel-test",
                from_entity_id="e1",
                from_entity_version="v1",
                to_entity_id="e2",
                to_entity_version="v1",
                relationship_type=RelationshipType.CONTAINED_IN,
                properties=props,
                user_id="user"
            )

            # Test to_dict preserves properties
            rel_dict = relationship.to_dict()
            assert rel_dict["properties"] == props

            # Test properties are preserved in dict
            assert rel_dict["properties"] == props

    def test_bidirectional_relationships(self):
        """Test relationships in both directions."""
        # Device -> Room (located_in)
        rel1 = EntityRelationship(
            id="rel-1",
            from_entity_id="device-1",
            from_entity_version="v1",
            to_entity_id="room-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            user_id="user"
        )

        # Room -> Device (contains) - inverse relationship
        rel2 = EntityRelationship(
            id="rel-2",
            from_entity_id="room-1",
            from_entity_version="v1",
            to_entity_id="device-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.CONTAINED_IN,
            properties={},
            user_id="user"
        )

        assert rel1.from_entity_id == rel2.to_entity_id
        assert rel1.to_entity_id == rel2.from_entity_id
        assert rel1.relationship_type == RelationshipType.LOCATED_IN
        assert rel2.relationship_type == RelationshipType.CONTAINED_IN

    def test_self_referential_relationship(self):
        """Test relationship where entity references itself."""
        relationship = EntityRelationship(
            id="rel-self",
            from_entity_id="entity-1",
            from_entity_version="v2",
            to_entity_id="entity-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.PART_OF,  # v2 is part of v1 (version chain)
            properties={"reason": "update"},
            user_id="user"
        )

        assert relationship.from_entity_id == relationship.to_entity_id
        assert relationship.from_entity_version != relationship.to_entity_version

    def test_relationship_version_tracking(self):
        """Test relationships between different entity versions."""
        # Relationship to specific version
        rel1 = EntityRelationship(
            id="rel-1",
            from_entity_id="automation-1",
            from_entity_version="v3",  # Specific version of automation
            to_entity_id="device-1",
            to_entity_version="v2",  # Specific version of device
            relationship_type=RelationshipType.CONTROLS,
            properties={},
            user_id="user"
        )

        # Relationship to different versions
        rel2 = EntityRelationship(
            id="rel-2",
            from_entity_id="automation-1",
            from_entity_version="v4",  # Newer version
            to_entity_id="device-1",
            to_entity_version="v3",  # Newer version
            relationship_type=RelationshipType.CONTROLS,
            properties={},
            user_id="user"
        )

        # Same entities, different versions
        assert rel1.from_entity_id == rel2.from_entity_id
        assert rel1.to_entity_id == rel2.to_entity_id

        # But different version combinations
        assert rel1.from_entity_version != rel2.from_entity_version
        assert rel1.to_entity_version != rel2.to_entity_version
