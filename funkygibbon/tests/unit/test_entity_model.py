"""
Unit tests for Entity model
"""

import pytest
from datetime import datetime
from uuid import uuid4

from funkygibbon.models import Entity, EntityType, SourceType


class TestEntityModel:
    """Test Entity model functionality"""
    
    def test_entity_creation(self):
        """Test creating a new entity"""
        entity = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.DEVICE,
            name="Test Device",
            content={"manufacturer": "TestCorp", "model": "T-100"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        
        assert entity.entity_type == EntityType.DEVICE
        assert entity.name == "Test Device"
        assert entity.content["manufacturer"] == "TestCorp"
        assert entity.source_type == SourceType.MANUAL
        assert entity.user_id == "test-user"
        assert len(entity.parent_versions) == 0
    
    def test_version_generation(self):
        """Test version string generation"""
        version1 = Entity.create_version("user1")
        version2 = Entity.create_version("user1")
        
        # Versions should be unique
        assert version1 != version2
        
        # Version should contain user ID
        assert "user1" in version1
        assert "user1" in version2
        
        # Version should be ISO format with user suffix
        assert version1.endswith("-user1")
    
    def test_entity_to_dict(self):
        """Test converting entity to dictionary"""
        entity_id = str(uuid4())
        entity = Entity(
            id=entity_id,
            version=Entity.create_version("test-user"),
            entity_type=EntityType.ROOM,
            name="Living Room",
            content={"area": 25.5, "windows": 2},
            source_type=SourceType.HOMEKIT,
            user_id="test-user",
            parent_versions=["v1", "v2"]
        )
        
        entity_dict = entity.to_dict()
        
        assert entity_dict["id"] == entity_id
        assert entity_dict["entity_type"] == "room"
        assert entity_dict["name"] == "Living Room"
        assert entity_dict["content"]["area"] == 25.5
        assert entity_dict["source_type"] == "homekit"
        assert entity_dict["user_id"] == "test-user"
        assert entity_dict["parent_versions"] == ["v1", "v2"]
    
    def test_create_new_version(self):
        """Test creating a new version of an entity"""
        original = Entity(
            id=str(uuid4()),
            version=Entity.create_version("user1"),
            entity_type=EntityType.DEVICE,
            name="Smart Light",
            content={"brightness": 50, "color": "white"},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=[]
        )
        
        # Create new version with changes
        changes = {
            "name": "Smart Light v2",
            "content": {"brightness": 75, "temperature": 3000}
        }
        
        new_version = original.create_new_version("user2", changes)
        
        # Check new version properties
        assert new_version.id == original.id  # Same ID
        assert new_version.version != original.version  # Different version
        assert new_version.name == "Smart Light v2"
        assert new_version.user_id == "user2"
        
        # Check content merge
        assert new_version.content["brightness"] == 75
        assert new_version.content["temperature"] == 3000
        assert new_version.content["color"] == "white"  # Original property preserved
        
        # Check parent versions
        assert original.version in new_version.parent_versions
        assert len(new_version.parent_versions) == 1
    
    def test_entity_types(self):
        """Test all entity types are valid"""
        for entity_type in EntityType:
            entity = Entity(
                id=str(uuid4()),
                version=Entity.create_version("test"),
                entity_type=entity_type,
                name=f"Test {entity_type.value}",
                content={},
                source_type=SourceType.MANUAL,
                user_id="test",
                parent_versions=[]
            )
            assert entity.entity_type == entity_type
    
    def test_source_types(self):
        """Test all source types are valid"""
        for source_type in SourceType:
            entity = Entity(
                id=str(uuid4()),
                version=Entity.create_version("test"),
                entity_type=EntityType.DEVICE,
                name="Test Device",
                content={},
                source_type=source_type,
                user_id="test",
                parent_versions=[]
            )
            assert entity.source_type == source_type
    
    def test_entity_repr(self):
        """Test entity string representation"""
        entity = Entity(
            id="test-id-123",
            version="2025-07-30T12:00:00Z-user1",
            entity_type=EntityType.HOME,
            name="My Home",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=[]
        )
        
        repr_str = repr(entity)
        assert "test-id-123" in repr_str
        assert "HOME" in repr_str or "home" in repr_str.lower()
        assert "My Home" in repr_str
        assert "2025-07-" in repr_str  # First 8 chars of version