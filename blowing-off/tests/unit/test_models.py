"""Unit tests for Blowing-Off models."""

import pytest
from datetime import datetime, UTC

from blowingoff.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType, SyncMetadata


class TestModels:
    """Test model functionality."""

    def test_entity_creation(self):
        """Test creating an entity."""
        entity = Entity(
            id="entity-1",
            entity_type=EntityType.HOME,
            name="Test Home",
            content={"is_primary": True},
            source_type=SourceType.MANUAL,
            user_id="user-1"
        )

        assert entity.id == "entity-1"
        assert entity.name == "Test Home"
        assert entity.entity_type == EntityType.HOME
        assert entity.content["is_primary"] == True

    def test_room_entity_creation(self):
        """Test creating a room entity."""
        room = Entity(
            id="room-1",
            entity_type=EntityType.ROOM,
            name="Living Room",
            content={"floor": 1},
            source_type=SourceType.MANUAL,
            user_id="user-1"
        )

        assert room.id == "room-1"
        assert room.entity_type == EntityType.ROOM
        assert room.name == "Living Room"

    def test_sync_metadata(self):
        """Test sync metadata."""
        metadata = SyncMetadata(
            client_id="client-1",
            last_sync_time=datetime.now(UTC),
            server_url="http://localhost:8000"
        )

        assert metadata.client_id == "client-1"
        assert metadata.last_sync_time is not None
        assert metadata.server_url == "http://localhost:8000"
        assert metadata.sync_failures == 0
        assert metadata.total_syncs == 0

    def test_to_dict(self):
        """Test converting entity to dictionary."""
        entity = Entity(
            id="entity-1",
            entity_type=EntityType.HOME,
            name="Test Home",
            content={"is_primary": True},
            source_type=SourceType.MANUAL,
            user_id="user-1",
            version="v1"
        )

        entity_dict = entity.to_dict()

        assert entity_dict["id"] == "entity-1"
        assert entity_dict["name"] == "Test Home"
        assert entity_dict["entity_type"] == "home"
        assert entity_dict["content"]["is_primary"] == True
        assert entity_dict["source_type"] == "manual"
