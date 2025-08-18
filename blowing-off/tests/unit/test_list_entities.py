"""Test the list-entities CLI command."""

import json
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from click.testing import CliRunner

from blowingoff.cli.main import cli
from blowingoff.graph.local_storage import LocalGraphStorage
from inbetweenies.models import Entity, EntityType, SourceType


class TestListEntitiesCommand:
    """Test list-entities command functionality."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @pytest.fixture
    def mock_client(self):
        """Create a mock BlowingOffClient."""
        client = AsyncMock()
        client.disconnect = AsyncMock()
        return client

    @pytest.fixture
    def sample_entities(self):
        """Create sample entities for testing."""
        return [
            {
                "entity": {
                    "id": "home-1",
                    "entity_type": "home",
                    "name": "Test Home",
                    "content": {"is_primary": True},
                    "updated_at": "2025-01-01T10:00:00"
                },
                "score": 1.0
            },
            {
                "entity": {
                    "id": "room-1",
                    "entity_type": "room",
                    "name": "Living Room",
                    "content": {"floor": 1},
                    "updated_at": "2025-01-01T11:00:00"
                },
                "score": 1.0
            },
            {
                "entity": {
                    "id": "device-1",
                    "entity_type": "device",
                    "name": "Smart Light",
                    "content": {"manufacturer": "Test Corp"},
                    "updated_at": "2025-01-01T12:00:00"
                },
                "score": 1.0
            }
        ]

    def test_list_entities_not_connected(self, runner, tmp_path, monkeypatch):
        """Test list-entities when not connected."""
        # Set working directory to temp path
        monkeypatch.chdir(tmp_path)

        # Run command
        result = runner.invoke(cli, ['list-entities'])

        # Should fail with connection error
        assert result.exit_code != 0
        assert "Not connected" in result.output

    def test_list_entities_success(self, runner, mock_client, sample_entities, tmp_path, monkeypatch):
        """Test successful list-entities command."""
        # Set working directory to temp path
        monkeypatch.chdir(tmp_path)

        # Create config file
        config = {
            "server_url": "http://localhost:8000",
            "auth_token": "test-token",
            "client_id": "test-client",
            "db_path": str(tmp_path / "test.db")
        }
        config_path = tmp_path / ".blowingoff.json"
        config_path.write_text(json.dumps(config))

        # Mock the client
        mock_client.execute_mcp_tool = AsyncMock(return_value={
            "success": True,
            "result": {
                "results": sample_entities,
                "count": 3,
                "query": "*"
            }
        })

        with patch('blowingoff.cli.main.BlowingOffClient', return_value=mock_client):
            with patch('blowingoff.cli.main.load_client', new_callable=AsyncMock) as mock_load:
                mock_load.return_value = mock_client

                # Run command
                result = runner.invoke(cli, ['list-entities'])

                # Check output
                assert result.exit_code == 0
                assert "HOMES (1)" in result.output
                assert "Test Home" in result.output
                assert "ROOMS (1)" in result.output
                assert "Living Room" in result.output
                assert "DEVICES (1)" in result.output
                assert "Smart Light" in result.output

                # Verify MCP tool was called correctly
                mock_client.execute_mcp_tool.assert_called_once_with(
                    "search_entities",
                    query="*",
                    limit=100
                )

    def test_list_entities_empty(self, runner, mock_client, tmp_path, monkeypatch):
        """Test list-entities with no entities."""
        # Set working directory to temp path
        monkeypatch.chdir(tmp_path)

        # Create config file
        config = {
            "server_url": "http://localhost:8000",
            "auth_token": "test-token",
            "client_id": "test-client",
            "db_path": str(tmp_path / "test.db")
        }
        config_path = tmp_path / ".blowingoff.json"
        config_path.write_text(json.dumps(config))

        # Mock the client
        mock_client.execute_mcp_tool = AsyncMock(return_value={
            "success": True,
            "result": {
                "results": [],
                "count": 0,
                "query": "*"
            }
        })

        with patch('blowingoff.cli.main.BlowingOffClient', return_value=mock_client):
            with patch('blowingoff.cli.main.load_client', new_callable=AsyncMock) as mock_load:
                mock_load.return_value = mock_client

                # Run command
                result = runner.invoke(cli, ['list-entities'])

                # Should succeed and show "No entities found"
                assert result.exit_code == 0
                assert "No entities found" in result.output

    def test_list_entities_error(self, runner, mock_client, tmp_path, monkeypatch):
        """Test list-entities with MCP tool error."""
        # Set working directory to temp path
        monkeypatch.chdir(tmp_path)

        # Create config file
        config = {
            "server_url": "http://localhost:8000",
            "auth_token": "test-token",
            "client_id": "test-client",
            "db_path": str(tmp_path / "test.db")
        }
        config_path = tmp_path / ".blowingoff.json"
        config_path.write_text(json.dumps(config))

        # Mock the client with error
        mock_client.execute_mcp_tool = AsyncMock(return_value={
            "success": False,
            "error": "Database connection failed"
        })

        with patch('blowingoff.cli.main.BlowingOffClient', return_value=mock_client):
            with patch('blowingoff.cli.main.load_client', new_callable=AsyncMock) as mock_load:
                mock_load.return_value = mock_client

                # Run command
                result = runner.invoke(cli, ['list-entities'])

                # Should handle error gracefully
                assert result.exit_code == 0  # CLI doesn't propagate error as exit code
                # Error message might be shown in output

                # Verify MCP tool was called
                mock_client.execute_mcp_tool.assert_called_once()

    def test_list_entities_with_none_timestamps(self, runner, mock_client, tmp_path, monkeypatch):
        """Test list-entities with entities that have None timestamps."""
        # Set working directory to temp path
        monkeypatch.chdir(tmp_path)

        # Create config file
        config = {
            "server_url": "http://localhost:8000",
            "auth_token": "test-token",
            "client_id": "test-client",
            "db_path": str(tmp_path / "test.db")
        }
        config_path = tmp_path / ".blowingoff.json"
        config_path.write_text(json.dumps(config))

        # Create entities with None timestamps
        sample_entities = [
            {
                "entity": {
                    "id": "auto-1",
                    "entity_type": "automation",
                    "name": "Morning Routine",
                    "content": {"enabled": True},
                    "updated_at": None,  # None timestamp
                    "created_at": None
                },
                "score": 1.0
            },
            {
                "entity": {
                    "id": "auto-2",
                    "entity_type": "automation",
                    "name": "Night Mode",
                    "content": {"enabled": False}
                    # Missing timestamps entirely
                },
                "score": 1.0
            }
        ]

        # Mock the client
        mock_client.execute_mcp_tool = AsyncMock(return_value={
            "success": True,
            "result": {
                "results": sample_entities,
                "count": 2,
                "query": "*"
            }
        })

        with patch('blowingoff.cli.main.BlowingOffClient', return_value=mock_client):
            with patch('blowingoff.cli.main.load_client', new_callable=AsyncMock) as mock_load:
                mock_load.return_value = mock_client

                # Run command - should not crash on None timestamps
                result = runner.invoke(cli, ['list-entities'])

                # Check output
                assert result.exit_code == 0
                assert "AUTOMATIONS (2)" in result.output
                assert "Morning Routine" in result.output
                assert "Night Mode" in result.output
                assert "Unknown" in result.output  # For None timestamps


class TestSearchEntitiesMCPTool:
    """Test the search_entities MCP tool implementation."""

    @pytest.mark.asyncio
    async def test_search_all_entities(self, tmp_path):
        """Test searching for all entities with '*' query."""
        from blowingoff.graph.local_operations import LocalGraphOperations

        # Create storage with test data using temp path
        storage = LocalGraphStorage(str(tmp_path / "test.db"))

        # Add test entities
        home = Entity(
            id="home-1",
            version="v1",
            entity_type=EntityType.HOME,
            name="Test Home",
            content={"is_primary": True},
            source_type=SourceType.MANUAL,
            user_id="test-user"
        )
        room = Entity(
            id="room-1",
            version="v1",
            entity_type=EntityType.ROOM,
            name="Living Room",
            content={"floor": 1},
            source_type=SourceType.MANUAL,
            user_id="test-user"
        )
        device = Entity(
            id="device-1",
            version="v1",
            entity_type=EntityType.DEVICE,
            name="Smart Light",
            content={"manufacturer": "Test Corp"},
            source_type=SourceType.HOMEKIT,
            user_id="test-user"
        )

        storage.store_entity(home)
        storage.store_entity(room)
        storage.store_entity(device)

        # Create operations
        ops = LocalGraphOperations(storage)

        # Test search all with '*'
        result = await ops.search_entities_tool(query="*", limit=10)

        assert result.success is True
        assert result.result["count"] == 3
        assert len(result.result["results"]) == 3
        assert result.result["query"] == "*"

        # Check that all entities are returned
        entity_ids = {r["entity"]["id"] for r in result.result["results"]}
        assert entity_ids == {"home-1", "room-1", "device-1"}

    @pytest.mark.asyncio
    async def test_search_by_name(self, tmp_path):
        """Test searching entities by name."""
        from blowingoff.graph.local_operations import LocalGraphOperations

        # Create storage with test data using temp path
        storage = LocalGraphStorage(str(tmp_path / "test.db"))

        # Add test entities
        entity1 = Entity(
            id="1",
            version="v1",
            entity_type=EntityType.ROOM,
            name="Living Room",
            content={},
            source_type=SourceType.MANUAL,
            user_id="test"
        )
        entity2 = Entity(
            id="2",
            version="v1",
            entity_type=EntityType.ROOM,
            name="Bedroom",
            content={},
            source_type=SourceType.MANUAL,
            user_id="test"
        )

        storage.store_entity(entity1)
        storage.store_entity(entity2)

        # Create operations
        ops = LocalGraphOperations(storage)

        # Search for "living" - should only match Living Room
        result = await ops.search_entities_tool(query="living", limit=10)

        assert result.success is True
        assert result.result["count"] == 1
        assert result.result["results"][0]["entity"]["name"] == "Living Room"

    @pytest.mark.asyncio
    async def test_search_with_type_filter(self, tmp_path):
        """Test searching with entity type filter."""
        from blowingoff.graph.local_operations import LocalGraphOperations

        # Create storage with test data using temp path
        storage = LocalGraphStorage(str(tmp_path / "test.db"))

        # Add entities of different types
        home = Entity(
            id="home-1",
            version="v1",
            entity_type=EntityType.HOME,
            name="Test Home",
            content={},
            source_type=SourceType.MANUAL,
            user_id="test"
        )
        room = Entity(
            id="room-1",
            version="v1",
            entity_type=EntityType.ROOM,
            name="Test Room",
            content={},
            source_type=SourceType.MANUAL,
            user_id="test"
        )

        storage.store_entity(home)
        storage.store_entity(room)

        # Create operations
        ops = LocalGraphOperations(storage)

        # Search for all rooms only
        result = await ops.search_entities_tool(
            query="*",
            entity_types=["room"],
            limit=10
        )

        assert result.success is True
        assert result.result["count"] == 1
        assert result.result["results"][0]["entity"]["entity_type"] == "room"

    @pytest.mark.asyncio
    async def test_search_result_to_dict_with_none_values(self, tmp_path):
        """Test SearchResult.to_dict handles None values properly."""
        from blowingoff.graph.local_operations import LocalGraphOperations, SearchResult

        # Create storage with test data
        storage = LocalGraphStorage(str(tmp_path / "test.db"))

        # Create entity without timestamps
        entity = Entity(
            id="test-1",
            version="v1",
            entity_type=EntityType.AUTOMATION,
            name="Test Automation",
            content={"enabled": True},
            source_type=SourceType.MANUAL,
            user_id="test"
        )
        # Don't set created_at or updated_at

        # Create SearchResult
        result = SearchResult(entity=entity, score=1.0)

        # Convert to dict
        result_dict = result.to_dict()

        # Check structure
        assert "entity" in result_dict
        assert "score" in result_dict

        # Check entity fields exist even if None
        entity_dict = result_dict["entity"]
        assert "id" in entity_dict
        assert "name" in entity_dict
        assert "entity_type" in entity_dict
        assert "updated_at" in entity_dict
        assert "created_at" in entity_dict

        # Check values
        assert entity_dict["id"] == "test-1"
        assert entity_dict["name"] == "Test Automation"
        assert entity_dict["entity_type"] == "automation"
        assert entity_dict["updated_at"] is None
        assert entity_dict["created_at"] is None
