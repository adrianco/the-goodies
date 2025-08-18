"""
Unit tests for GraphIndex
"""

import pytest
from uuid import uuid4

from funkygibbon.models import (
    Entity, EntityType, SourceType,
    EntityRelationship, RelationshipType
)
from funkygibbon.graph.index import GraphIndex


class TestGraphIndex:
    """Test GraphIndex functionality"""

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

    def test_graph_index_initialization(self):
        """Test GraphIndex initialization"""
        index = GraphIndex()

        assert len(index.entities) == 0
        assert len(index.nodes) == 0
        assert len(index.relationships_by_source) == 0
        assert len(index.relationships_by_target) == 0
        assert len(index.entities_by_type) == 0

    def test_add_entity(self):
        """Test adding entities to the index"""
        index = GraphIndex()

        entity = self.create_test_entity(EntityType.DEVICE, "Test Device")
        index._add_entity(entity)

        assert entity.id in index.entities
        assert index.entities[entity.id] == entity
        assert entity.id in index.entities_by_type["device"]
        assert entity.id in index.entities_by_name["test device"]

    def test_add_relationship(self):
        """Test adding relationships to the index"""
        index = GraphIndex()

        # Create entities
        device = self.create_test_entity(EntityType.DEVICE, "Device")
        room = self.create_test_entity(EntityType.ROOM, "Room")

        index._add_entity(device)
        index._add_entity(room)

        # Create relationship
        rel = EntityRelationship(
            id=str(uuid4()),
            from_entity_id=device.id,
            from_entity_version=device.version,
            to_entity_id=room.id,
            to_entity_version=room.version,
            relationship_type=RelationshipType.LOCATED_IN,
            user_id="test-user"
        )

        index._add_relationship(rel)

        assert rel in index.relationships_by_source[device.id]
        assert rel in index.relationships_by_target[room.id]
        assert rel in index.relationships_by_type[RelationshipType.LOCATED_IN]

    def test_build_nodes(self):
        """Test building graph nodes"""
        index = GraphIndex()

        # Setup entities and relationships
        device1 = self.create_test_entity(EntityType.DEVICE, "Device 1")
        device2 = self.create_test_entity(EntityType.DEVICE, "Device 2")
        room = self.create_test_entity(EntityType.ROOM, "Room")

        index._add_entity(device1)
        index._add_entity(device2)
        index._add_entity(room)

        rel1 = EntityRelationship(
            from_entity_id=device1.id,
            to_entity_id=room.id,
            relationship_type=RelationshipType.LOCATED_IN
        )
        rel2 = EntityRelationship(
            from_entity_id=device1.id,
            to_entity_id=device2.id,
            relationship_type=RelationshipType.CONTROLS
        )

        index._add_relationship(rel1)
        index._add_relationship(rel2)

        # Build nodes
        index._build_nodes()

        # Check device1 node
        node = index.nodes[device1.id]
        assert node.entity == device1
        assert len(node.outgoing) == 2
        assert len(node.incoming) == 0

        # Check room node
        room_node = index.nodes[room.id]
        assert len(room_node.incoming) == 1
        assert len(room_node.outgoing) == 0

    def test_find_path_simple(self):
        """Test finding a simple path between entities"""
        index = GraphIndex()

        # Create chain: device -> room -> zone
        device = self.create_test_entity(EntityType.DEVICE, "Device")
        room = self.create_test_entity(EntityType.ROOM, "Room")
        zone = self.create_test_entity(EntityType.ZONE, "Zone")

        index._add_entity(device)
        index._add_entity(room)
        index._add_entity(zone)

        rel1 = EntityRelationship(
            from_entity_id=device.id,
            to_entity_id=room.id,
            relationship_type=RelationshipType.LOCATED_IN
        )
        rel2 = EntityRelationship(
            from_entity_id=room.id,
            to_entity_id=zone.id,
            relationship_type=RelationshipType.LOCATED_IN
        )

        index._add_relationship(rel1)
        index._add_relationship(rel2)
        index._build_nodes()

        # Find path
        path = index.find_path(device.id, zone.id)
        assert len(path) == 3
        assert path == [device.id, room.id, zone.id]

    def test_find_path_no_path(self):
        """Test finding path when no path exists"""
        index = GraphIndex()

        # Create disconnected entities
        entity1 = self.create_test_entity(EntityType.DEVICE, "Device 1")
        entity2 = self.create_test_entity(EntityType.DEVICE, "Device 2")

        index._add_entity(entity1)
        index._add_entity(entity2)
        index._build_nodes()

        path = index.find_path(entity1.id, entity2.id)
        assert len(path) == 0

    def test_find_path_max_depth(self):
        """Test path finding with max depth limit"""
        index = GraphIndex()

        # Create long chain
        entities = []
        for i in range(5):
            entity = self.create_test_entity(EntityType.ROOM, f"Room {i}")
            entities.append(entity)
            index._add_entity(entity)

        # Connect in chain
        for i in range(4):
            rel = EntityRelationship(
                from_entity_id=entities[i].id,
                to_entity_id=entities[i + 1].id,
                relationship_type=RelationshipType.CONNECTS_TO
            )
            index._add_relationship(rel)

        index._build_nodes()

        # Should find path within depth
        path = index.find_path(entities[0].id, entities[3].id, max_depth=5)
        assert len(path) == 4

        # Should not find path beyond max depth
        path = index.find_path(entities[0].id, entities[4].id, max_depth=2)
        assert len(path) == 0

    def test_get_connected_entities(self):
        """Test getting connected entities"""
        index = GraphIndex()

        # Create hub with connections
        hub = self.create_test_entity(EntityType.DEVICE, "Hub")
        device1 = self.create_test_entity(EntityType.DEVICE, "Device 1")
        device2 = self.create_test_entity(EntityType.DEVICE, "Device 2")
        room = self.create_test_entity(EntityType.ROOM, "Room")

        for entity in [hub, device1, device2, room]:
            index._add_entity(entity)

        # Create relationships
        rel1 = EntityRelationship(
            from_entity_id=hub.id,
            to_entity_id=device1.id,
            relationship_type=RelationshipType.CONTROLS
        )
        rel2 = EntityRelationship(
            from_entity_id=hub.id,
            to_entity_id=device2.id,
            relationship_type=RelationshipType.CONTROLS
        )
        rel3 = EntityRelationship(
            from_entity_id=hub.id,
            to_entity_id=room.id,
            relationship_type=RelationshipType.LOCATED_IN
        )

        for rel in [rel1, rel2, rel3]:
            index._add_relationship(rel)

        index._build_nodes()

        # Get all connected
        connected = index.get_connected_entities(hub.id)
        assert len(connected) == 3

        # Filter by relationship type
        controlled = index.get_connected_entities(
            hub.id,
            rel_type=RelationshipType.CONTROLS,
            direction="outgoing"
        )
        assert len(controlled) == 2
        assert all(c["relationship"].relationship_type == RelationshipType.CONTROLS
                  for c in controlled)

    def test_find_entities_by_name(self):
        """Test finding entities by name"""
        index = GraphIndex()

        # Add entities with similar names
        entities = [
            self.create_test_entity(EntityType.DEVICE, "Smart Light"),
            self.create_test_entity(EntityType.DEVICE, "Light Switch"),
            self.create_test_entity(EntityType.ROOM, "Lighting Control Room"),
            self.create_test_entity(EntityType.DEVICE, "Temperature Sensor")
        ]

        for entity in entities:
            index._add_entity(entity)

        # Fuzzy search
        results = index.find_entities_by_name("light", fuzzy=True)
        assert len(results) == 3
        assert all("light" in r.name.lower() for r in results)

        # Exact search
        exact = index.find_entities_by_name("smart light", fuzzy=False)
        assert len(exact) == 1
        assert exact[0].name == "Smart Light"

    def test_get_subgraph(self):
        """Test extracting a subgraph"""
        index = GraphIndex()

        # Create connected graph
        room1 = self.create_test_entity(EntityType.ROOM, "Room 1")
        room2 = self.create_test_entity(EntityType.ROOM, "Room 2")
        device1 = self.create_test_entity(EntityType.DEVICE, "Device 1")
        device2 = self.create_test_entity(EntityType.DEVICE, "Device 2")

        for entity in [room1, room2, device1, device2]:
            index._add_entity(entity)

        # Create relationships
        rel1 = EntityRelationship(
            from_entity_id=device1.id,
            to_entity_id=room1.id,
            relationship_type=RelationshipType.LOCATED_IN
        )
        rel2 = EntityRelationship(
            from_entity_id=device2.id,
            to_entity_id=room2.id,
            relationship_type=RelationshipType.LOCATED_IN
        )
        rel3 = EntityRelationship(
            from_entity_id=room1.id,
            to_entity_id=room2.id,
            relationship_type=RelationshipType.CONNECTS_TO
        )

        for rel in [rel1, rel2, rel3]:
            index._add_relationship(rel)

        # Extract subgraph with room1 and device1
        subgraph = index.get_subgraph({room1.id, device1.id})

        assert len(subgraph["entities"]) == 2
        assert room1.id in subgraph["entities"]
        assert device1.id in subgraph["entities"]
        assert len(subgraph["relationships"]) == 1  # Only rel1

    def test_calculate_centrality(self):
        """Test calculating entity centrality"""
        index = GraphIndex()

        # Create star topology
        center = self.create_test_entity(EntityType.DEVICE, "Hub")
        index._add_entity(center)

        # Add connected devices
        for i in range(5):
            device = self.create_test_entity(EntityType.DEVICE, f"Device {i}")
            index._add_entity(device)

            rel = EntityRelationship(
                from_entity_id=center.id,
                to_entity_id=device.id,
                relationship_type=RelationshipType.CONTROLS
            )
            index._add_relationship(rel)

        index._build_nodes()

        # Check centrality
        centrality = index.calculate_centrality(center.id)
        assert centrality["out_degree"] == 5
        assert centrality["in_degree"] == 0
        assert centrality["degree"] == 5

        # Check leaf node
        device_centrality = index.calculate_centrality(index.entities[list(index.entities.keys())[1]].id)
        assert device_centrality["in_degree"] == 1
        assert device_centrality["out_degree"] == 0

    def test_get_statistics(self):
        """Test getting graph statistics"""
        index = GraphIndex()

        # Add various entities
        for i in range(3):
            device = self.create_test_entity(EntityType.DEVICE, f"Device {i}")
            room = self.create_test_entity(EntityType.ROOM, f"Room {i}")
            index._add_entity(device)
            index._add_entity(room)

            if i > 0:
                rel = EntityRelationship(
                    from_entity_id=device.id,
                    to_entity_id=room.id,
                    relationship_type=RelationshipType.LOCATED_IN
                )
                index._add_relationship(rel)

        index._build_nodes()

        stats = index.get_statistics()

        assert stats["total_entities"] == 6
        assert stats["entity_types"]["device"] == 3
        assert stats["entity_types"]["room"] == 3
        assert stats["total_relationships"] == 2
        assert stats["relationship_types"]["located_in"] == 2
        assert stats["isolated_entities"] > 0
