#!/usr/bin/env python3
"""
BDD Integration Tests for TinyLlama MCP Chat
============================================

Runs BDD tests against the actual running chat application with real data.
Requires FunkyGibbon server to be running at http://localhost:8000.
"""

import asyncio
import pytest
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock

sys.path.append('/workspaces/the-goodies')

from chat.tinyllama_mcp_chat import TinyLlamaMCPChat
from blowingoff.client import BlowingOffClient


class TestIntegrationBase:
    """Base class for integration tests with real server"""

    @pytest.fixture
    async def real_chat_instance(self):
        """Create a real chat instance connected to the server"""
        chat = TinyLlamaMCPChat()

        # Mock only the model to avoid loading it
        chat.model = MagicMock()
        chat.model.return_value = {
            'choices': [{
                'text': 'Based on the data, here are the results from the smart home system.'
            }]
        }

        # Use real client connection
        chat.client = BlowingOffClient(db_path="/tmp/test-integration.db")

        # Connect to actual server
        try:
            await chat.client.connect(
                server_url="http://localhost:8000",
                password="admin"
            )
            await chat.client.sync()
            chat.tools = chat._get_available_tools()
        except Exception as e:
            pytest.skip(f"FunkyGibbon server not available: {e}")

        yield chat

        # Cleanup
        await chat.client.disconnect()

    @pytest.fixture
    async def check_server_health(self):
        """Check if server is running before tests"""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8000/health") as response:
                    if response.status != 200:
                        pytest.skip("FunkyGibbon server health check failed")
        except:
            pytest.skip("FunkyGibbon server not running at http://localhost:8000")


