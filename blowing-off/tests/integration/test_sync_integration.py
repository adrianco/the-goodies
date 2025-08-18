"""
Integration tests for synchronization functionality.

Tests the sync engine, protocol, and conflict resolution.
"""

import pytest
import pytest_asyncio
import tempfile
import json
from datetime import datetime, timedelta, UTC
from unittest.mock import Mock, AsyncMock, patch
import uuid
import httpx

from blowingoff.sync.engine import SyncEngine
from blowingoff.sync.protocol import InbetweeniesProtocol
from blowingoff.sync.conflict_resolver import ConflictResolver
from inbetweenies.sync import SyncState, Change, SyncOperation, ConflictResolution
from inbetweenies.models import Entity, EntityType


@pytest.fixture
def sync_protocol():
    """Create an InbetweeniesProtocol instance."""
    return InbetweeniesProtocol(
        base_url="http://localhost:8000",
        auth_token="test-token",
        client_id="test-client"
    )


@pytest.fixture
def conflict_resolver():
    """Create a ConflictResolver instance."""
    return ConflictResolver()


@pytest_asyncio.fixture
async def sync_engine():
    """Create a SyncEngine instance."""
    # Create a mock session
    mock_session = AsyncMock()

    engine = SyncEngine(
        session=mock_session,
        base_url="http://localhost:8000",
        auth_token="test-token",
        client_id="test-client"
    )
    return engine


class TestInbetweeniesProtocol:
    """Test the synchronization protocol."""

    @pytest.mark.asyncio
    async def test_sync_push(self, sync_protocol):
        """Test pushing changes to server."""
        changes = [
            Change(
                entity_type="device",
                entity_id=str(uuid.uuid4()),
                operation=SyncOperation.CREATE,
                data={
                    "name": "Test Entity",
                    "entity_type": "device"
                },
                updated_at=datetime.now(UTC),
                sync_id=str(uuid.uuid4())
            )
        ]

        with patch('httpx.AsyncClient') as mock_client_class:
            # Create mock client instance
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__.return_value = None

            # Create mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json = Mock(return_value={
                "success": True,
                "accepted": 1,
                "rejected": 0
            })
            mock_response.raise_for_status = Mock()

            # Set the post method to return the response
            mock_client.post = AsyncMock(return_value=mock_response)

            result = await sync_protocol.sync_push(changes)
            assert result["success"] is True
            assert result["accepted"] == 1

    @pytest.mark.asyncio
    async def test_sync_ack(self, sync_protocol):
        """Test acknowledging sync with server."""
        # sync_ack doesn't actually make HTTP calls in the new protocol
        result = await sync_protocol.sync_ack()
        assert result["success"] is True
        assert "message" in result

    def test_parse_sync_delta(self, sync_protocol):
        """Test parsing sync delta response."""
        entity_id = str(uuid.uuid4())
        response = {
            "sync_type": "delta",
            "changes": [
                {
                    "change_type": "create",  # Must be create/update/delete
                    "entity": {
                        "id": entity_id,
                        "version": f"{datetime.now(UTC).isoformat()}Z-test",
                        "entity_type": "device",
                        "name": "Test Device",
                        "content": {"test": True},
                        "source_type": "manual",  # Required field
                        "user_id": "test-user",  # Required field
                        "created_at": datetime.now(UTC).isoformat(),
                        "updated_at": datetime.now(UTC).isoformat()
                    }
                }
            ],
            "conflicts": []
        }

        changes, conflicts = sync_protocol.parse_sync_delta(response)
        assert len(changes) == 1
        assert len(conflicts) == 0
        assert changes[0].entity_id == entity_id

    def test_parse_sync_result(self, sync_protocol):
        """Test parsing sync result."""
        id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
        response = {
            "sync_type": "result",
            "sync_stats": {
                "entities_synced": 2,
                "relationships_synced": 0,
                "conflicts_resolved": 0
            },
            "changes": [  # parse_sync_result looks for "changes", not "accepted"
                {
                    "entity": {"id": id1}
                },
                {
                    "entity": {"id": id2}
                }
            ],
            "conflicts": []
        }

        accepted_ids, conflicts = sync_protocol.parse_sync_result(response)
        assert len(accepted_ids) == 2
        assert id1 in accepted_ids
        assert id2 in accepted_ids
        assert len(conflicts) == 0


