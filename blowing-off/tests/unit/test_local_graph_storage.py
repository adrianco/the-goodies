"""
Unit tests for LocalGraphStorage.

Tests the local storage functionality for entities and relationships.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, UTC
import uuid

from blowingoff.graph.local_storage import LocalGraphStorage
from inbetweenies.models import Entity, EntityRelationship, EntityType, RelationshipType


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def storage(temp_storage_dir):
    """Create a LocalGraphStorage instance with temp directory."""
    return LocalGraphStorage(storage_dir=temp_storage_dir)


@pytest.fixture
def sample_entity():
    """Create a sample entity for testing."""
    return Entity(
        id=str(uuid.uuid4()),
        version=f"{datetime.now(UTC).isoformat()}Z-test",
        entity_type=EntityType.DEVICE,
        name="Test Device",
        content={"manufacturer": "Test Corp", "model": "T-1000"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        user_id="test-user"
    )


@pytest.fixture
def sample_room():
    """Create a sample room entity."""
    return Entity(
        id=str(uuid.uuid4()),
        version=f"{datetime.now(UTC).isoformat()}Z-test",
        entity_type=EntityType.ROOM,
        name="Living Room",
        content={"area": 30, "floor": 1},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        user_id="test-user"
    )


@pytest.fixture
def sample_relationship(sample_entity, sample_room):
    """Create a sample relationship."""
    return EntityRelationship(
        id=str(uuid.uuid4()),
        from_entity_id=sample_entity.id,
        from_entity_version=sample_entity.version,
        to_entity_id=sample_room.id,
        to_entity_version=sample_room.version,
        relationship_type=RelationshipType.LOCATED_IN,
        properties={"installed_date": "2024-01-01"},
        created_at=datetime.now(UTC),
        user_id="test-user"
    )


class TestLocalGraphStorage:
    """Test LocalGraphStorage functionality."""

    def test_store_and_retrieve_entity(self, storage, sample_entity):
        """Test storing and retrieving an entity."""
        # Store entity
        stored = storage.store_entity(sample_entity)
        assert stored.id == sample_entity.id
        assert stored.name == sample_entity.name

        # Retrieve entity
        retrieved = storage.get_entity(sample_entity.id)
        assert retrieved is not None
        assert retrieved.id == sample_entity.id
        assert retrieved.name == sample_entity.name
        assert retrieved.entity_type == sample_entity.entity_type

    def test_store_multiple_versions(self, storage, sample_entity):
        """Test storing multiple versions of the same entity."""
        # Store first version
        v1 = storage.store_entity(sample_entity)

        # Create and store second version
        v2 = Entity(
            id=sample_entity.id,
            version=f"{datetime.now(UTC).isoformat()}Z-test-v2",
            entity_type=sample_entity.entity_type,
            name="Updated Device",
            content={"manufacturer": "Test Corp", "model": "T-2000"},
            parent_versions=[v1.version],
            created_at=sample_entity.created_at,
            updated_at=datetime.now(UTC),
            user_id="test-user-2"
        )
        storage.store_entity(v2)

        # Get latest version (should be v2)
        latest = storage.get_entity(sample_entity.id)
        assert latest.name == "Updated Device"
        assert latest.version == v2.version

        # Get specific version
        specific = storage.get_entity(sample_entity.id, version=v1.version)
        assert specific.name == sample_entity.name
        assert specific.version == v1.version

    def test_get_entities_by_type(self, storage, sample_entity, sample_room):
        """Test retrieving entities by type."""
        # Store entities
        storage.store_entity(sample_entity)
        storage.store_entity(sample_room)

        # Get devices
        devices = storage.get_entities_by_type(EntityType.DEVICE)
        assert len(devices) == 1
        assert devices[0].id == sample_entity.id

        # Get rooms
        rooms = storage.get_entities_by_type(EntityType.ROOM)
        assert len(rooms) == 1
        assert rooms[0].id == sample_room.id

    def test_store_and_retrieve_relationship(self, storage, sample_entity, sample_room, sample_relationship):
        """Test storing and retrieving relationships."""
        # Store entities first
        storage.store_entity(sample_entity)
        storage.store_entity(sample_room)

        # Store relationship
        stored = storage.store_relationship(sample_relationship)
        assert stored.id == sample_relationship.id

        # Get relationships
        from_rels = storage.get_relationships(from_id=sample_entity.id)
        assert len(from_rels) == 1
        assert from_rels[0].to_entity_id == sample_room.id

        to_rels = storage.get_relationships(to_id=sample_room.id)
        assert len(to_rels) == 1
        assert to_rels[0].from_entity_id == sample_entity.id

        # Get by relationship type
        located_rels = storage.get_relationships(rel_type=RelationshipType.LOCATED_IN)
        assert len(located_rels) == 1

    def test_search_entities(self, storage, sample_entity, sample_room):
        """Test searching entities."""
        # Store entities
        storage.store_entity(sample_entity)
        storage.store_entity(sample_room)

        # Search by name
        results = storage.search_entities("Device")
        assert len(results) == 1
        assert results[0].id == sample_entity.id

        # Search with type filter
        results = storage.search_entities("Room", entity_types=[EntityType.ROOM])
        assert len(results) == 1
        assert results[0].id == sample_room.id

        # Search that matches multiple
        results = storage.search_entities("Test")
        assert len(results) == 1  # Only device has "Test" in name

    def test_get_devices_in_room(self, storage, sample_entity, sample_room, sample_relationship):
        """Test getting devices in a room."""
        # Store entities and relationship
        storage.store_entity(sample_entity)
        storage.store_entity(sample_room)
        storage.store_relationship(sample_relationship)

        # Get devices in room
        devices = storage.get_devices_in_room(sample_room.id)
        assert len(devices) == 1
        assert devices[0].id == sample_entity.id

    def test_clear_storage(self, storage, sample_entity):
        """Test clearing storage."""
        # Store entity
        storage.store_entity(sample_entity)
        assert len(storage._entities) == 1

        # Clear storage
        storage.clear()
        assert len(storage._entities) == 0
        assert len(storage._relationships) == 0

        # Verify entity is gone
        retrieved = storage.get_entity(sample_entity.id)
        assert retrieved is None

    def test_sync_from_server(self, storage, sample_entity, sample_room, sample_relationship):
        """Test syncing data from server."""
        # Sync entities and relationships
        storage.sync_from_server([sample_entity, sample_room], [sample_relationship])

        # Verify entities were stored
        assert storage.get_entity(sample_entity.id) is not None
        assert storage.get_entity(sample_room.id) is not None

        # Verify relationship was stored
        rels = storage.get_relationships(from_id=sample_entity.id)
        assert len(rels) == 1

    def test_get_statistics(self, storage, sample_entity, sample_room, sample_relationship):
        """Test getting graph statistics."""
        # Store entities and relationship
        storage.store_entity(sample_entity)
        storage.store_entity(sample_room)
        storage.store_relationship(sample_relationship)

        # Get statistics
        stats = storage.get_statistics()

        assert stats['total_entities'] == 2
        assert stats['total_relationships'] == 1
        assert stats['entity_types']['device'] == 1
        assert stats['entity_types']['room'] == 1
        assert stats['relationship_types']['located_in'] == 1
        assert stats['isolated_entities'] == 0
        assert stats['average_degree'] > 0

    def test_persistence(self, temp_storage_dir, sample_entity):
        """Test that data persists across storage instances."""
        # Create first storage instance and store entity
        storage1 = LocalGraphStorage(storage_dir=temp_storage_dir)
        storage1.store_entity(sample_entity)

        # Create second storage instance
        storage2 = LocalGraphStorage(storage_dir=temp_storage_dir)

        # Verify entity was loaded from disk
        retrieved = storage2.get_entity(sample_entity.id)
        assert retrieved is not None
        assert retrieved.name == sample_entity.name
