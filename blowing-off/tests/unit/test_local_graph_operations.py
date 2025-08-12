"""
Unit tests for LocalGraphOperations and MCP tools.

Tests the local graph operations and MCP tool implementations.
"""

import pytest
import tempfile
import shutil
from datetime import datetime
import uuid

from blowingoff.graph.local_operations import LocalGraphOperations, SearchResult
from blowingoff.graph.local_storage import LocalGraphStorage
from inbetweenies.models import Entity, EntityRelationship, EntityType, RelationshipType
from inbetweenies.mcp import ToolResult


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def graph_ops(temp_storage_dir):
    """Create LocalGraphOperations with temp storage."""
    storage = LocalGraphStorage(storage_dir=temp_storage_dir)
    return LocalGraphOperations(storage)


@pytest.fixture
async def sample_room(graph_ops):
    """Create and store a sample room."""
    room = Entity(
        id=str(uuid.uuid4()),
        version=f"{datetime.utcnow().isoformat()}Z-test",
        entity_type=EntityType.ROOM,
        name="Living Room",
        content={"area": 30, "floor": 1},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        created_by="test-user",
        updated_by="test-user"
    )
    await graph_ops.store_entity(room)
    return room


@pytest.fixture
async def sample_device(graph_ops):
    """Create and store a sample device."""
    device = Entity(
        id=str(uuid.uuid4()),
        version=f"{datetime.utcnow().isoformat()}Z-test",
        entity_type=EntityType.DEVICE,
        name="Smart Light",
        content={
            "manufacturer": "Philips",
            "model": "Hue",
            "capabilities": ["on_off", "brightness", "color"]
        },
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        created_by="test-user",
        updated_by="test-user"
    )
    await graph_ops.store_entity(device)
    return device


@pytest.fixture
async def sample_automation(graph_ops):
    """Create and store a sample automation."""
    automation = Entity(
        id=str(uuid.uuid4()),
        version=f"{datetime.utcnow().isoformat()}Z-test",
        entity_type=EntityType.AUTOMATION,
        name="Evening Scene",
        content={"trigger": "sunset", "actions": ["dim_lights", "close_blinds"]},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        created_by="test-user",
        updated_by="test-user"
    )
    await graph_ops.store_entity(automation)
    return automation


class TestLocalGraphOperations:
    """Test LocalGraphOperations functionality."""
    
    @pytest.mark.asyncio
    async def test_store_and_get_entity(self, graph_ops):
        """Test storing and retrieving entities."""
        entity = Entity(
            id=str(uuid.uuid4()),
            version=f"{datetime.utcnow().isoformat()}Z-test",
            entity_type=EntityType.DEVICE,
            name="Test Device",
            content={"test": True},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by="test-user",
            updated_by="test-user"
        )
        
        # Store entity
        stored = await graph_ops.store_entity(entity)
        assert stored.id == entity.id
        
        # Get entity
        retrieved = await graph_ops.get_entity(entity.id)
        assert retrieved is not None
        assert retrieved.name == entity.name
    
    @pytest.mark.asyncio
    async def test_search_entities(self, graph_ops, sample_device, sample_room):
        """Test searching entities."""
        # Search for "Smart"
        results = await graph_ops.search_entities("Smart")
        assert len(results) == 1
        assert results[0].entity.id == sample_device.id
        assert results[0].score > 0
        
        # Search with type filter
        results = await graph_ops.search_entities("Room", entity_types=[EntityType.ROOM])
        assert len(results) == 1
        assert results[0].entity.id == sample_room.id
    
    @pytest.mark.asyncio
    async def test_find_path(self, graph_ops, sample_device, sample_room):
        """Test finding path between entities."""
        # Create relationship
        rel = EntityRelationship(
            id=str(uuid.uuid4()),
            from_entity_id=sample_device.id,
            from_entity_version=sample_device.version,
            to_entity_id=sample_room.id,
            to_entity_version=sample_room.version,
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            created_at=datetime.utcnow(),
            created_by="test-user"
        )
        await graph_ops.store_relationship(rel)
        
        # Find path
        path = await graph_ops.find_path(sample_device.id, sample_room.id)
        assert len(path) == 2
        assert path[0].id == sample_device.id
        assert path[1].id == sample_room.id


