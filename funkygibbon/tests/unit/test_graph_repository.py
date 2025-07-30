"""
Unit tests for GraphRepository
"""

import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.models import (
    Entity, EntityType, SourceType,
    EntityRelationship, RelationshipType
)
from funkygibbon.repositories.graph import GraphRepository


@pytest.mark.asyncio
class TestGraphRepository:
    """Test GraphRepository functionality"""
    
    async def test_store_entity(self, db_session: AsyncSession):
        """Test storing an entity"""
        repo = GraphRepository(db_session)
        
        entity = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.DEVICE,
            name="Test Device",
            content={"status": "active"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        
        stored = await repo.store_entity(entity)
        await db_session.commit()
        
        assert stored.id == entity.id
        assert stored.version == entity.version
        assert stored.name == entity.name
    
    async def test_get_entity_latest_version(self, db_session: AsyncSession):
        """Test getting the latest version of an entity"""
        repo = GraphRepository(db_session)
        
        entity_id = str(uuid4())
        
        # Store multiple versions
        v1 = Entity(
            id=entity_id,
            version=Entity.create_version("user1"),
            entity_type=EntityType.ROOM,
            name="Room v1",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=[]
        )
        await repo.store_entity(v1)
        
        v2 = Entity(
            id=entity_id,
            version=Entity.create_version("user2"),
            entity_type=EntityType.ROOM,
            name="Room v2",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user2",
            parent_versions=[v1.version]
        )
        await repo.store_entity(v2)
        await db_session.commit()
        
        # Get latest version
        latest = await repo.get_entity(entity_id)
        assert latest is not None
        assert latest.name == "Room v2"
        assert latest.version == v2.version
    
    async def test_get_entity_specific_version(self, db_session: AsyncSession):
        """Test getting a specific version of an entity"""
        repo = GraphRepository(db_session)
        
        entity = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.HOME,
            name="Test Home",
            content={},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )
        
        await repo.store_entity(entity)
        await db_session.commit()
        
        # Get specific version
        retrieved = await repo.get_entity(entity.id, entity.version)
        assert retrieved is not None
        assert retrieved.version == entity.version
        
        # Try non-existent version
        non_existent = await repo.get_entity(entity.id, "non-existent-version")
        assert non_existent is None
    
    async def test_get_entities_by_type(self, db_session: AsyncSession):
        """Test getting entities by type"""
        repo = GraphRepository(db_session)
        
        # Store different types
        device1 = Entity(
            id=str(uuid4()),
            version=Entity.create_version("user"),
            entity_type=EntityType.DEVICE,
            name="Device 1",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=[]
        )
        
        device2 = Entity(
            id=str(uuid4()),
            version=Entity.create_version("user"),
            entity_type=EntityType.DEVICE,
            name="Device 2",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=[]
        )
        
        room = Entity(
            id=str(uuid4()),
            version=Entity.create_version("user"),
            entity_type=EntityType.ROOM,
            name="Room",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=[]
        )
        
        await repo.store_entity(device1)
        await repo.store_entity(device2)
        await repo.store_entity(room)
        await db_session.commit()
        
        # Get only devices
        devices = await repo.get_entities_by_type(EntityType.DEVICE)
        assert len(devices) >= 2
        assert all(e.entity_type == EntityType.DEVICE for e in devices)
        
        # Get only rooms
        rooms = await repo.get_entities_by_type(EntityType.ROOM)
        assert any(r.id == room.id for r in rooms)
    
    async def test_store_relationship(self, db_session: AsyncSession):
        """Test storing a relationship"""
        repo = GraphRepository(db_session)
        
        # Create entities first
        device = Entity(
            id=str(uuid4()),
            version=Entity.create_version("user"),
            entity_type=EntityType.DEVICE,
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=[]
        )
        
        room = Entity(
            id=str(uuid4()),
            version=Entity.create_version("user"),
            entity_type=EntityType.ROOM,
            name="Room",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=[]
        )
        
        await repo.store_entity(device)
        await repo.store_entity(room)
        
        # Create relationship
        relationship = EntityRelationship(
            from_entity_id=device.id,
            from_entity_version=device.version,
            to_entity_id=room.id,
            to_entity_version=room.version,
            relationship_type=RelationshipType.LOCATED_IN,
            properties={"position": "wall"},
            user_id="user"
        )
        
        stored = await repo.store_relationship(relationship)
        await db_session.commit()
        
        assert stored.id is not None
        assert stored.from_entity_id == device.id
        assert stored.to_entity_id == room.id
    
    async def test_get_relationships_filters(self, db_session: AsyncSession):
        """Test getting relationships with filters"""
        repo = GraphRepository(db_session)
        
        # Create test entities
        device1 = Entity(
            id=str(uuid4()),
            version=Entity.create_version("user"),
            entity_type=EntityType.DEVICE,
            name="Device 1",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=[]
        )
        
        device2 = Entity(
            id=str(uuid4()),
            version=Entity.create_version("user"),
            entity_type=EntityType.DEVICE,
            name="Device 2",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=[]
        )
        
        room = Entity(
            id=str(uuid4()),
            version=Entity.create_version("user"),
            entity_type=EntityType.ROOM,
            name="Room",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user",
            parent_versions=[]
        )
        
        await repo.store_entity(device1)
        await repo.store_entity(device2)
        await repo.store_entity(room)
        
        # Create relationships
        rel1 = EntityRelationship(
            from_entity_id=device1.id,
            from_entity_version=device1.version,
            to_entity_id=room.id,
            to_entity_version=room.version,
            relationship_type=RelationshipType.LOCATED_IN,
            user_id="user"
        )
        
        rel2 = EntityRelationship(
            from_entity_id=device1.id,
            from_entity_version=device1.version,
            to_entity_id=device2.id,
            to_entity_version=device2.version,
            relationship_type=RelationshipType.CONTROLS,
            user_id="user"
        )
        
        await repo.store_relationship(rel1)
        await repo.store_relationship(rel2)
        await db_session.commit()
        
        # Test filters
        # By from_id
        from_device1 = await repo.get_relationships(from_id=device1.id)
        assert len(from_device1) == 2
        
        # By to_id
        to_room = await repo.get_relationships(to_id=room.id)
        assert len(to_room) == 1
        assert to_room[0].relationship_type == RelationshipType.LOCATED_IN
        
        # By relationship type
        controls = await repo.get_relationships(rel_type=RelationshipType.CONTROLS)
        assert any(r.id == rel2.id for r in controls)
    
    async def test_search_entities(self, db_session: AsyncSession):
        """Test searching entities"""
        repo = GraphRepository(db_session)
        
        # Create searchable entities
        entities = [
            Entity(
                id=str(uuid4()),
                version=Entity.create_version("user"),
                entity_type=EntityType.DEVICE,
                name="Smart Light Bulb",
                content={"manufacturer": "Philips"},
                source_type=SourceType.MANUAL,
                user_id="user",
                parent_versions=[]
            ),
            Entity(
                id=str(uuid4()),
                version=Entity.create_version("user"),
                entity_type=EntityType.DEVICE,
                name="Light Switch",
                content={"type": "dimmer"},
                source_type=SourceType.MANUAL,
                user_id="user",
                parent_versions=[]
            ),
            Entity(
                id=str(uuid4()),
                version=Entity.create_version("user"),
                entity_type=EntityType.ROOM,
                name="Living Room",
                content={"area": 30},
                source_type=SourceType.MANUAL,
                user_id="user",
                parent_versions=[]
            )
        ]
        
        for entity in entities:
            await repo.store_entity(entity)
        await db_session.commit()
        
        # Search by name
        results = await repo.search_entities("light")
        assert len(results) >= 2
        assert all("light" in r.name.lower() for r in results)
        
        # Search with type filter
        device_results = await repo.search_entities(
            "light",
            entity_types=[EntityType.DEVICE]
        )
        assert all(r.entity_type == EntityType.DEVICE for r in device_results)