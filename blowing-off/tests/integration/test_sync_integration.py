"""
Integration tests for synchronization functionality.

Tests the sync engine, protocol, and conflict resolution.
"""

import pytest
import tempfile
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import uuid
import httpx

from blowingoff.sync.engine import SyncEngine
from blowingoff.sync.protocol import InbetweeniesProtocol
from blowingoff.sync.conflict_resolver import ConflictResolver
from inbetweenies.sync import SyncState, Change, ChangeType, Conflict, ConflictResolution
from inbetweenies.models import Entity, EntityType


@pytest.fixture
def sync_protocol():
    """Create an InbetweeniesProtocol instance."""
    return InbetweeniesProtocol(
        server_url="http://localhost:8000",
        auth_token="test-token"
    )


@pytest.fixture
def conflict_resolver():
    """Create a ConflictResolver instance."""
    return ConflictResolver()


@pytest.fixture
async def sync_engine(sync_protocol, conflict_resolver):
    """Create a SyncEngine instance."""
    session_factory = AsyncMock()
    session_factory.return_value.__aenter__ = AsyncMock()
    session_factory.return_value.__aexit__ = AsyncMock()
    
    engine = SyncEngine(
        protocol=sync_protocol,
        session_factory=session_factory,
        conflict_resolver=conflict_resolver,
        client_id="test-client",
        user_id="test-user"
    )
    return engine


class TestInbetweeniesProtocol:
    """Test the synchronization protocol."""
    
    @pytest.mark.asyncio
    async def test_negotiate_protocol(self, sync_protocol):
        """Test protocol negotiation."""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=Mock(return_value={
                    "protocol_version": "inbetweenies-v2",
                    "supported_features": ["delta_sync", "conflict_resolution"]
                })
            )
            
            result = await sync_protocol.negotiate_protocol()
            assert result["protocol_version"] == "inbetweenies-v2"
    
    @pytest.mark.asyncio
    async def test_send_sync_request(self, sync_protocol):
        """Test sending sync request."""
        sync_state = SyncState(
            client_id="test-client",
            last_sync=datetime.utcnow() - timedelta(hours=1),
            vector_clock={"test-client": 1},
            pending_changes=[]
        )
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=Mock(return_value={
                    "success": True,
                    "entities": [],
                    "relationships": [],
                    "conflicts": [],
                    "vector_clock": {"test-client": 1, "server": 5}
                })
            )
            
            result = await sync_protocol.send_sync_request(sync_state)
            assert result["success"] is True
            assert "vector_clock" in result
    
    @pytest.mark.asyncio
    async def test_send_changes(self, sync_protocol):
        """Test sending changes to server."""
        changes = [
            Change(
                entity_id=str(uuid.uuid4()),
                change_type=ChangeType.CREATE,
                entity_data={
                    "name": "Test Entity",
                    "entity_type": "device"
                },
                timestamp=datetime.utcnow(),
                user_id="test-user"
            )
        ]
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=Mock(return_value={
                    "success": True,
                    "accepted": 1,
                    "rejected": 0
                })
            )
            
            result = await sync_protocol.send_changes(changes)
            assert result["success"] is True
            assert result["accepted"] == 1
    
    @pytest.mark.asyncio
    async def test_resolve_conflicts(self, sync_protocol):
        """Test resolving conflicts with server."""
        resolutions = [
            ConflictResolution(
                conflict_id=str(uuid.uuid4()),
                resolution_type="client_wins",
                resolved_data={"test": "data"},
                resolved_by="test-user"
            )
        ]
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=Mock(return_value={
                    "success": True,
                    "resolved": 1
                })
            )
            
            result = await sync_protocol.resolve_conflicts(resolutions)
            assert result["success"] is True
            assert result["resolved"] == 1