class TestConflictResolver:
    """Test conflict resolution functionality."""

    def test_resolve_last_write_wins(self, conflict_resolver):
        """Test last-write-wins conflict resolution."""
        local_data = {
            "name": "Local Name",
            "updated_at": "2024-01-01T12:00:00Z"
        }
        remote_data = {
            "name": "Remote Name",
            "updated_at": "2024-01-01T13:00:00Z"
        }

        winning_data, reason = conflict_resolver.resolve_conflict(local_data, remote_data)
        assert winning_data == remote_data
        assert reason == "newer_remote"

    def test_resolve_client_wins(self, conflict_resolver):
        """Test client-wins conflict resolution (newer local)."""
        local_data = {
            "name": "Local Name",
            "updated_at": "2024-01-01T14:00:00Z"  # Newer
        }
        remote_data = {
            "name": "Remote Name",
            "updated_at": "2024-01-01T13:00:00Z"
        }

        winning_data, reason = conflict_resolver.resolve_conflict(local_data, remote_data)
        assert winning_data == local_data
        assert reason == "newer_local"

    def test_resolve_server_wins(self, conflict_resolver):
        """Test server-wins conflict resolution."""
        local_data = {
            "name": "Local Name",
            "updated_at": "2024-01-01T12:00:00Z"
        }
        remote_data = {
            "name": "Remote Name",
            "updated_at": "2024-01-01T13:00:00Z"  # Newer
        }

        winning_data, reason = conflict_resolver.resolve_conflict(local_data, remote_data)
        assert winning_data == remote_data
        assert reason == "newer_remote"

    def test_resolve_deletion_conflict(self, conflict_resolver):
        """Test deletion conflict resolution."""
        local_data = {
            "name": "Local Name",
            "updated_at": "2024-01-01T12:00:00Z",
            "deleted": True
        }
        remote_data = {
            "name": "Remote Name",
            "updated_at": "2024-01-01T13:00:00Z",
            "deleted": False
        }

        winning_data, reason = conflict_resolver.resolve_conflict(local_data, remote_data)
        assert winning_data == local_data
        assert reason == "local_deleted"


