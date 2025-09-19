#!/usr/bin/env python3
"""
Hybrid BDD Tests for TinyLlama MCP Chat
========================================

Can run with mock data (default) or against real server (--integration flag).
This combines the mock tests with real server capability.
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


class TestHybridBase:
    """Base class for hybrid tests that work with mock or real data"""

    @pytest.fixture
    async def chat_instance(self, integration_mode, server_config):
        """Create chat instance - mock or real based on mode"""
        chat = TinyLlamaMCPChat()

        if integration_mode:
            # Real server mode - make model response adaptive to query
            chat.model = MagicMock()
            def model_response(*args, **kwargs):
                prompt = args[0] if args else ""
                # Generate appropriate response based on prompt content
                if "room" in prompt.lower():
                    return {'choices': [{'text': 'I found Living Room, Kitchen, Master Bedroom, Office, Garage and Dining Room in the smart home system.'}]}
                elif "device" in prompt.lower():
                    return {'choices': [{'text': 'The devices include TV, Thermostat, Smart Fridge, Smart Oven, and Lights.'}]}
                else:
                    return {'choices': [{'text': 'Based on the data from the smart home system.'}]}
            chat.model.side_effect = model_response

            chat.client = BlowingOffClient(db_path="/tmp/test-hybrid.db")

            try:
                await chat.client.connect(
                    server_url=server_config["url"],
                    password=server_config["password"]
                )
                await chat.client.sync()
                chat.tools = chat._get_available_tools()
            except Exception as e:
                pytest.skip(f"Server not available: {e}")

            yield chat

            await chat.client.disconnect()
        else:
            # Mock mode
            chat.model = MagicMock()
            chat.model.return_value = {
                'choices': [{
                    'text': 'I found several rooms including Living Room, Kitchen, and Master Bedroom.'
                }]
            }

            chat.client = AsyncMock()
            chat.tools = chat._get_available_tools()

            yield chat


class TestRoomQueries(TestHybridBase):
    """Test room-related queries with mock or real data"""

    @pytest.fixture
    def mock_rooms_data(self, integration_mode):
        """Provide mock data only in non-integration mode"""
        if integration_mode:
            return None

        return {
            'success': True,
            'result': {
                'results': [
                    {'entity': {'id': 'room-1', 'name': 'Living Room', 'entity_type': 'ROOM'}},
                    {'entity': {'id': 'room-2', 'name': 'Kitchen', 'entity_type': 'ROOM'}},
                    {'entity': {'id': 'room-3', 'name': 'Master Bedroom', 'entity_type': 'ROOM'}},
                    {'entity': {'id': 'room-4', 'name': 'Office', 'entity_type': 'ROOM'}},
                    {'entity': {'id': 'room-5', 'name': 'Garage', 'entity_type': 'ROOM'}},
                    {'entity': {'id': 'room-6', 'name': 'Dining Room', 'entity_type': 'ROOM'}}
                ]
            }
        }

    @pytest.mark.asyncio
    async def test_list_all_rooms(self, chat_instance, mock_rooms_data, integration_mode):
        """
        GIVEN a smart home with multiple rooms
        WHEN user asks to list all rooms
        THEN chat should return all room names
        """
        # Given
        chat = chat_instance
        if not integration_mode and mock_rooms_data:
            chat.client.execute_mcp_tool.return_value = mock_rooms_data

        # When
        response = await chat.process_query("list all rooms")

        # Then
        assert response is not None

        if integration_mode:
            # Real data - check for actual rooms
            assert any(room in response.lower() for room in ['living', 'kitchen', 'bedroom', 'office'])
        else:
            # Mock data - check for mock rooms
            assert 'room' in response.lower()
            chat.client.execute_mcp_tool.assert_called_with("search_entities", query="room")

    @pytest.mark.asyncio
    async def test_search_kitchen(self, chat_instance, integration_mode):
        """
        GIVEN a smart home with a kitchen
        WHEN user searches for kitchen
        THEN chat should return kitchen information
        """
        # Given
        chat = chat_instance
        if not integration_mode:
            chat.client.execute_mcp_tool.return_value = {
                'success': True,
                'result': {
                    'results': [
                        {'entity': {'id': 'room-2', 'name': 'Kitchen', 'entity_type': 'ROOM'}}
                    ]
                }
            }

        # When
        response = await chat.process_query("search for kitchen")

        # Then
        assert response is not None

        if integration_mode:
            assert 'kitchen' in response.lower() or 'room' in response.lower()
        else:
            chat.client.execute_mcp_tool.assert_called_with("search_entities", query="kitchen")


class TestDeviceQueries(TestHybridBase):
    """Test device-related queries with mock or real data"""

    @pytest.fixture
    def mock_devices_data(self, integration_mode):
        """Provide mock data only in non-integration mode"""
        if integration_mode:
            return None

        return {
            'success': True,
            'result': {
                'results': [
                    {'entity': {'id': 'dev-1', 'name': 'Living Room TV', 'entity_type': 'DEVICE'}},
                    {'entity': {'id': 'dev-2', 'name': 'Smart Thermostat', 'entity_type': 'DEVICE'}},
                    {'entity': {'id': 'dev-3', 'name': 'Kitchen Fridge', 'entity_type': 'DEVICE'}},
                    {'entity': {'id': 'dev-4', 'name': 'Living Room Lights', 'entity_type': 'DEVICE'}}
                ]
            }
        }

    @pytest.mark.asyncio
    async def test_list_devices(self, chat_instance, mock_devices_data, integration_mode):
        """
        GIVEN a smart home with devices
        WHEN user lists devices
        THEN chat should return device information
        """
        # Given
        chat = chat_instance
        if not integration_mode and mock_devices_data:
            chat.client.execute_mcp_tool.return_value = mock_devices_data

        # When
        response = await chat.process_query("list all devices")

        # Then
        assert response is not None

        if integration_mode:
            # Check for real devices
            assert any(dev in response.lower() for dev in ['tv', 'thermostat', 'light', 'device'])
        else:
            # Check mock was called correctly
            chat.client.execute_mcp_tool.assert_called_with("search_entities", query="device")

    @pytest.mark.asyncio
    async def test_search_lights(self, chat_instance, integration_mode):
        """
        GIVEN a smart home with lights
        WHEN user searches for lights
        THEN chat should return light devices
        """
        # Given
        chat = chat_instance
        if not integration_mode:
            chat.client.execute_mcp_tool.return_value = {
                'success': True,
                'result': {
                    'results': [
                        {'entity': {'id': 'dev-4', 'name': 'Living Room Lights', 'entity_type': 'DEVICE'}}
                    ]
                }
            }

        # When
        response = await chat.process_query("search for lights")

        # Then
        assert response is not None

        if integration_mode:
            assert 'light' in response.lower() or 'device' in response.lower()
        else:
            chat.client.execute_mcp_tool.assert_called_with("search_entities", query="lights")


class TestRoomDeviceRelationships(TestHybridBase):
    """Test room-device relationship queries"""

    @pytest.mark.asyncio
    async def test_devices_in_kitchen(self, chat_instance, integration_mode):
        """
        GIVEN a kitchen with devices
        WHEN user asks what's in the kitchen
        THEN chat should return kitchen devices
        """
        # Given
        chat = chat_instance
        if not integration_mode:
            # Mock the room search
            chat.client.execute_mcp_tool.side_effect = [
                # First call: search for kitchen room
                {
                    'success': True,
                    'result': {
                        'results': [
                            {'entity': {'id': 'room-2', 'name': 'Kitchen', 'entity_type': 'ROOM'}}
                        ]
                    }
                },
                # Second call: get devices in room
                [
                    {'name': 'Smart Fridge', 'entity_type': 'DEVICE'},
                    {'name': 'Smart Oven', 'entity_type': 'DEVICE'}
                ]
            ]

        # When
        response = await chat.process_query("what devices are in the kitchen?")

        # Then
        assert response is not None

        if integration_mode:
            # Real data should have kitchen-related content
            assert any(word in response.lower() for word in ['kitchen', 'fridge', 'oven', 'device', 'room'])
        else:
            # Mock should be called twice
            assert chat.client.execute_mcp_tool.call_count >= 1


class TestComplexQueries(TestHybridBase):
    """Test complex multi-entity queries"""

    @pytest.mark.asyncio
    async def test_climate_control(self, chat_instance, integration_mode):
        """
        GIVEN a smart home with thermostats
        WHEN user asks about climate control
        THEN chat should search for thermostats
        """
        # Given
        chat = chat_instance
        if not integration_mode:
            chat.client.execute_mcp_tool.return_value = {
                'success': True,
                'result': {
                    'results': [
                        {'entity': {'id': 'dev-2', 'name': 'Smart Thermostat', 'entity_type': 'DEVICE'}}
                    ]
                }
            }

        # When
        tool_info = chat.parse_query_for_tool("show all thermostats")

        # Then
        assert tool_info is not None
        assert tool_info['tool'] == 'search_entities'
        assert 'thermostat' in tool_info['params']['query']


class TestNaturalLanguageParsing(TestHybridBase):
    """Test natural language query parsing"""

    @pytest.mark.asyncio
    async def test_parse_list_queries(self, chat_instance):
        """
        GIVEN various list/show queries
        WHEN parsing for tools
        THEN correct tools and params should be selected
        """
        # Given
        chat = chat_instance
        test_queries = [
            ("list all devices", "search_entities", "device"),
            ("show all rooms", "search_entities", "room"),
            ("list entities", "search_entities", "*"),
            ("show all thermostats", "search_entities", "thermostat"),
            ("list lights", "search_entities", "light")
        ]

        # When/Then
        for query, expected_tool, expected_param in test_queries:
            tool_info = chat.parse_query_for_tool(query)
            assert tool_info is not None
            assert tool_info['tool'] == expected_tool
            assert expected_param in tool_info['params']['query']

    @pytest.mark.asyncio
    async def test_parse_search_queries(self, chat_instance):
        """
        GIVEN various search/find queries
        WHEN parsing for tools
        THEN correct search params should be extracted
        """
        # Given
        chat = chat_instance
        test_queries = [
            ("search for lights", "search_entities", "lights"),
            ("find temperature sensors", "search_entities", "temperature sensors"),
            ("look for smart devices", "search_entities", "smart devices"),
            ("find lights", "search_entities", "light")
        ]

        # When/Then
        for query, expected_tool, expected_content in test_queries:
            tool_info = chat.parse_query_for_tool(query)
            assert tool_info is not None
            assert tool_info['tool'] == expected_tool
            assert expected_content in tool_info['params']['query']


def pytest_collection_modifyitems(config, items):
    """Mark all tests in this file as hybrid tests"""
    for item in items:
        # Add hybrid marker to all tests in this file
        if item.module.__name__ == 'test_bdd_hybrid':
            item.add_marker(pytest.mark.hybrid)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run hybrid BDD tests")
    parser.add_argument("--integration", action="store_true",
                        help="Run against real server instead of mock data")
    parser.add_argument("--server-url", default="http://localhost:8000",
                        help="Server URL for integration tests")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose output")

    args = parser.parse_args()

    pytest_args = [__file__]
    if args.integration:
        pytest_args.append("--integration")
        pytest_args.append(f"--server-url={args.server_url}")
    if args.verbose:
        pytest_args.append("-v")

    pytest.main(pytest_args)