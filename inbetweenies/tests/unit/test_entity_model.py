"""Test Entity model functionality."""

import pytest
import json
from datetime import datetime, timezone
from uuid import uuid4

from inbetweenies.models import Entity, EntityType, SourceType


class TestEntityModel:
    """Test Entity model methods and validation."""

    def test_entity_creation(self, sample_entity):
        """Test basic entity creation."""
        assert sample_entity.id == "test-entity-1"
        assert sample_entity.version == "v1"
        assert sample_entity.entity_type == EntityType.DEVICE
        assert sample_entity.name == "Test Device"
        assert sample_entity.content["manufacturer"] == "TestCorp"
        assert sample_entity.source_type == SourceType.MANUAL
        assert sample_entity.user_id == "test-user"
        assert isinstance(sample_entity.created_at, datetime)
        assert isinstance(sample_entity.updated_at, datetime)

    def test_entity_to_dict(self, sample_entity):
        """Test entity serialization to dictionary."""
        entity_dict = sample_entity.to_dict()

        assert entity_dict["id"] == "test-entity-1"
        assert entity_dict["version"] == "v1"
        assert entity_dict["entity_type"] == "device"
        assert entity_dict["name"] == "Test Device"
        assert entity_dict["content"] == {"manufacturer": "TestCorp", "model": "T1000"}
        assert entity_dict["source_type"] == "manual"
        assert entity_dict["user_id"] == "test-user"
        assert entity_dict["parent_versions"] == []
        assert "created_at" in entity_dict
        assert "updated_at" in entity_dict

    def test_entity_construction(self):
        """Test entity construction from parameters."""
        entity = Entity(
            id="test-2",
            version="v2",
            entity_type=EntityType.ROOM,
            name="Bedroom",
            content={"floor": 2},
            source_type=SourceType.HOMEKIT,
            user_id="user-2",
            parent_versions=["v1"]
        )

        assert entity.id == "test-2"
        assert entity.version == "v2"
        assert entity.entity_type == EntityType.ROOM
        assert entity.name == "Bedroom"
        assert entity.content["floor"] == 2
        assert entity.source_type == SourceType.HOMEKIT
        assert entity.user_id == "user-2"
        assert entity.parent_versions == ["v1"]

    def test_entity_json_serialization(self, sample_entity):
        """Test entity JSON serialization."""
        # Serialize to JSON
        json_str = json.dumps(sample_entity.to_dict())

        # Parse JSON back
        entity_dict = json.loads(json_str)

        assert entity_dict["id"] == sample_entity.id
        assert entity_dict["version"] == sample_entity.version
        assert entity_dict["entity_type"] == "device"
        assert entity_dict["name"] == sample_entity.name
        assert entity_dict["content"] == sample_entity.content

    def test_entity_identity(self):
        """Test entity identity comparison."""
        entity1 = Entity(
            id="test",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user"
        )

        entity2 = Entity(
            id="test",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user"
        )

        entity3 = Entity(
            id="test",
            version="v2",  # Different version
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user"
        )

        # Same ID and version means they identify the same entity version
        assert entity1.id == entity2.id
        assert entity1.version == entity2.version

        # Different versions of same entity
        assert entity1.id == entity3.id
        assert entity1.version != entity3.version

    def test_entity_unique_identity(self):
        """Test entity unique identity with id and version."""
        entity1 = Entity(
            id="test",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user"
        )

        entity2 = Entity(
            id="test",
            version="v2",
            entity_type=EntityType.DEVICE,
            name="Device Updated",
            content={"modified": True},
            source_type=SourceType.MANUAL,
            user_id="user"
        )

        # Different versions of same entity have different identities
        assert entity1.id == entity2.id
        assert entity1.version != entity2.version

        # Can track multiple versions
        versions = [entity1, entity2]
        assert len(versions) == 2

    def test_entity_with_null_timestamps(self):
        """Test entity with None timestamps."""
        entity = Entity(
            id="test",
            version="v1",
            entity_type=EntityType.AUTOMATION,
            name="Test",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            created_at=None,
            updated_at=None
        )

        entity_dict = entity.to_dict()
        assert entity_dict["created_at"] is None
        assert entity_dict["updated_at"] is None

    def test_entity_types(self):
        """Test all entity types."""
        types = [
            EntityType.HOME,
            EntityType.ROOM,
            EntityType.DEVICE,
            EntityType.ZONE,
            EntityType.DOOR,
            EntityType.WINDOW,
            EntityType.PROCEDURE,
            EntityType.MANUAL,
            EntityType.NOTE,
            EntityType.SCHEDULE,
            EntityType.AUTOMATION
        ]

        for entity_type in types:
            entity = Entity(
                id=f"test-{entity_type.value}",
                version="v1",
                entity_type=entity_type,
                name=f"Test {entity_type.value}",
                content={},
                source_type=SourceType.MANUAL,
                user_id="user"
            )

            assert entity.entity_type == entity_type
            entity_dict = entity.to_dict()
            assert entity_dict["entity_type"] == entity_type.value

    def test_source_types(self):
        """Test all source types."""
        types = [
            SourceType.HOMEKIT,
            SourceType.MATTER,
            SourceType.MANUAL,
            SourceType.IMPORTED,
            SourceType.GENERATED
        ]

        for source_type in types:
            entity = Entity(
                id=f"test-{source_type.value}",
                version="v1",
                entity_type=EntityType.DEVICE,
                name=f"Test {source_type.value}",
                content={},
                source_type=source_type,
                user_id="user"
            )

            assert entity.source_type == source_type
            entity_dict = entity.to_dict()
            assert entity_dict["source_type"] == source_type.value

    def test_entity_content_types(self):
        """Test various content types."""
        test_contents = [
            {},  # Empty dict
            {"simple": "value"},  # Simple string value
            {"number": 42},  # Number value
            {"boolean": True},  # Boolean value
            {"nested": {"key": "value"}},  # Nested dict
            {"list": [1, 2, 3]},  # List value
            {"mixed": {"str": "text", "num": 123, "bool": False, "list": ["a", "b"]}}  # Mixed types
        ]

        for content in test_contents:
            entity = Entity(
                id="test",
                version="v1",
                entity_type=EntityType.DEVICE,
                name="Test",
                content=content,
                source_type=SourceType.MANUAL,
                user_id="user"
            )

            # Test to_dict preserves content
            entity_dict = entity.to_dict()
            assert entity_dict["content"] == content

            # Test content is preserved in dict
            assert entity_dict["content"] == content

    def test_entity_parent_versions(self):
        """Test parent versions handling."""
        # No parents
        entity1 = Entity(
            id="test",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=[]
        )
        assert entity1.parent_versions == []

        # Single parent
        entity2 = Entity(
            id="test",
            version="v2",
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=["v1"]
        )
        assert entity2.parent_versions == ["v1"]

        # Multiple parents (merge scenario)
        entity3 = Entity(
            id="test",
            version="v3",
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=["v2a", "v2b"]
        )
        assert entity3.parent_versions == ["v2a", "v2b"]
        assert len(entity3.parent_versions) == 2

    def test_entity_version_generation(self):
        """Test version string patterns."""
        # Simple versions
        versions = ["v1", "v2", "v3", "v10", "v100"]
        for version in versions:
            entity = Entity(
                id="test",
                version=version,
                entity_type=EntityType.DEVICE,
                name="Device",
                content={},
                source_type=SourceType.MANUAL,
                user_id="user"
            )
            assert entity.version == version

        # UUID versions
        uuid_version = str(uuid4())
        entity = Entity(
            id="test",
            version=uuid_version,
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user"
        )
        assert entity.version == uuid_version

        # Timestamp versions
        timestamp_version = datetime.now(timezone.utc).isoformat()
        entity = Entity(
            id="test",
            version=timestamp_version,
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user"
        )
        assert entity.version == timestamp_version