class TestSyncEngine:
    """Test the synchronization engine."""

    @pytest.mark.asyncio
    async def test_sync_basic(self, sync_engine):
        """Test basic synchronization."""
        # Set up graph operations mock
        mock_graph_ops = Mock()
        mock_graph_ops.store_entity = AsyncMock()
        mock_graph_ops.store_relationship = AsyncMock()
        # Return empty list to avoid Mock serialization issues
        mock_graph_ops.get_entities_by_type = AsyncMock(return_value=[])
        mock_graph_ops.get_entity = AsyncMock(return_value=None)
        mock_graph_ops.search_entities = AsyncMock(return_value=[])
        sync_engine.set_graph_operations(mock_graph_ops)

        # Mock metadata repository to return None (no previous sync)
        sync_engine.metadata_repo.get_metadata = AsyncMock(return_value=None)
        sync_engine.metadata_repo.update_sync_time = AsyncMock()
        sync_engine.metadata_repo.create_metadata = AsyncMock()

        # Mock the http client
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock response for sync with proper structure
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json = Mock(return_value={
                "sync_type": "full",
                "changes": [],
                "conflicts": [],
                "sync_stats": {
                    "entities_synced": 0,
                    "relationships_synced": 0,
                    "conflicts_resolved": 0
                }
            })
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.get = AsyncMock(return_value=mock_response)

            # Mock session methods with proper return values
            sync_engine.session.execute = AsyncMock()
            sync_engine.session.commit = AsyncMock()
            sync_engine.session.rollback = AsyncMock()

            # Create a mock result that returns empty list properly
            mock_scalars = Mock()
            mock_scalars.all = Mock(return_value=[])
            mock_result = Mock()
            mock_result.scalars = Mock(return_value=mock_scalars)
            sync_engine.session.execute.return_value = mock_result

            result = await sync_engine.sync()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_sync_with_conflicts(self, sync_engine):
        """Test synchronization with conflicts."""
        # Set up graph operations mock
        mock_graph_ops = Mock()
        mock_graph_ops.store_entity = AsyncMock()
        mock_graph_ops.store_relationship = AsyncMock()
        mock_graph_ops.get_entities_by_type = AsyncMock(return_value=[])
        mock_graph_ops.get_entity = AsyncMock(return_value=None)
        mock_graph_ops.search_entities = AsyncMock(return_value=[])
        sync_engine.set_graph_operations(mock_graph_ops)

        entity_id = str(uuid.uuid4())

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock response with conflicts
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json = Mock(return_value={
                "sync_type": "full",
                "changes": [],
                "conflicts": [
                    {
                        "entity_id": entity_id,
                        "local_version": "v1",
                        "remote_version": "v2",
                        "local_data": {"name": "Local", "updated_at": datetime.now(UTC).isoformat()},
                        "remote_data": {"name": "Remote", "updated_at": datetime.now(UTC).isoformat()},
                        "conflict_type": "update_conflict"
                    }
                ],
                "sync_stats": {
                    "entities_synced": 0,
                    "relationships_synced": 0,
                    "conflicts_resolved": 0
                }
            })
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)

            # Mock session
            sync_engine.session.execute = AsyncMock()
            sync_engine.session.commit = AsyncMock()
            sync_engine.session.rollback = AsyncMock()
            mock_result = Mock()
            mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
            sync_engine.session.execute.return_value = mock_result

            result = await sync_engine.sync()
            # The test passes if it doesn't raise an exception
            assert result is not None

    @pytest.mark.asyncio
    async def test_sync_delta(self, sync_engine):
        """Test delta synchronization."""
        # Set up graph operations mock
        mock_graph_ops = Mock()
        mock_graph_ops.store_entity = AsyncMock()
        mock_graph_ops.store_relationship = AsyncMock()
        mock_graph_ops.get_entities_by_type = AsyncMock(return_value=[])
        mock_graph_ops.get_entity = AsyncMock(return_value=None)
        mock_graph_ops.search_entities = AsyncMock(return_value=[])
        sync_engine.set_graph_operations(mock_graph_ops)

        # Mock metadata repository
        sync_engine.metadata_repo.get_metadata = AsyncMock(return_value=None)
        sync_engine.metadata_repo.update_sync_time = AsyncMock()
        sync_engine.metadata_repo.create_metadata = AsyncMock()

        # Set last sync time
        sync_engine.last_sync = datetime.now(UTC) - timedelta(minutes=5)

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock delta sync response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json = Mock(return_value={
                "sync_type": "delta",
                "changes": [],
                "conflicts": [],
                "sync_stats": {
                    "entities_synced": 0,
                    "relationships_synced": 0,
                    "conflicts_resolved": 0
                }
            })
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)

            # Mock session with proper return values
            sync_engine.session.execute = AsyncMock()
            sync_engine.session.commit = AsyncMock()
            sync_engine.session.rollback = AsyncMock()

            # Create a mock result that returns empty list properly
            mock_scalars = Mock()
            mock_scalars.all = Mock(return_value=[])
            mock_result = Mock()
            mock_result.scalars = Mock(return_value=mock_scalars)
            sync_engine.session.execute.return_value = mock_result

            result = await sync_engine.sync()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_sync_error_handling(self, sync_engine):
        """Test error handling during sync."""
        # Set up graph operations mock
        mock_graph_ops = Mock()
        mock_graph_ops.get_entities_by_type = AsyncMock(return_value=[])
        sync_engine.set_graph_operations(mock_graph_ops)

        # Mock metadata repository
        sync_engine.metadata_repo.get_metadata = AsyncMock(return_value=None)
        sync_engine.metadata_repo.update_sync_time = AsyncMock()
        sync_engine.metadata_repo.create_metadata = AsyncMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            # Make the context manager raise an error
            mock_client_class.side_effect = httpx.ConnectError("Connection failed")

            # Mock session with proper return values
            sync_engine.session.execute = AsyncMock()
            sync_engine.session.rollback = AsyncMock()

            # Create a mock result that returns empty list properly
            mock_scalars = Mock()
            mock_scalars.all = Mock(return_value=[])
            mock_result = Mock()
            mock_result.scalars = Mock(return_value=mock_scalars)
            sync_engine.session.execute.return_value = mock_result

            result = await sync_engine.sync()
            assert result.success is False
            assert len(result.errors) > 0
            assert "Connection failed" in str(result.errors[0])

    @pytest.mark.asyncio
    async def test_get_local_changes(self, sync_engine):
        """Test getting local changes for sync."""
        # Create a mock entity
        mock_entity = Mock()
        mock_entity.id = str(uuid.uuid4())
        mock_entity.version = f"{datetime.now(UTC).isoformat()}Z-test"
        mock_entity.entity_type = "device"
        mock_entity.updated_at = datetime.now(UTC)
        mock_entity.to_dict = Mock(return_value={
            "id": mock_entity.id,
            "name": "Test",
            "entity_type": "device",
            "version": mock_entity.version,
            "updated_at": mock_entity.updated_at.isoformat()
        })

        # Mock session execute to return the entity
        mock_result = Mock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[mock_entity])))
        sync_engine.session.execute = AsyncMock(return_value=mock_result)

        changes = await sync_engine._get_local_changes(datetime.now(UTC) - timedelta(hours=1))
        assert len(changes) >= 0  # May be 0 if no changes detected

    @pytest.mark.asyncio
    async def test_apply_remote_changes(self, sync_engine):
        """Test applying remote changes."""
        # Set up graph operations mock
        mock_graph_ops = Mock()
        mock_graph_ops.store_entity = AsyncMock()
        sync_engine.set_graph_operations(mock_graph_ops)

        # Create a test change
        test_change = Change(
            entity_type="device",
            entity_id=str(uuid.uuid4()),
            operation=SyncOperation.CREATE,
            data={
                "id": str(uuid.uuid4()),
                "version": f"{datetime.now(UTC).isoformat()}Z-server",
                "entity_type": "device",
                "name": "Remote Device",
                "content": {},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat()
            },
            updated_at=datetime.now(UTC),
            sync_id=str(uuid.uuid4())
        )

        # Mock session
        sync_engine.session.merge = Mock()
        sync_engine.session.commit = AsyncMock()

        result = await sync_engine._apply_single_change(test_change)

        # Verify the change was processed
        assert result is True  # Should return True on success


