import pytest
from datetime import datetime
import json
from funkygibbon.core.models import (
    HomeEntity, EntityType, SourceType, RelationshipType,
    EntityRelationship, InbetweeniesRequest, InbetweeniesResponse
)


class TestHomeEntity:
    """Test suite for HomeEntity model"""
    
    def test_basic_entity_creation(self):
        """Test creating entity with minimal required fields"""
        # Arrange & Act
        entity = HomeEntity(
            entity_type=EntityType.ROOM,
            content={"name": "Living Room"},
            user_id="test-user"
        )
        
        # Assert
        assert entity.entity_type == EntityType.ROOM
        assert entity.content["name"] == "Living Room"
        assert entity.user_id == "test-user"
        assert entity.source_type == SourceType.MANUAL
        assert entity.id is not None
        assert entity.version is not None
        assert isinstance(entity.created_at, datetime)
        assert isinstance(entity.last_modified, datetime)
        assert entity.parent_versions == []
    
    def test_entity_with_all_fields(self):
        """Test creating entity with all fields specified"""
        # Arrange
        entity_id = "custom-id-123"
        version = "2024-01-01T00:00:00Z-user"
        parent_versions = ["parent-v1", "parent-v2"]
        content = {
            "name": "Smart Thermostat",
            "brand": "Nest",
            "temperature": 72.5,
            "is_online": True
        }
        
        # Act
        entity = HomeEntity(
            id=entity_id,
            version=version,
            entity_type=EntityType.DEVICE,
            parent_versions=parent_versions,
            content=content,
            user_id="user-123",
            source_type=SourceType.HOMEKIT
        )
        
        # Assert
        assert entity.id == entity_id
        assert entity.version == version
        assert entity.parent_versions == parent_versions
        assert entity.content["temperature"] == 72.5
        assert entity.content["is_online"] is True
        assert entity.source_type == SourceType.HOMEKIT
    
    @pytest.mark.parametrize("entity_type", list(EntityType))
    def test_all_entity_types(self, entity_type):
        """Test entity creation with each entity type"""
        entity = HomeEntity(
            entity_type=entity_type,
            content={"type_test": entity_type.value},
            user_id="test-user"
        )
        
        assert entity.entity_type == entity_type
        assert entity.content["type_test"] == entity_type.value
    
    def test_entity_json_serialization(self):
        """Test JSON serialization and deserialization"""
        # Arrange
        entity = HomeEntity(
            entity_type=EntityType.DEVICE,
            content={
                "name": "Test Device",
                "nested": {"level1": {"level2": "value"}}
            },
            user_id="test-user"
        )
        
        # Act
        json_str = entity.model_dump_json()
        parsed = HomeEntity.model_validate_json(json_str)
        
        # Assert
        assert parsed.id == entity.id
        assert parsed.entity_type == entity.entity_type
        assert parsed.content == entity.content
        assert parsed.user_id == entity.user_id
        # Timestamps should be close but might differ slightly
        assert abs((parsed.created_at - entity.created_at).total_seconds()) < 1
    
    def test_entity_dict_conversion(self):
        """Test conversion to and from dictionary"""
        # Arrange
        entity = HomeEntity(
            entity_type=EntityType.ROOM,
            content={"name": "Bedroom", "area": 200},
            user_id="test-user"
        )
        
        # Act
        entity_dict = entity.model_dump()
        reconstructed = HomeEntity(**entity_dict)
        
        # Assert
        assert reconstructed.id == entity.id
        assert reconstructed.content == entity.content
        assert entity_dict["entity_type"] == "room"
        assert "created_at" in entity_dict
        assert "last_modified" in entity_dict
    
    def test_entity_validation_errors(self):
        """Test validation errors for invalid data"""
        # Missing required field
        with pytest.raises(ValueError):
            HomeEntity(
                entity_type=EntityType.DEVICE,
                content={"name": "Device"}
                # Missing user_id
            )
        
        # Invalid entity type
        with pytest.raises(ValueError):
            HomeEntity(
                entity_type="invalid_type",  # type: ignore
                content={},
                user_id="user"
            )
    
    def test_entity_version_format(self):
        """Test that version follows expected format"""
        entity = HomeEntity(
            entity_type=EntityType.DEVICE,
            content={},
            user_id="test-user"
        )
        
        # Version should contain ISO timestamp and user
        assert "T" in entity.version  # ISO format
        assert "Z" in entity.version  # UTC timezone
        assert "-" in entity.version  # Separator
    
    def test_entity_id_uniqueness(self):
        """Test that generated IDs are unique"""
        entities = [
            HomeEntity(
                entity_type=EntityType.DEVICE,
                content={"index": i},
                user_id="user"
            )
            for i in range(10)
        ]
        
        ids = [e.id for e in entities]
        assert len(ids) == len(set(ids))  # All IDs should be unique