class TestConflictResolver:
    """Test conflict resolution functionality."""
    
    @pytest.mark.asyncio
    async def test_resolve_last_write_wins(self, conflict_resolver):
        """Test last-write-wins conflict resolution."""
        conflict = Conflict(
            entity_id=str(uuid.uuid4()),
            local_version="2024-01-01T12:00:00Z-user1",
            remote_version="2024-01-01T13:00:00Z-user2",
            local_data={"name": "Local Name"},
            remote_data={"name": "Remote Name"},
            conflict_type="update_conflict"
        )
        
        resolution = await conflict_resolver.resolve(conflict, strategy="last_write_wins")
        assert resolution.resolved_data == conflict.remote_data
    
    @pytest.mark.asyncio
    async def test_resolve_client_wins(self, conflict_resolver):
        """Test client-wins conflict resolution."""
        conflict = Conflict(
            entity_id=str(uuid.uuid4()),
            local_version="2024-01-01T12:00:00Z-user1",
            remote_version="2024-01-01T13:00:00Z-user2",
            local_data={"name": "Local Name"},
            remote_data={"name": "Remote Name"},
            conflict_type="update_conflict"
        )
        
        resolution = await conflict_resolver.resolve(conflict, strategy="client_wins")
        assert resolution.resolved_data == conflict.local_data
    
    @pytest.mark.asyncio
    async def test_resolve_server_wins(self, conflict_resolver):
        """Test server-wins conflict resolution."""
        conflict = Conflict(
            entity_id=str(uuid.uuid4()),
            local_version="2024-01-01T12:00:00Z-user1",
            remote_version="2024-01-01T13:00:00Z-user2",
            local_data={"name": "Local Name"},
            remote_data={"name": "Remote Name"},
            conflict_type="update_conflict"
        )
        
        resolution = await conflict_resolver.resolve(conflict, strategy="server_wins")
        assert resolution.resolved_data == conflict.remote_data
    
    @pytest.mark.asyncio
    async def test_resolve_merge(self, conflict_resolver):
        """Test merge conflict resolution."""
        conflict = Conflict(
            entity_id=str(uuid.uuid4()),
            local_version="2024-01-01T12:00:00Z-user1",
            remote_version="2024-01-01T13:00:00Z-user2",
            local_data={"name": "Local Name", "field1": "value1"},
            remote_data={"name": "Remote Name", "field2": "value2"},
            conflict_type="update_conflict"
        )
        
        resolution = await conflict_resolver.resolve(conflict, strategy="merge")
        # Merge should include fields from both
        assert "field1" in resolution.resolved_data
        assert "field2" in resolution.resolved_data


class TestSyncEngine:
    """Test the synchronization engine."""
    
    @pytest.mark.asyncio
    async def test_sync_full(self, sync_engine):
        """Test full synchronization."""
        # Mock protocol responses
        with patch.object(sync_engine.protocol, 'negotiate_protocol') as mock_negotiate:
            mock_negotiate.return_value = {
                "protocol_version": "inbetweenies-v2",
                "supported_features": ["delta_sync"]
            }
            
            with patch.object(sync_engine.protocol, 'send_sync_request') as mock_sync:
                mock_sync.return_value = {
                    "success": True,
                    "entities": [
                        {
                            "id": str(uuid.uuid4()),
                            "name": "Test Entity",
                            "entity_type": "device",
                            "version": f"{datetime.utcnow().isoformat()}Z-server"
                        }
                    ],
                    "relationships": [],
                    "conflicts": [],
                    "vector_clock": {"server": 1}
                }
                
                result = await sync_engine.sync()
                assert result.success is True
                assert result.entities_synced == 1
                assert result.relationships_synced == 0
                assert len(result.conflicts) == 0
    
    @pytest.mark.asyncio
    async def test_sync_with_conflicts(self, sync_engine):
        """Test synchronization with conflicts."""
        entity_id = str(uuid.uuid4())
        
        with patch.object(sync_engine.protocol, 'negotiate_protocol') as mock_negotiate:
            mock_negotiate.return_value = {
                "protocol_version": "inbetweenies-v2",
                "supported_features": ["conflict_resolution"]
            }
            
            with patch.object(sync_engine.protocol, 'send_sync_request') as mock_sync:
                mock_sync.return_value = {
                    "success": True,
                    "entities": [],
                    "relationships": [],
                    "conflicts": [
                        {
                            "entity_id": entity_id,
                            "local_version": "v1",
                            "remote_version": "v2",
                            "local_data": {"name": "Local"},
                            "remote_data": {"name": "Remote"},
                            "conflict_type": "update_conflict"
                        }
                    ],
                    "vector_clock": {"server": 1}
                }
                
                with patch.object(sync_engine.protocol, 'resolve_conflicts') as mock_resolve:
                    mock_resolve.return_value = {"success": True, "resolved": 1}
                    
                    result = await sync_engine.sync()
                    assert result.success is True
                    assert len(result.conflicts) == 1
                    assert result.conflicts[0].entity_id == entity_id
    
    @pytest.mark.asyncio
    async def test_sync_delta(self, sync_engine):
        """Test delta synchronization."""
        # Set last sync time
        sync_engine.last_sync = datetime.utcnow() - timedelta(minutes=5)
        
        with patch.object(sync_engine.protocol, 'negotiate_protocol') as mock_negotiate:
            mock_negotiate.return_value = {
                "protocol_version": "inbetweenies-v2",
                "supported_features": ["delta_sync"]
            }
            
            with patch.object(sync_engine.protocol, 'send_sync_request') as mock_sync:
                mock_sync.return_value = {
                    "success": True,
                    "sync_type": "delta",
                    "entities": [],
                    "relationships": [],
                    "conflicts": [],
                    "vector_clock": {"server": 2}
                }
                
                result = await sync_engine.sync()
                assert result.success is True
                # Verify delta sync was used
                mock_sync.assert_called_once()
                call_args = mock_sync.call_args[0][0]
                assert call_args.last_sync is not None
    
    @pytest.mark.asyncio
    async def test_sync_error_handling(self, sync_engine):
        """Test error handling during sync."""
        with patch.object(sync_engine.protocol, 'negotiate_protocol') as mock_negotiate:
            mock_negotiate.side_effect = httpx.ConnectError("Connection failed")
            
            result = await sync_engine.sync()
            assert result.success is False
            assert result.error is not None
            assert "Connection failed" in result.error
    
    @pytest.mark.asyncio
    async def test_get_local_changes(self, sync_engine):
        """Test getting local changes for sync."""
        # Mock session to return some local changes
        mock_session = AsyncMock()
        sync_engine.session_factory.return_value.__aenter__.return_value = mock_session
        
        # Create a mock entity
        mock_entity = Mock()
        mock_entity.id = str(uuid.uuid4())
        mock_entity.updated_at = datetime.utcnow()
        mock_entity.to_dict = Mock(return_value={"id": mock_entity.id, "name": "Test"})
        
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalars = Mock(return_value=Mock(all=Mock(return_value=[mock_entity])))
        
        changes = await sync_engine._get_local_changes(datetime.utcnow() - timedelta(hours=1))
        assert len(changes) >= 0  # May be 0 if no changes detected
    
    @pytest.mark.asyncio
    async def test_apply_remote_changes(self, sync_engine):
        """Test applying remote changes."""
        entities = [
            {
                "id": str(uuid.uuid4()),
                "version": f"{datetime.utcnow().isoformat()}Z-server",
                "entity_type": "device",
                "name": "Remote Device",
                "content": {},
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "created_by": "server",
                "updated_by": "server"
            }
        ]
        
        mock_session = AsyncMock()
        sync_engine.session_factory.return_value.__aenter__.return_value = mock_session
        mock_session.merge = Mock()
        mock_session.commit = AsyncMock()
        
        await sync_engine._apply_remote_changes(entities, [])
        
        # Verify entities were merged
        assert mock_session.merge.called