class TestMCPTools:
    """Test MCP tool implementations."""
    
    @pytest.mark.asyncio
    async def test_get_devices_in_room(self, graph_ops, sample_device, sample_room):
        """Test getting devices in a room."""
        # Create relationship
        rel = EntityRelationship(
            id=str(uuid.uuid4()),
            from_entity_id=sample_device.id,
            from_entity_version=sample_device.version,
            to_entity_id=sample_room.id,
            to_entity_version=sample_room.version,
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            created_at=datetime.utcnow(),
            created_by="test-user"
        )
        await graph_ops.store_relationship(rel)
        
        # Get devices in room
        result = await graph_ops.get_devices_in_room(sample_room.id)
        assert result.success
        assert result.result['count'] == 1
        assert len(result.result['devices']) == 1
        assert result.result['devices'][0]['id'] == sample_device.id
    
    @pytest.mark.asyncio
    async def test_find_device_controls(self, graph_ops, sample_device):
        """Test getting device controls."""
        result = await graph_ops.find_device_controls(sample_device.id)
        assert result.success
        assert result.result['device_id'] == sample_device.id
        assert result.result['device_name'] == sample_device.name
        assert "on_off" in result.result['capabilities']
        assert "brightness" in result.result['capabilities']
    
    @pytest.mark.asyncio
    async def test_search_entities_tool(self, graph_ops, sample_device, sample_room):
        """Test search entities MCP tool."""
        result = await graph_ops.search_entities_tool("Smart", limit=5)
        assert result.success
        assert result.result['count'] == 1
        assert result.result['query'] == "Smart"
        assert result.result['results'][0]['entity']['id'] == sample_device.id
    
    @pytest.mark.asyncio
    async def test_create_entity_tool(self, graph_ops):
        """Test creating entity via MCP tool."""
        result = await graph_ops.create_entity_tool(
            entity_type="device",
            name="New Device",
            content={"test": True},
            user_id="test-user"
        )
        assert result.success
        assert result.result['entity']['name'] == "New Device"
        
        # Verify entity was created
        entity_id = result.result['entity']['id']
        retrieved = await graph_ops.get_entity(entity_id)
        assert retrieved is not None
        assert retrieved.name == "New Device"
    
    @pytest.mark.asyncio
    async def test_create_relationship_tool(self, graph_ops, sample_device, sample_room):
        """Test creating relationship via MCP tool."""
        result = await graph_ops.create_relationship_tool(
            from_entity_id=sample_device.id,
            to_entity_id=sample_room.id,
            relationship_type="located_in",
            properties={"position": "ceiling"},
            user_id="test-user"
        )
        assert result.success
        assert result.result['relationship']['from_entity_id'] == sample_device.id
        assert result.result['relationship']['to_entity_id'] == sample_room.id
        
        # Verify relationship was created
        rels = await graph_ops.get_relationships(from_id=sample_device.id)
        assert len(rels) == 1
        assert rels[0].to_entity_id == sample_room.id
    
    @pytest.mark.asyncio
    async def test_find_path_tool(self, graph_ops, sample_device, sample_room):
        """Test finding path via MCP tool."""
        # Create relationship
        rel = EntityRelationship(
            id=str(uuid.uuid4()),
            from_entity_id=sample_device.id,
            from_entity_version=sample_device.version,
            to_entity_id=sample_room.id,
            to_entity_version=sample_room.version,
            relationship_type=RelationshipType.LOCATED_IN,
            properties={},
            created_at=datetime.utcnow(),
            created_by="test-user"
        )
        await graph_ops.store_relationship(rel)
        
        # Find path
        result = await graph_ops.find_path_tool(sample_device.id, sample_room.id)
        assert result.success
        assert result.result['found']
        assert result.result['length'] == 1
        assert len(result.result['path']) == 2
    
    @pytest.mark.asyncio
    async def test_get_entity_details_tool(self, graph_ops, sample_device):
        """Test getting entity details via MCP tool."""
        result = await graph_ops.get_entity_details_tool(sample_device.id)
        assert result.success
        assert result.result['entity']['id'] == sample_device.id
        assert result.result['entity']['name'] == sample_device.name
        assert 'outgoing_relationships' in result.result
        assert 'incoming_relationships' in result.result
    
    @pytest.mark.asyncio
    async def test_update_entity_tool(self, graph_ops, sample_device):
        """Test updating entity via MCP tool."""
        result = await graph_ops.update_entity_tool(
            entity_id=sample_device.id,
            changes={"name": "Updated Light", "content": {"brightness": 100}},
            user_id="test-user"
        )
        assert result.success
        assert result.result['entity']['name'] == "Updated Light"
        assert result.result['previous_version'] == sample_device.version
        
        # Verify new version was created
        updated = await graph_ops.get_entity(sample_device.id)
        assert updated.name == "Updated Light"
        assert updated.version != sample_device.version
    
    @pytest.mark.asyncio
    async def test_get_automations_in_room_tool(self, graph_ops, sample_room, sample_automation):
        """Test getting automations in room via MCP tool."""
        # Create relationship
        rel = EntityRelationship(
            id=str(uuid.uuid4()),
            from_entity_id=sample_automation.id,
            from_entity_version=sample_automation.version,
            to_entity_id=sample_room.id,
            to_entity_version=sample_room.version,
            relationship_type=RelationshipType.AUTOMATES,
            properties={},
            created_at=datetime.utcnow(),
            created_by="test-user"
        )
        await graph_ops.store_relationship(rel)
        
        # Get automations
        result = await graph_ops.get_automations_in_room_tool(sample_room.id)
        assert result.success
        assert result.result['count'] == 1
        assert result.result['automations'][0]['id'] == sample_automation.id
    
    @pytest.mark.asyncio
    async def test_find_similar_entities_tool(self, graph_ops, sample_device):
        """Test finding similar entities via MCP tool."""
        # Create another device
        similar_device = Entity(
            id=str(uuid.uuid4()),
            version=f"{datetime.utcnow().isoformat()}Z-test",
            entity_type=EntityType.DEVICE,
            name="Smart Bulb",
            content={"manufacturer": "LIFX"},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by="test-user",
            updated_by="test-user"
        )
        await graph_ops.store_entity(similar_device)
        
        # Find similar
        result = await graph_ops.find_similar_entities_tool(sample_device.id, limit=5)
        assert result.success
        assert result.result['count'] >= 1
        assert result.result['reference_entity_id'] == sample_device.id
        # Should find the other device
        entity_ids = [r['entity']['id'] for r in result.result['results']]
        assert similar_device.id in entity_ids


class TestSearchResult:
    """Test SearchResult functionality."""
    
    def test_search_result_to_dict(self):
        """Test converting SearchResult to dict."""
        entity = Entity(
            id=str(uuid.uuid4()),
            version=f"{datetime.utcnow().isoformat()}Z-test",
            entity_type=EntityType.DEVICE,
            name="Test Device",
            content={"test": True},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by="test-user",
            updated_by="test-user"
        )
        
        result = SearchResult(entity=entity, score=1.5)
        result_dict = result.to_dict()
        
        assert 'entity' in result_dict
        assert 'score' in result_dict
        assert result_dict['score'] == 1.5
        assert result_dict['entity']['id'] == entity.id
        assert result_dict['entity']['name'] == entity.name