class TestEntityRelationship:
    """Test suite for EntityRelationship model"""
    
    def test_basic_relationship_creation(self):
        """Test creating relationship with minimal fields"""
        # Arrange & Act
        relationship = EntityRelationship(
            from_entity_id="entity-1",
            to_entity_id="entity-2",
            relationship_type=RelationshipType.LOCATED_IN,
            user_id="test-user"
        )
        
        # Assert
        assert relationship.from_entity_id == "entity-1"
        assert relationship.to_entity_id == "entity-2"
        assert relationship.relationship_type == RelationshipType.LOCATED_IN
        assert relationship.user_id == "test-user"
        assert relationship.id is not None
        assert relationship.properties == {}
        assert isinstance(relationship.created_at, datetime)
    
    def test_relationship_with_properties(self):
        """Test creating relationship with custom properties"""
        # Arrange
        properties = {
            "distance": 5.5,
            "direction": "north",
            "accessible": True
        }
        
        # Act
        relationship = EntityRelationship(
            from_entity_id="room-1",
            to_entity_id="room-2",
            relationship_type=RelationshipType.CONNECTS_TO,
            properties=properties,
            user_id="test-user"
        )
        
        # Assert
        assert relationship.properties == properties
        assert relationship.properties["distance"] == 5.5
        assert relationship.properties["accessible"] is True
    
    @pytest.mark.parametrize("rel_type", list(RelationshipType))
    def test_all_relationship_types(self, rel_type):
        """Test all relationship types"""
        relationship = EntityRelationship(
            from_entity_id="from",
            to_entity_id="to",
            relationship_type=rel_type,
            user_id="user"
        )
        
        assert relationship.relationship_type == rel_type
    
    def test_relationship_serialization(self):
        """Test JSON serialization of relationships"""
        # Arrange
        relationship = EntityRelationship(
            from_entity_id="device-1",
            to_entity_id="room-1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={"floor": 2, "zone": "north"},
            user_id="user"
        )
        
        # Act
        json_str = relationship.model_dump_json()
        parsed = EntityRelationship.model_validate_json(json_str)
        
        # Assert
        assert parsed.from_entity_id == relationship.from_entity_id
        assert parsed.to_entity_id == relationship.to_entity_id
        assert parsed.properties == relationship.properties


class TestInbetweeniesModels:
    """Test suite for Inbetweenies protocol models"""
    
    def test_inbetweenies_request_creation(self):
        """Test creating Inbetweenies sync request"""
        # Arrange
        changes = [
            {
                "change_type": "create",
                "entity_id": "new-entity",
                "entity_version": "v1",
                "entity_type": "device",
                "content": {"name": "New Device"},
                "timestamp": "2024-01-01T00:00:00Z"
            }
        ]
        vector_clock = {"client": "100", "server": "50"}
        
        # Act
        request = InbetweeniesRequest(
            device_id="test-device",
            user_id="test-user",
            vector_clock=vector_clock,
            changes=changes
        )
        
        # Assert
        assert request.protocol_version == "inbetweenies-v1"
        assert request.device_id == "test-device"
        assert request.user_id == "test-user"
        assert request.vector_clock == vector_clock
        assert len(request.changes) == 1
        assert request.changes[0]["change_type"] == "create"
    
    def test_inbetweenies_response_creation(self):
        """Test creating Inbetweenies sync response"""
        # Arrange
        changes = [
            {
                "change_type": "update",
                "entity_id": "existing-entity",
                "entity_version": "v2",
                "content": {"updated": True}
            }
        ]
        vector_clock = {"server": "101", "client": "100"}
        conflicts = ["conflict-1", "conflict-2"]
        
        # Act
        response = InbetweeniesResponse(
            changes=changes,
            vector_clock=vector_clock,
            conflicts=conflicts
        )
        
        # Assert
        assert len(response.changes) == 1
        assert response.vector_clock == vector_clock
        assert response.conflicts == conflicts
    
    def test_empty_inbetweenies_response(self):
        """Test response with no changes or conflicts"""
        response = InbetweeniesResponse(
            changes=[],
            vector_clock={"server": "0"}
        )
        
        assert response.changes == []
        assert response.conflicts == []
        assert response.vector_clock == {"server": "0"}


class TestModelPerformance:
    """Performance tests for models"""
    
    def test_entity_creation_performance(self, benchmark):
        """Benchmark entity creation"""
        def create_entity():
            return HomeEntity(
                entity_type=EntityType.DEVICE,
                content={"name": "Test", "value": 123},
                user_id="perf-test"
            )
        
        result = benchmark(create_entity)
        assert result is not None
    
    def test_serialization_performance(self, benchmark):
        """Benchmark JSON serialization"""
        entity = HomeEntity(
            entity_type=EntityType.ROOM,
            content={
                "name": "Complex Room",
                "devices": list(range(100)),
                "metadata": {f"key_{i}": f"value_{i}" for i in range(50)}
            },
            user_id="perf-test"
        )
        
        def serialize():
            return entity.model_dump_json()
        
        result = benchmark(serialize)
        assert len(result) > 0
    
    def test_bulk_entity_validation(self, benchmark):
        """Benchmark bulk entity validation"""
        entities_data = [
            {
                "entity_type": EntityType.DEVICE,
                "content": {"index": i},
                "user_id": "bulk-test"
            }
            for i in range(100)
        ]
        
        def validate_all():
            return [HomeEntity(**data) for data in entities_data]
        
        result = benchmark(validate_all)
        assert len(result) == 100