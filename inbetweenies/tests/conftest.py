"""Test configuration and fixtures for Inbetweenies."""

import pytest
from datetime import datetime, timezone
from typing import List, Dict, Any
from uuid import uuid4

from inbetweenies.models import (
    Entity, EntityRelationship, EntityType, RelationshipType,
    SourceType
)


@pytest.fixture
def sample_entity():
    """Create a sample entity for testing."""
    return Entity(
        id="test-entity-1",
        version="v1",
        entity_type=EntityType.DEVICE,
        name="Test Device",
        content={"manufacturer": "TestCorp", "model": "T1000"},
        source_type=SourceType.MANUAL,
        user_id="test-user",
        parent_versions=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_entities():
    """Create multiple sample entities."""
    base_time = datetime.now(timezone.utc)

    return [
        Entity(
            id="home-1",
            version="v1",
            entity_type=EntityType.HOME,
            name="Test Home",
            content={"is_primary": True, "address": "123 Test St"},
            source_type=SourceType.MANUAL,
            user_id="user-1",
            parent_versions=[],
            created_at=base_time,
            updated_at=base_time
        ),
        Entity(
            id="room-1",
            version="v1",
            entity_type=EntityType.ROOM,
            name="Living Room",
            content={"floor": 1, "room_type": "living"},
            source_type=SourceType.HOMEKIT,
            user_id="user-1",
            parent_versions=[],
            created_at=base_time,
            updated_at=base_time
        ),
        Entity(
            id="device-1",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Smart Light",
            content={"manufacturer": "TestCorp", "brightness": 75},
            source_type=SourceType.HOMEKIT,
            user_id="user-1",
            parent_versions=[],
            created_at=base_time,
            updated_at=base_time
        ),
        Entity(
            id="automation-1",
            version="v1",
            entity_type=EntityType.AUTOMATION,
            name="Morning Routine",
            content={"enabled": True, "triggers": ["sunrise"]},
            source_type=SourceType.MANUAL,
            user_id="user-1",
            parent_versions=[],
            created_at=base_time,
            updated_at=base_time
        )
    ]


@pytest.fixture
def sample_relationship():
    """Create a sample relationship."""
    return EntityRelationship(
        id="rel-1",
        from_entity_id="device-1",
        from_entity_version="v1",
        to_entity_id="room-1",
        to_entity_version="v1",
        relationship_type=RelationshipType.LOCATED_IN,
        properties={"position": "ceiling"},
        user_id="test-user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_relationships():
    """Create multiple sample relationships."""
    base_time = datetime.now(timezone.utc)

    return [
        EntityRelationship(
            id="rel-1",
            from_entity_id="room-1",
            from_entity_version="v1",
            to_entity_id="home-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            user_id="user-1",
            created_at=base_time,
            updated_at=base_time
        ),
        EntityRelationship(
            id="rel-2",
            from_entity_id="device-1",
            from_entity_version="v1",
            to_entity_id="room-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={"position": "wall"},
            user_id="user-1",
            created_at=base_time,
            updated_at=base_time
        ),
        EntityRelationship(
            id="rel-3",
            from_entity_id="automation-1",
            from_entity_version="v1",
            to_entity_id="device-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.CONTROLS,
            properties={"action": "toggle"},
            user_id="user-1",
            created_at=base_time,
            updated_at=base_time
        )
    ]


@pytest.fixture
def conflict_scenarios():
    """Create various conflict scenarios for testing."""
    base_time = datetime.now(timezone.utc)

    # Same entity, different versions from different sources
    entity_v1 = Entity(
        id="conflict-entity",
        version="v1",
        entity_type=EntityType.DEVICE,
        name="Original Name",
        content={"value": 100},
        source_type=SourceType.MANUAL,
        user_id="user-1",
        parent_versions=[],
        created_at=base_time,
        updated_at=base_time
    )

    entity_v2_client = Entity(
        id="conflict-entity",
        version="v2-client",
        entity_type=EntityType.DEVICE,
        name="Client Update",
        content={"value": 200},
        source_type=SourceType.MANUAL,
        user_id="user-1",
        parent_versions=["v1"],
        created_at=base_time,
        updated_at=base_time
    )

    entity_v2_server = Entity(
        id="conflict-entity",
        version="v2-server",
        entity_type=EntityType.DEVICE,
        name="Server Update",
        content={"value": 150},
        source_type=SourceType.HOMEKIT,
        user_id="user-2",
        parent_versions=["v1"],
        created_at=base_time,
        updated_at=base_time
    )

    return {
        "base": entity_v1,
        "client_update": entity_v2_client,
        "server_update": entity_v2_server
    }


@pytest.fixture
def sync_messages():
    """Create sample sync protocol messages."""
    return {
        "pull_request": {
            "type": "pull",
            "client_id": "test-client",
            "last_sync": None,
            "entity_types": ["device", "room"]
        },
        "push_request": {
            "type": "push",
            "client_id": "test-client",
            "entities": [],
            "relationships": []
        },
        "conflict_resolution": {
            "type": "conflict_resolution",
            "strategy": "merge",
            "entity_id": "conflict-entity",
            "resolution": {}
        }
    }


@pytest.fixture
def mock_storage():
    """Create a mock storage implementation."""
    class MockStorage:
        def __init__(self):
            self.entities = {}
            self.relationships = {}

        def store_entity(self, entity: Entity):
            if entity.id not in self.entities:
                self.entities[entity.id] = []
            self.entities[entity.id].append(entity)

        def get_entity(self, entity_id: str, version: str = None):
            if entity_id not in self.entities:
                return None
            versions = self.entities[entity_id]
            if version:
                for entity in versions:
                    if entity.version == version:
                        return entity
                return None
            return versions[-1] if versions else None

        def get_all_entities(self):
            result = []
            for versions in self.entities.values():
                if versions:
                    result.append(versions[-1])
            return result

        def store_relationship(self, relationship: EntityRelationship):
            self.relationships[relationship.id] = relationship

        def get_relationships_for_entity(self, entity_id: str):
            result = []
            for rel in self.relationships.values():
                if rel.from_entity_id == entity_id or rel.to_entity_id == entity_id:
                    result.append(rel)
            return result

    return MockStorage()
