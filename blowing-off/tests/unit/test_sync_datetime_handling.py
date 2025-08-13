"""Test datetime handling in sync process."""

import json
import pytest
from datetime import datetime, UTC
from pathlib import Path

from blowingoff.graph.local_storage import LocalGraphStorage
from inbetweenies.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType


class TestSyncDatetimeHandling:
    """Test that sync properly handles datetime fields."""
    
    def test_entity_to_dict_with_datetime(self, tmp_path):
        """Test _entity_to_dict with datetime objects."""
        storage = LocalGraphStorage(str(tmp_path / "test.db"))
        
        # Create entity with datetime objects
        entity = Entity(
            id="test-1",
            version="v1",
            entity_type=EntityType.HOME,
            name="Test Home",
            content={"test": True},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        # Set datetime attributes
        entity.created_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        entity.updated_at = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
        
        # Convert to dict
        result = storage._entity_to_dict(entity)
        
        # Check that timestamps are strings
        assert isinstance(result["created_at"], str)
        assert isinstance(result["updated_at"], str)
        assert result["created_at"] == "2025-01-01T10:00:00+00:00"
        assert result["updated_at"] == "2025-01-01T11:00:00+00:00"
    
    def test_entity_to_dict_with_string_timestamps(self, tmp_path):
        """Test _entity_to_dict with string timestamps (from sync)."""
        storage = LocalGraphStorage(str(tmp_path / "test.db"))
        
        # Create entity with string timestamps (as from sync)
        entity = Entity(
            id="test-1",
            version="v1",
            entity_type=EntityType.HOME,
            name="Test Home",
            content={"test": True},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        # Set string attributes (simulating data from sync)
        entity.created_at = "2025-01-01T10:00:00+00:00"
        entity.updated_at = "2025-01-01T11:00:00+00:00"
        
        # Convert to dict - should not raise error
        result = storage._entity_to_dict(entity)
        
        # Check that timestamps are still strings
        assert isinstance(result["created_at"], str)
        assert isinstance(result["updated_at"], str)
        assert result["created_at"] == "2025-01-01T10:00:00+00:00"
        assert result["updated_at"] == "2025-01-01T11:00:00+00:00"
    
    def test_entity_to_dict_with_no_timestamps(self, tmp_path):
        """Test _entity_to_dict with no timestamp attributes."""
        storage = LocalGraphStorage(str(tmp_path / "test.db"))
        
        # Create entity without timestamp attributes
        entity = Entity(
            id="test-1",
            version="v1",
            entity_type=EntityType.HOME,
            name="Test Home",
            content={"test": True},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        # Don't set created_at or updated_at
        
        # Convert to dict
        result = storage._entity_to_dict(entity)
        
        # Check that timestamps are None
        assert result["created_at"] is None
        assert result["updated_at"] is None
    
    def test_relationship_to_dict_with_datetime(self, tmp_path):
        """Test _relationship_to_dict with datetime objects."""
        storage = LocalGraphStorage(str(tmp_path / "test.db"))
        
        # Create relationship with datetime
        rel = EntityRelationship(
            id="rel-1",
            from_entity_id="entity-1",
            from_entity_version="v1",
            to_entity_id="entity-2",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            user_id="test-user"
        )
        rel.created_at = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        
        # Convert to dict
        result = storage._relationship_to_dict(rel)
        
        # Check that timestamp is string
        assert isinstance(result["created_at"], str)
        assert result["created_at"] == "2025-01-01T10:00:00+00:00"
    
    def test_relationship_to_dict_with_string_timestamp(self, tmp_path):
        """Test _relationship_to_dict with string timestamp."""
        storage = LocalGraphStorage(str(tmp_path / "test.db"))
        
        # Create relationship with string timestamp
        rel = EntityRelationship(
            id="rel-1",
            from_entity_id="entity-1",
            from_entity_version="v1",
            to_entity_id="entity-2",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            user_id="test-user"
        )
        rel.created_at = "2025-01-01T10:00:00+00:00"
        
        # Convert to dict - should not raise error
        result = storage._relationship_to_dict(rel)
        
        # Check that timestamp is still string
        assert isinstance(result["created_at"], str)
        assert result["created_at"] == "2025-01-01T10:00:00+00:00"
    
    def test_store_entity_with_mixed_timestamps(self, tmp_path):
        """Test storing entities with various timestamp formats."""
        storage = LocalGraphStorage(str(tmp_path / "test.db"))
        
        # Entity with datetime
        entity1 = Entity(
            id="test-1",
            version="v1",
            entity_type=EntityType.HOME,
            name="Test Home 1",
            content={},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        entity1.created_at = datetime.now(UTC)
        
        # Entity with string timestamp
        entity2 = Entity(
            id="test-2",
            version="v1",
            entity_type=EntityType.ROOM,
            name="Test Room",
            content={},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        entity2.created_at = "2025-01-01T10:00:00+00:00"
        
        # Entity with no timestamp
        entity3 = Entity(
            id="test-3",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Test Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        
        # Store all entities - should not raise errors
        storage.store_entity(entity1)
        storage.store_entity(entity2)
        storage.store_entity(entity3)
        
        # Verify they were stored
        assert storage.get_entity("test-1") is not None
        assert storage.get_entity("test-2") is not None
        assert storage.get_entity("test-3") is not None
        
        # Verify save doesn't raise errors
        storage._save_data()
        
        # Verify the saved files are valid JSON
        entities_file = Path(storage.entities_file)
        assert entities_file.exists()
        with open(entities_file) as f:
            data = json.load(f)
            assert "test-1" in data
            assert "test-2" in data
            assert "test-3" in data