@pytest.mark.integration
class TestRoomQueriesIntegration(TestIntegrationBase):
    """Integration tests for room-related queries with real data"""

    @pytest.mark.asyncio
    async def test_list_all_rooms(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with smart home data
        WHEN user asks to list all rooms
        THEN chat should return actual rooms from the database
        """
        # Given
        chat = real_chat_instance

        # When
        response = await chat.process_query("list all rooms")

        # Then
        assert response is not None
        # Check for known rooms from the test data
        assert any(room in response.lower() for room in ['living', 'kitchen', 'bedroom', 'office'])

    @pytest.mark.asyncio
    async def test_search_specific_room(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with room data
        WHEN user searches for kitchen
        THEN chat should return kitchen information
        """
        # Given
        chat = real_chat_instance

        # When
        response = await chat.process_query("search for kitchen")

        # Then
        assert response is not None
        assert 'kitchen' in response.lower()

    @pytest.mark.asyncio
    async def test_get_room_connections(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with room relationship data
        WHEN user asks about room connections
        THEN chat should use get_room_connections MCP tool
        """
        # Given
        chat = real_chat_instance

        # When - first get a room ID
        rooms = await chat.client.execute_mcp_tool("search_entities", query="living room")
        if isinstance(rooms, dict) and 'result' in rooms:
            rooms = rooms['result'].get('results', [])

        if rooms and len(rooms) > 0:
            room_entity = rooms[0].get('entity', rooms[0])
            room_id = room_entity.get('id') or room_entity.get('entity_id')

            if room_id:
                # Test room connections
                connections = await chat.client.execute_mcp_tool("get_room_connections", room_id=room_id)

                # Then
                assert connections is not None


@pytest.mark.integration
class TestDeviceQueriesIntegration(TestIntegrationBase):
    """Integration tests for device-related queries with real data"""

    @pytest.mark.asyncio
    async def test_list_all_devices(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with device data
        WHEN user asks to list all devices
        THEN chat should return actual devices from the database
        """
        # Given
        chat = real_chat_instance

        # When
        response = await chat.process_query("list all devices")

        # Then
        assert response is not None
        # Check for known devices
        assert any(device in response.lower() for device in ['tv', 'thermostat', 'light', 'fridge'])

    @pytest.mark.asyncio
    async def test_search_lights(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with light devices
        WHEN user searches for lights
        THEN chat should return light information
        """
        # Given
        chat = real_chat_instance

        # When
        response = await chat.process_query("search for lights")

        # Then
        assert response is not None
        assert 'light' in response.lower()

    @pytest.mark.asyncio
    async def test_find_device_controls(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with device control relationships
        WHEN checking what controls a device
        THEN chat should use find_device_controls MCP tool
        """
        # Given
        chat = real_chat_instance

        # When - first get a device ID
        devices = await chat.client.execute_mcp_tool("search_entities", query="thermostat")
        if isinstance(devices, dict) and 'result' in devices:
            devices = devices['result'].get('results', [])

        if devices and len(devices) > 0:
            device_entity = devices[0].get('entity', devices[0])
            device_id = device_entity.get('id') or device_entity.get('entity_id')

            if device_id:
                # Test device controls
                controls = await chat.client.execute_mcp_tool("find_device_controls", device_id=device_id)

                # Then
                assert controls is not None


@pytest.mark.integration
class TestRoomDeviceRelationshipsIntegration(TestIntegrationBase):
    """Integration tests for room-device relationships with real data"""

    @pytest.mark.asyncio
    async def test_devices_in_kitchen(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with kitchen devices
        WHEN user asks what devices are in the kitchen
        THEN chat should return kitchen devices
        """
        # Given
        chat = real_chat_instance

        # When
        response = await chat.process_query("what devices are in the kitchen?")

        # Then
        assert response is not None
        # Kitchen should have fridge and oven based on test data
        assert any(device in response.lower() for device in ['fridge', 'oven', 'kitchen'])

    @pytest.mark.asyncio
    async def test_devices_in_living_room(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with living room devices
        WHEN user asks what devices are in the living room
        THEN chat should return living room devices
        """
        # Given
        chat = real_chat_instance

        # When
        response = await chat.process_query("what devices are in the living room?")

        # Then
        assert response is not None
        # Living room should have TV and lights based on test data
        assert any(device in response.lower() for device in ['tv', 'light', 'living'])

    @pytest.mark.asyncio
    async def test_get_devices_in_room(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with room-device relationships
        WHEN using get_devices_in_room MCP tool
        THEN should return devices in that room
        """
        # Given
        chat = real_chat_instance

        # When - first get a room ID
        rooms = await chat.client.execute_mcp_tool("search_entities", query="kitchen")
        if isinstance(rooms, dict) and 'result' in rooms:
            rooms = rooms['result'].get('results', [])

        if rooms and len(rooms) > 0:
            room_entity = rooms[0].get('entity', rooms[0])
            room_id = room_entity.get('id') or room_entity.get('entity_id')

            if room_id:
                # Test devices in room
                devices = await chat.client.execute_mcp_tool("get_devices_in_room", room_id=room_id)

                # Then
                assert devices is not None


@pytest.mark.integration
class TestAutomationQueriesIntegration(TestIntegrationBase):
    """Integration tests for automation-related queries with real data"""

    @pytest.mark.asyncio
    async def test_list_automations(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with automation data
        WHEN user asks to list automations
        THEN chat should return actual automations
        """
        # Given
        chat = real_chat_instance

        # When
        response = await chat.process_query("list all automations")

        # Then
        assert response is not None
        # Check for known automations from test data
        assert any(auto in response.lower() for auto in ['morning', 'movie', 'automation'])

    @pytest.mark.asyncio
    async def test_get_automations_in_room(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with room automations
        WHEN using get_automations_in_room MCP tool
        THEN should return automations for that room
        """
        # Given
        chat = real_chat_instance

        # When - first get a room ID
        rooms = await chat.client.execute_mcp_tool("search_entities", query="living room")
        if isinstance(rooms, dict) and 'result' in rooms:
            rooms = rooms['result'].get('results', [])

        if rooms and len(rooms) > 0:
            room_entity = rooms[0].get('entity', rooms[0])
            room_id = room_entity.get('id') or room_entity.get('entity_id')

            if room_id:
                # Test automations in room
                automations = await chat.client.execute_mcp_tool("get_automations_in_room", room_id=room_id)

                # Then
                assert automations is not None


@pytest.mark.integration
class TestMCPToolsIntegration(TestIntegrationBase):
    """Integration tests for MCP tool functionality with real server"""

    @pytest.mark.asyncio
    async def test_search_entities_tool(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with entity data
        WHEN using search_entities MCP tool
        THEN should return matching entities
        """
        # Given
        chat = real_chat_instance

        # When
        result = await chat.client.execute_mcp_tool("search_entities", query="smart")

        # Then
        assert result is not None
        if isinstance(result, dict) and 'result' in result:
            results = result['result'].get('results', [])
            assert len(results) > 0

    @pytest.mark.asyncio
    async def test_find_similar_entities_tool(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with entity data
        WHEN using find_similar_entities MCP tool
        THEN should return similar entities
        """
        # Given
        chat = real_chat_instance

        # When - first get an entity ID
        entities = await chat.client.execute_mcp_tool("search_entities", query="light")
        if isinstance(entities, dict) and 'result' in entities:
            entities = entities['result'].get('results', [])

        if entities and len(entities) > 0:
            entity = entities[0].get('entity', entities[0])
            entity_id = entity.get('id') or entity.get('entity_id')

            if entity_id:
                # Test similar entities
                similar = await chat.client.execute_mcp_tool("find_similar_entities", entity_id=entity_id)

                # Then
                assert similar is not None

    @pytest.mark.asyncio
    async def test_get_procedures_for_device_tool(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with device procedures
        WHEN using get_procedures_for_device MCP tool
        THEN should return procedures for that device
        """
        # Given
        chat = real_chat_instance

        # When - first get a device ID
        devices = await chat.client.execute_mcp_tool("search_entities", query="tv")
        if isinstance(devices, dict) and 'result' in devices:
            devices = devices['result'].get('results', [])

        if devices and len(devices) > 0:
            device_entity = devices[0].get('entity', devices[0])
            device_id = device_entity.get('id') or device_entity.get('entity_id')

            if device_id:
                # Test procedures for device
                procedures = await chat.client.execute_mcp_tool("get_procedures_for_device", device_id=device_id)

                # Then
                assert procedures is not None

    @pytest.mark.asyncio
    async def test_find_path_tool(self, real_chat_instance, check_server_health):
        """
        GIVEN a running server with room connections
        WHEN using find_path MCP tool
        THEN should return path between locations
        """
        # Given
        chat = real_chat_instance

        # When - get two room IDs
        kitchen = await chat.client.execute_mcp_tool("search_entities", query="kitchen")
        living = await chat.client.execute_mcp_tool("search_entities", query="living room")

        kitchen_id = None
        living_id = None

        if isinstance(kitchen, dict) and 'result' in kitchen:
            kitchen_results = kitchen['result'].get('results', [])
            if kitchen_results:
                kitchen_entity = kitchen_results[0].get('entity', kitchen_results[0])
                kitchen_id = kitchen_entity.get('id') or kitchen_entity.get('entity_id')

        if isinstance(living, dict) and 'result' in living:
            living_results = living['result'].get('results', [])
            if living_results:
                living_entity = living_results[0].get('entity', living_results[0])
                living_id = living_entity.get('id') or living_entity.get('entity_id')

        if kitchen_id and living_id:
            # Test path finding
            path = await chat.client.execute_mcp_tool("find_path", from_id=kitchen_id, to_id=living_id)

            # Then
            assert path is not None


# Pytest configuration for integration tests
def pytest_configure(config):
    """Add custom markers for integration tests"""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test with real server"
    )


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-m", "integration"])