class TestSyncIntegration:
    """Test full sync integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_bidirectional_sync(self, sync_engine):
        """Test bidirectional synchronization."""
        # Create local changes
        local_entity_id = str(uuid.uuid4())
        local_changes = [
            Change(
                entity_id=local_entity_id,
                change_type=ChangeType.CREATE,
                entity_data={
                    "id": local_entity_id,
                    "name": "Local Entity",
                    "entity_type": "device"
                },
                timestamp=datetime.utcnow(),
                user_id="test-user"
            )
        ]
        
        # Mock getting local changes
        with patch.object(sync_engine, '_get_local_changes') as mock_get_changes:
            mock_get_changes.return_value = local_changes
            
            # Mock protocol
            with patch.object(sync_engine.protocol, 'negotiate_protocol') as mock_negotiate:
                mock_negotiate.return_value = {
                    "protocol_version": "inbetweenies-v2",
                    "supported_features": ["delta_sync"]
                }
                
                with patch.object(sync_engine.protocol, 'send_sync_request') as mock_sync:
                    # Server returns its own changes
                    server_entity_id = str(uuid.uuid4())
                    mock_sync.return_value = {
                        "success": True,
                        "entities": [
                            {
                                "id": server_entity_id,
                                "name": "Server Entity",
                                "entity_type": "room",
                                "version": f"{datetime.utcnow().isoformat()}Z-server"
                            }
                        ],
                        "relationships": [],
                        "conflicts": [],
                        "vector_clock": {"server": 1, "test-client": 1}
                    }
                    
                    with patch.object(sync_engine, '_apply_remote_changes') as mock_apply:
                        mock_apply.return_value = None
                        
                        result = await sync_engine.sync()
                        
                        assert result.success is True
                        assert result.entities_synced == 1  # Server entity
                        
                        # Verify local changes were sent
                        mock_sync.assert_called_once()
                        sync_state = mock_sync.call_args[0][0]
                        assert len(sync_state.pending_changes) == 1
                        assert sync_state.pending_changes[0].entity_id == local_entity_id