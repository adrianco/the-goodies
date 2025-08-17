"""
Unit tests for EntityRelationship model
"""

import pytest
from uuid import uuid4

from funkygibbon.models import (
    Entity, EntityType, SourceType,
    EntityRelationship, RelationshipType
)


class TestRelationshipModel:
    """Test EntityRelationship model functionality"""
    
    def create_test_entity(self, entity_type: EntityType, name: str) -> Entity:
        """Helper to create test entities"""
        return Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=entity_type,
            name=name,
            content={},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
    
    def test_relationship_creation(self):
        """Test creating a new relationship"""
        from_entity = self.create_test_entity(EntityType.DEVICE, "Smart Light")
        to_entity = self.create_test_entity(EntityType.ROOM, "Living Room")
        
        relationship = EntityRelationship(
            id=str(uuid4()),
            from_entity_id=from_entity.id,
            from_entity_version=from_entity.version,
            to_entity_id=to_entity.id,
            to_entity_version=to_entity.version,
            relationship_type=RelationshipType.LOCATED_IN,
            properties={"position": "ceiling"},
            user_id="test-user"
        )
        
        assert relationship.from_entity_id == from_entity.id
        assert relationship.to_entity_id == to_entity.id
        assert relationship.relationship_type == RelationshipType.LOCATED_IN
        assert relationship.properties["position"] == "ceiling"
    
    def test_relationship_to_dict(self):
        """Test converting relationship to dictionary"""
        rel_id = str(uuid4())
        relationship = EntityRelationship(
            id=rel_id,
            from_entity_id="entity1",
            from_entity_version="v1",
            to_entity_id="entity2",
            to_entity_version="v2",
            relationship_type=RelationshipType.CONTROLS,
            properties={"protocol": "zigbee"},
            user_id="user1"
        )
        
        rel_dict = relationship.to_dict()
        
        assert rel_dict["id"] == rel_id
        assert rel_dict["from_entity_id"] == "entity1"
        assert rel_dict["from_entity_version"] == "v1"
        assert rel_dict["to_entity_id"] == "entity2"
        assert rel_dict["to_entity_version"] == "v2"
        assert rel_dict["relationship_type"] == "controls"
        assert rel_dict["properties"]["protocol"] == "zigbee"
        assert rel_dict["user_id"] == "user1"
    
    def test_valid_relationship_located_in(self):
        """Test LOCATED_IN relationship validation"""
        device = self.create_test_entity(EntityType.DEVICE, "Device")
        room = self.create_test_entity(EntityType.ROOM, "Room")
        zone = self.create_test_entity(EntityType.ZONE, "Zone")
        home = self.create_test_entity(EntityType.HOME, "Home")
        
        # Valid relationships
        rel1 = EntityRelationship(
            from_entity_id=device.id,
            to_entity_id=room.id,
            relationship_type=RelationshipType.LOCATED_IN
        )
        assert rel1.is_valid_for_entities(device, room)
        
        rel2 = EntityRelationship(
            from_entity_id=room.id,
            to_entity_id=zone.id,
            relationship_type=RelationshipType.LOCATED_IN
        )
        assert rel2.is_valid_for_entities(room, zone)
        
        # Invalid relationship
        rel3 = EntityRelationship(
            from_entity_id=device.id,
            to_entity_id=device.id,
            relationship_type=RelationshipType.LOCATED_IN
        )
        assert not rel3.is_valid_for_entities(device, device)
    
    def test_valid_relationship_controls(self):
        """Test CONTROLS relationship validation"""
        device1 = self.create_test_entity(EntityType.DEVICE, "Switch")
        device2 = self.create_test_entity(EntityType.DEVICE, "Light")
        automation = self.create_test_entity(EntityType.AUTOMATION, "Auto1")
        
        # Valid relationships
        rel1 = EntityRelationship(
            from_entity_id=device1.id,
            to_entity_id=device2.id,
            relationship_type=RelationshipType.CONTROLS
        )
        assert rel1.is_valid_for_entities(device1, device2)
        
        rel2 = EntityRelationship(
            from_entity_id=automation.id,
            to_entity_id=device1.id,
            relationship_type=RelationshipType.CONTROLS
        )
        assert rel2.is_valid_for_entities(automation, device1)
        
        # Invalid relationship
        room = self.create_test_entity(EntityType.ROOM, "Room")
        rel3 = EntityRelationship(
            from_entity_id=room.id,
            to_entity_id=device1.id,
            relationship_type=RelationshipType.CONTROLS
        )
        assert not rel3.is_valid_for_entities(room, device1)
    
    def test_valid_relationship_connects_to(self):
        """Test CONNECTS_TO relationship validation"""
        room1 = self.create_test_entity(EntityType.ROOM, "Room1")
        room2 = self.create_test_entity(EntityType.ROOM, "Room2")
        door = self.create_test_entity(EntityType.DOOR, "Door")
        
        # Valid relationships
        rel1 = EntityRelationship(
            from_entity_id=room1.id,
            to_entity_id=room2.id,
            relationship_type=RelationshipType.CONNECTS_TO
        )
        assert rel1.is_valid_for_entities(room1, room2)
        
        rel2 = EntityRelationship(
            from_entity_id=door.id,
            to_entity_id=room1.id,
            relationship_type=RelationshipType.CONNECTS_TO
        )
        assert rel2.is_valid_for_entities(door, room1)
    
    def test_valid_relationship_documented_by(self):
        """Test DOCUMENTED_BY relationship validation"""
        device = self.create_test_entity(EntityType.DEVICE, "Device")
        manual = self.create_test_entity(EntityType.MANUAL, "Manual")
        procedure = self.create_test_entity(EntityType.PROCEDURE, "Procedure")
        
        # Valid relationships
        rel1 = EntityRelationship(
            from_entity_id=device.id,
            to_entity_id=manual.id,
            relationship_type=RelationshipType.DOCUMENTED_BY
        )
        assert rel1.is_valid_for_entities(device, manual)
        
        rel2 = EntityRelationship(
            from_entity_id=device.id,
            to_entity_id=procedure.id,
            relationship_type=RelationshipType.DOCUMENTED_BY
        )
        assert rel2.is_valid_for_entities(device, procedure)
    
    def test_relationship_types(self):
        """Test all relationship types are defined"""
        expected_types = [
            "located_in", "controls", "connects_to", "part_of",
            "manages", "documented_by", "procedure_for", "triggered_by",
            "depends_on", "contained_in", "monitors", "automates",
            "controlled_by_app", "has_blob"
        ]
        
        actual_types = [rt.value for rt in RelationshipType]
        assert set(actual_types) == set(expected_types)
    
    def test_relationship_repr(self):
        """Test relationship string representation"""
        relationship = EntityRelationship(
            id="rel-123",
            from_entity_id="entity1",
            from_entity_version="v1",
            to_entity_id="entity2",
            to_entity_version="v2",
            relationship_type=RelationshipType.CONTROLS,
            properties={},
            user_id="user1"
        )
        
        repr_str = repr(relationship)
        assert "rel-123" in repr_str
        assert "controls" in repr_str
        assert "entity1" in repr_str
        assert "entity2" in repr_str