"""Basic integration tests for sync functionality."""

import pytest
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from inbetweenies.models import (
    Entity, EntityRelationship, EntityType, RelationshipType,
    SourceType
)
from inbetweenies.sync.conflict import ConflictResolver
from inbetweenies.sync.types import Change, Conflict, SyncOperation, SyncResult, SyncState


class TestSyncBasics:
    """Test basic sync functionality."""

    def test_entity_serialization(self):
        """Test entity can be serialized to dict."""
        entity = Entity(
            id="test-1",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Test Device",
            content={"manufacturer": "TestCorp"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        # Serialize
        entity_dict = entity.to_dict()

        # Verify dict contents
        assert entity_dict["id"] == entity.id
        assert entity_dict["version"] == entity.version
        assert entity_dict["entity_type"] == "device"
        assert entity_dict["name"] == entity.name
        assert entity_dict["content"] == entity.content

    def test_relationship_serialization(self):
        """Test relationship can be serialized to dict."""
        relationship = EntityRelationship(
            id="rel-1",
            from_entity_id="device-1",
            from_entity_version="v1",
            to_entity_id="room-1",
            to_entity_version="v1",
            relationship_type=RelationshipType.LOCATED_IN,
            properties={"position": "ceiling"},
            user_id="test-user",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        # Serialize
        rel_dict = relationship.to_dict()

        # Verify dict contents
        assert rel_dict["id"] == relationship.id
        assert rel_dict["from_entity_id"] == relationship.from_entity_id
        assert rel_dict["to_entity_id"] == relationship.to_entity_id
        assert rel_dict["relationship_type"] == "located_in"
        assert rel_dict["properties"] == relationship.properties

    def test_change_tracking(self):
        """Test Change object for tracking entity changes."""
        now = datetime.now(timezone.utc)

        change = Change(
            entity_type="device",
            entity_id="device-1",
            operation=SyncOperation.UPDATE,
            data={"name": "Updated Device", "content": {"value": 100}},
            updated_at=now,
            sync_id="sync-123",
            client_sync_id="client-456"
        )

        assert change.entity_type == "device"
        assert change.entity_id == "device-1"
        assert change.operation == SyncOperation.UPDATE
        assert change.data["name"] == "Updated Device"
        assert change.updated_at == now
        assert change.sync_id == "sync-123"
        assert change.client_sync_id == "client-456"

    def test_conflict_representation(self):
        """Test Conflict object for representing sync conflicts."""
        conflict = Conflict(
            entity_type="device",
            entity_id="device-1",
            reason="Both client and server modified",
            server_version={"name": "Server Device", "updated_at": "2025-01-01T10:00:00Z"},
            client_version={"name": "Client Device", "updated_at": "2025-01-01T09:00:00Z"},
            resolution="server_wins"
        )

        assert conflict.entity_type == "device"
        assert conflict.entity_id == "device-1"
        assert conflict.reason == "Both client and server modified"
        assert conflict.server_version["name"] == "Server Device"
        assert conflict.client_version["name"] == "Client Device"
        assert conflict.resolution == "server_wins"

    def test_sync_state_tracking(self):
        """Test SyncState for tracking sync progress."""
        last_sync = datetime.now(timezone.utc) - timedelta(hours=1)

        state = SyncState(
            last_sync=last_sync,
            pending_changes=[],
            sync_in_progress=False,
            failed_syncs=0,
            next_retry=None
        )

        assert state.last_sync == last_sync
        assert len(state.pending_changes) == 0
        assert state.sync_in_progress is False
        assert state.failed_syncs == 0
        assert state.next_retry is None

        # Add pending change
        change = Change(
            entity_type="device",
            entity_id="device-1",
            operation=SyncOperation.CREATE,
            data={},
            updated_at=datetime.now(timezone.utc),
            sync_id="sync-1"
        )
        state.pending_changes.append(change)

        assert len(state.pending_changes) == 1
        assert state.pending_changes[0].entity_id == "device-1"

    def test_sync_result(self):
        """Test SyncResult for tracking sync operation results."""
        conflict = Conflict(
            entity_type="device",
            entity_id="device-1",
            reason="conflict",
            server_version={},
            client_version={},
            resolution="merge"
        )

        result = SyncResult(
            success=True,
            synced_entities=10,
            conflicts_resolved=2,
            conflicts=[conflict],
            errors=[],
            duration=1.5,
            server_time=datetime.now(timezone.utc)
        )

        assert result.success is True
        assert result.synced_entities == 10
        assert result.conflicts_resolved == 2
        assert len(result.conflicts) == 1
        assert result.conflicts[0].entity_id == "device-1"
        assert len(result.errors) == 0
        assert result.duration == 1.5
        assert result.server_time is not None
        assert result.timestamp is not None

    def test_conflict_resolution_in_sync_flow(self):
        """Test conflict resolution as part of sync flow."""
        base_time = datetime.now(timezone.utc)

        # Client version
        client_entity = {
            "id": "device-1",
            "version": "v2-client",
            "entity_type": "device",
            "name": "Client Device",
            "content": {"value": 200},
            "updated_at": base_time - timedelta(minutes=5),
            "sync_id": "client-sync-1"
        }

        # Server version (newer)
        server_entity = {
            "id": "device-1",
            "version": "v2-server",
            "entity_type": "device",
            "name": "Server Device",
            "content": {"value": 150},
            "updated_at": base_time,
            "sync_id": "server-sync-1"
        }

        # Resolve conflict
        resolution = ConflictResolver.resolve(client_entity, server_entity)

        assert resolution.winner == server_entity
        assert resolution.loser == client_entity
        assert "remote has newer timestamp" in resolution.reason

        # Create conflict record
        conflict = Conflict(
            entity_type="device",
            entity_id="device-1",
            reason=resolution.reason,
            server_version=server_entity,
            client_version=client_entity,
            resolution="server_wins"
        )

        # Create sync result with conflict
        result = SyncResult(
            success=True,
            synced_entities=1,
            conflicts_resolved=1,
            conflicts=[conflict],
            errors=[],
            duration=0.5
        )

        assert result.conflicts_resolved == 1
        assert result.conflicts[0].resolution == "server_wins"

    def test_batch_entity_processing(self):
        """Test processing multiple entities in a batch."""
        entities = []
        base_time = datetime.now(timezone.utc)

        # Create batch of entities
        for i in range(10):
            entity = Entity(
                id=f"device-{i}",
                version="v1",
                entity_type=EntityType.DEVICE,
                name=f"Device {i}",
                content={"index": i},
                source_type=SourceType.MANUAL,
                user_id="batch-user",
                created_at=base_time,
                updated_at=base_time + timedelta(seconds=i)
            )
            entities.append(entity)

        # Serialize batch
        serialized = [e.to_dict() for e in entities]

        assert len(serialized) == 10

        # Verify batch serialization
        assert len(serialized) == 10

        # Verify order and content in serialized data
        for i, entity_dict in enumerate(serialized):
            assert entity_dict["id"] == f"device-{i}"
            assert entity_dict["content"]["index"] == i

    def test_relationship_batch_processing(self):
        """Test processing multiple relationships in a batch."""
        relationships = []
        base_time = datetime.now(timezone.utc)

        # Create batch of relationships
        for i in range(5):
            rel = EntityRelationship(
                id=f"rel-{i}",
                from_entity_id=f"device-{i}",
                from_entity_version="v1",
                to_entity_id=f"room-{i}",
                to_entity_version="v1",
                relationship_type=RelationshipType.LOCATED_IN,
                properties={"index": i},
                user_id="batch-user",
                created_at=base_time,
                updated_at=base_time
            )
            relationships.append(rel)

        # Serialize batch
        serialized = [r.to_dict() for r in relationships]

        assert len(serialized) == 5

        # Verify batch serialization
        assert len(serialized) == 5

        # Verify content in serialized data
        for i, rel_dict in enumerate(serialized):
            assert rel_dict["id"] == f"rel-{i}"
            assert rel_dict["from_entity_id"] == f"device-{i}"
            assert rel_dict["to_entity_id"] == f"room-{i}"
            assert rel_dict["properties"]["index"] == i
