"""
Tests for sync functionality.

Tests version management, conflict resolution, and delta sync operations.
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from funkygibbon.sync.versioning import VersionManager, VersionTree
from funkygibbon.sync.conflict_resolution import ConflictResolver, ConflictStrategy
from funkygibbon.sync.delta import DeltaSyncEngine, SyncDelta, MerkleNode
from inbetweenies.models import Entity, EntityType, SourceType


@pytest.fixture
def sample_entity():
    """Create a sample entity for testing"""
    return Entity(
        id=str(uuid4()),
        version=Entity.create_version("test-user"),
        entity_type=EntityType.DEVICE,
        name="Test Device",
        content={"power": "on", "brightness": 50},
        source_type=SourceType.MANUAL,
        user_id="test-user",
        parent_versions=[]
    )


@pytest.fixture
def sample_entities():
    """Create multiple sample entities"""
    entities = []
    for i in range(5):
        entity = Entity(
            id=str(uuid4()),
            version=Entity.create_version(f"user-{i}"),
            entity_type=EntityType.DEVICE,
            name=f"Device {i}",
            content={"index": i},
            source_type=SourceType.MANUAL,
            user_id=f"user-{i}",
            parent_versions=[]
        )
        entities.append(entity)
    return entities


class TestVersionManager:
    """Test version management functionality"""
    
    @pytest.mark.asyncio
    async def test_create_version(self, async_session, sample_entity):
        """Test version creation"""
        version_manager = VersionManager(async_session)
        
        version = version_manager.create_version(sample_entity, [])
        
        assert version.endswith(f"Z-{sample_entity.user_id}")
        assert "T" in version  # ISO format timestamp
    
    @pytest.mark.asyncio
    async def test_merge_versions(self, async_session):
        """Test version merging"""
        version_manager = VersionManager(async_session)
        
        # Create two versions of same entity
        entity1 = Entity(
            id="test-id",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Device V1",
            content={"power": "on", "color": "red"},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=["v0"],
            created_at=datetime.now(timezone.utc) - timedelta(hours=2)
        )
        
        entity2 = Entity(
            id="test-id",
            version="v2",
            entity_type=EntityType.DEVICE,
            name="Device V2",
            content={"power": "off", "brightness": 75},
            source_type=SourceType.MANUAL,
            user_id="user2",
            parent_versions=["v0"],
            created_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        
        # Merge versions
        merged = version_manager.merge_versions([entity1, entity2])
        
        assert merged.id == "test-id"
        assert merged.name == "Device V2"  # Uses most recent name
        assert merged.content["power"] == "off"  # From entity2
        assert merged.content["brightness"] == 75  # From entity2
        assert merged.content["color"] == "red"  # Preserved from entity1
        assert "v1" in merged.parent_versions
        assert "v2" in merged.parent_versions
    
    def test_calculate_version_diff(self, async_session):
        """Test version difference calculation"""
        version_manager = VersionManager(async_session)
        
        old_entity = Entity(
            id="test-id",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Old Name",
            content={"a": 1, "b": 2, "c": 3},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=[]
        )
        
        new_entity = Entity(
            id="test-id",
            version="v2",
            entity_type=EntityType.DEVICE,
            name="New Name",
            content={"a": 1, "b": 5, "d": 4},  # b modified, c removed, d added
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=["v1"]
        )
        
        diff = version_manager.calculate_version_diff(old_entity, new_entity)
        
        assert diff["name_changed"] is True
        assert diff["name_change"]["from"] == "Old Name"
        assert diff["name_change"]["to"] == "New Name"
        assert diff["content_changes"]["b"]["type"] == "modified"
        assert diff["content_changes"]["b"]["old_value"] == 2
        assert diff["content_changes"]["b"]["new_value"] == 5
        assert diff["content_changes"]["c"]["type"] == "removed"
        assert diff["content_changes"]["d"]["type"] == "added"


class TestConflictResolver:
    """Test conflict resolution strategies"""
    
    def test_last_write_wins(self):
        """Test last-write-wins strategy"""
        resolver = ConflictResolver()
        
        local = Entity(
            id="test-id",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Local",
            content={"value": "local"},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=[],
            updated_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        
        remote = Entity(
            id="test-id",
            version="v2",
            entity_type=EntityType.DEVICE,
            name="Remote",
            content={"value": "remote"},
            source_type=SourceType.MANUAL,
            user_id="user2",
            parent_versions=[],
            updated_at=datetime.now(timezone.utc)
        )
        
        resolution = resolver.resolve_conflict(local, remote, ConflictStrategy.LAST_WRITE_WINS)
        
        assert resolution.resolved_entity == remote
        assert resolution.strategy == ConflictStrategy.LAST_WRITE_WINS
    
    def test_merge_strategy(self):
        """Test merge strategy"""
        resolver = ConflictResolver()
        
        local = Entity(
            id="test-id",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Device",
            content={"power": "on", "local_setting": True},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=["v0"],
            updated_at=datetime.now(timezone.utc)
        )
        
        remote = Entity(
            id="test-id",
            version="v2",
            entity_type=EntityType.DEVICE,
            name="Device",
            content={"power": "off", "remote_setting": True},
            source_type=SourceType.MANUAL,
            user_id="user2",
            parent_versions=["v0"],
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        
        resolution = resolver.resolve_conflict(local, remote, ConflictStrategy.MERGE)
        
        assert resolution.resolved_entity is not None
        assert resolution.strategy == ConflictStrategy.MERGE
        assert resolution.resolved_entity.content["local_setting"] is True
        assert resolution.resolved_entity.content["remote_setting"] is True
        assert resolution.resolved_entity.content["power"] == "on"  # Local wins on conflict
        assert len(resolution.resolved_entity.parent_versions) == 2
    
    def test_manual_strategy(self):
        """Test manual resolution strategy"""
        resolver = ConflictResolver()
        
        local = Entity(
            id="test-id",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Local",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=[]
        )
        
        remote = Entity(
            id="test-id",
            version="v2",
            entity_type=EntityType.DEVICE,
            name="Remote",
            content={},
            source_type=SourceType.MANUAL,
            user_id="user2",
            parent_versions=[]
        )
        
        resolution = resolver.resolve_conflict(local, remote, ConflictStrategy.MANUAL)
        
        assert resolution.resolved_entity is None
        assert resolution.requires_manual is True
        assert len(resolver.get_pending_resolutions()) == 1


class TestDeltaSyncEngine:
    """Test delta synchronization engine"""
    
    @pytest.mark.asyncio
    async def test_calculate_delta(self, async_session, sample_entities):
        """Test delta calculation"""
        delta_engine = DeltaSyncEngine(async_session)
        
        # Add entities to database
        for entity in sample_entities:
            async_session.add(entity)
        await async_session.commit()
        
        # Calculate delta from 1 hour ago
        last_sync = datetime.now(timezone.utc) - timedelta(hours=1)
        delta = await delta_engine.calculate_delta(last_sync)
        
        assert len(delta.added_entities) == 5
        assert len(delta.modified_entities) == 0
        assert delta.from_timestamp == last_sync
    
    def test_merkle_tree(self, sample_entities):
        """Test merkle tree creation and comparison"""
        # Create two merkle trees
        tree1 = MerkleNode()
        tree2 = MerkleNode()
        
        # Add same entities to both
        for entity in sample_entities[:3]:
            tree1.add_entity(entity)
            tree2.add_entity(entity)
        
        # Trees should have same hash
        assert tree1.calculate_hash() == tree2.calculate_hash()
        
        # Add different entity to tree1
        tree1.add_entity(sample_entities[3])
        
        # Now hashes should differ
        assert tree1.calculate_hash() != tree2.calculate_hash()
        
        # Find differences
        differences = tree1.find_differences(tree2)
        assert sample_entities[3].id in differences
    
    def test_sync_checksum(self, sample_entities):
        """Test sync checksum calculation"""
        delta_engine = DeltaSyncEngine(None)
        
        # Calculate checksum
        checksum1 = delta_engine.compute_sync_checksum(sample_entities)
        
        # Same entities should produce same checksum
        checksum2 = delta_engine.compute_sync_checksum(sample_entities)
        assert checksum1 == checksum2
        
        # Different order should still produce same checksum
        reversed_entities = list(reversed(sample_entities))
        checksum3 = delta_engine.compute_sync_checksum(reversed_entities)
        assert checksum1 == checksum3
        
        # Modified entity should produce different checksum
        modified_entities = sample_entities.copy()
        modified_entities[0].name = "Modified"
        checksum4 = delta_engine.compute_sync_checksum(modified_entities)
        assert checksum1 != checksum4


@pytest.mark.integration
class TestSyncIntegration:
    """Integration tests for complete sync flow"""
    
    @pytest.mark.asyncio
    async def test_full_sync_flow(self, async_session):
        """Test complete sync flow with conflicts"""
        version_manager = VersionManager(async_session)
        conflict_resolver = ConflictResolver()
        delta_engine = DeltaSyncEngine(async_session)
        
        # Create initial entity
        entity = Entity(
            id="sync-test",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Sync Test Device",
            content={"status": "initial"},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=[]
        )
        async_session.add(entity)
        await async_session.commit()
        
        # Simulate local modification
        local_entity = Entity(
            id="sync-test",
            version="v2-local",
            entity_type=EntityType.DEVICE,
            name="Local Update",
            content={"status": "local", "local_data": True},
            source_type=SourceType.MANUAL,
            user_id="user1",
            parent_versions=["v1"]
        )
        
        # Simulate remote modification
        remote_entity = Entity(
            id="sync-test",
            version="v2-remote",
            entity_type=EntityType.DEVICE,
            name="Remote Update",
            content={"status": "remote", "remote_data": True},
            source_type=SourceType.MANUAL,
            user_id="user2",
            parent_versions=["v1"]
        )
        
        # Resolve conflict with merge
        resolution = conflict_resolver.resolve_conflict(
            local_entity, remote_entity, ConflictStrategy.MERGE
        )
        
        assert resolution.resolved_entity is not None
        assert resolution.resolved_entity.content["local_data"] is True
        assert resolution.resolved_entity.content["remote_data"] is True
        assert len(resolution.resolved_entity.parent_versions) == 2