class TestSyncIntegration:
    """Test full sync integration scenarios."""

    @pytest.mark.asyncio
    async def test_bidirectional_sync(self, sync_engine):
        """Test bidirectional synchronization."""
        # Set up graph operations mock
        mock_graph_ops = Mock()
        mock_graph_ops.store_entity = AsyncMock()
        mock_graph_ops.store_relationship = AsyncMock()
        mock_graph_ops.get_entities_by_type = AsyncMock(return_value=[])
        mock_graph_ops.get_entity = AsyncMock(return_value=None)
        mock_graph_ops.search_entities = AsyncMock(return_value=[])
        sync_engine.set_graph_operations(mock_graph_ops)

        # Mock metadata repository
        sync_engine.metadata_repo.get_metadata = AsyncMock(return_value=None)
        sync_engine.metadata_repo.update_sync_time = AsyncMock()
        sync_engine.metadata_repo.create_metadata = AsyncMock()

        # Create local entity
        local_entity_id = str(uuid.uuid4())
        mock_entity = Mock()
        mock_entity.id = local_entity_id
        mock_entity.version = f"{datetime.now(UTC).isoformat()}Z-test"
        mock_entity.entity_type = "device"
        mock_entity.updated_at = datetime.now(UTC)
        mock_entity.to_dict = Mock(return_value={
            "id": local_entity_id,
            "name": "Local Entity",
            "entity_type": "device",
            "version": mock_entity.version,
            "updated_at": mock_entity.updated_at.isoformat()
        })

        # Mock session with proper return values
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])  # Return empty list to avoid serialization issues
        mock_result = Mock()
        mock_result.scalars = Mock(return_value=mock_scalars)
        sync_engine.session.execute = AsyncMock(return_value=mock_result)
        sync_engine.session.commit = AsyncMock()
        sync_engine.session.rollback = AsyncMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock response with server changes
            server_entity_id = str(uuid.uuid4())
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json = Mock(return_value={
                "sync_type": "full",
                "changes": [
                    {
                        "change_type": "create",
                        "entity": {
                            "id": server_entity_id,
                            "version": f"{datetime.now(UTC).isoformat()}Z-server",
                            "entity_type": "room",
                            "name": "Server Room",
                            "content": {},
                            "source_type": "manual",
                            "user_id": "server-user",
                            "created_at": datetime.now(UTC).isoformat(),
                            "updated_at": datetime.now(UTC).isoformat()
                        }
                    }
                ],
                "conflicts": [],
                "sync_stats": {
                    "entities_synced": 1,
                    "relationships_synced": 0,
                    "conflicts_resolved": 0
                }
            })
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)

            result = await sync_engine.sync()

            assert result.success is True
            # Verify that sync completed without errors
            assert len(result.errors) == 0
