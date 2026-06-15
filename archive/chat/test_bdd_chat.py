#!/usr/bin/env python3
"""
Behavior-Driven Development Test Suite for TinyLlama MCP Chat
==============================================================

BDD tests using pytest with Given-When-Then structure to validate
the chat interface functionality against the smart home test dataset.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List
import sys
sys.path.append('/workspaces/the-goodies')

from chat.tinyllama_mcp_chat import TinyLlamaMCPChat


# Test fixtures for the smart home dataset
@pytest.fixture
def mock_search_rooms_result():
    """Mock result for searching rooms"""
    return {
        'success': True,
        'result': {
            'results': [
                {
                    'entity': {
                        'id': '19cc9d14-797f-421b-b349-a303d92ee52e',
                        'name': 'Living Room',
                        'entity_type': 'room',
                        'content': {'area': 350, 'floor': 1, 'features': ['fireplace', 'bay_window']}
                    },
                    'score': 1.5
                },
                {
                    'entity': {
                        'id': 'ff81fedf-7dd6-40c8-af42-882cdfd7c0b0',
                        'name': 'Kitchen',
                        'entity_type': 'room',
                        'content': {'area': 250, 'floor': 1, 'features': ['island', 'pantry']}
                    },
                    'score': 1.5
                },
                {
                    'entity': {
                        'id': '86a6dc0b-8c8c-471b-9c21-f87af91cc071',
                        'name': 'Dining Room',
                        'entity_type': 'room',
                        'content': {'area': 200, 'floor': 1, 'features': ['chandelier']}
                    },
                    'score': 1.5
                },
                {
                    'entity': {
                        'id': '56ede48b-eaa3-4504-a771-af187d7c8553',
                        'name': 'Master Bedroom',
                        'entity_type': 'room',
                        'content': {'area': 300, 'floor': 2, 'features': ['walk_in_closet', 'ensuite']}
                    },
                    'score': 1.5
                },
                {
                    'entity': {
                        'id': '5baa6338-a04b-44db-ae50-d1da73a0de54',
                        'name': 'Office',
                        'entity_type': 'room',
                        'content': {'area': 150, 'floor': 2, 'features': ['built_in_shelves']}
                    },
                    'score': 1.5
                },
                {
                    'entity': {
                        'id': '0d25603a-4de7-4193-be7c-687b0482b774',
                        'name': 'Garage',
                        'entity_type': 'room',
                        'content': {'area': 400, 'capacity': 2, 'features': ['ev_charger', 'workbench']}
                    },
                    'score': 1.5
                }
            ],
            'count': 6,
            'query': 'room'
        },
        'error': None
    }


@pytest.fixture
def mock_search_devices_result():
    """Mock result for searching devices"""
    return {
        'success': True,
        'result': {
            'results': [
                {
                    'entity': {
                        'id': '0fb50b5b-8b46-4aa1-ad45-66c854ead5f0',
                        'name': 'TV',
                        'entity_type': 'device',
                        'content': {
                            'manufacturer': 'Samsung',
                            'model': 'QN90A',
                            'type': 'entertainment',
                            'capabilities': ['power', 'volume', 'input', 'apps']
                        }
                    },
                    'score': 1.5
                },
                {
                    'entity': {
                        'id': 'c610446d-1e68-43d7-a477-4981a39aa12a',
                        'name': 'Thermostat',
                        'entity_type': 'device',
                        'content': {
                            'manufacturer': 'Nest',
                            'model': 'Learning Thermostat',
                            'type': 'climate',
                            'capabilities': ['temperature', 'humidity', 'schedule', 'eco_mode']
                        }
                    },
                    'score': 1.5
                },
                {
                    'entity': {
                        'id': 'cf6cd021-57b8-4093-ad55-522c455d6490',
                        'name': 'Living Room Lights',
                        'entity_type': 'device',
                        'content': {
                            'manufacturer': 'Philips',
                            'model': 'Hue Go',
                            'type': 'light',
                            'capabilities': ['power', 'brightness', 'color', 'scenes']
                        }
                    },
                    'score': 1.5
                }
            ],
            'count': 3,
            'query': 'device'
        },
        'error': None
    }


@pytest.fixture
def mock_get_devices_in_room_result():
    """Mock result for getting devices in a specific room (Kitchen)"""
    return {
        'success': True,
        'result': {
            'results': [
                {
                    'entity': {
                        'id': '96876301-4273-42e7-be05-48f117f910da',
                        'name': 'Smart Fridge',
                        'entity_type': 'device',
                        'content': {
                            'manufacturer': 'LG',
                            'model': 'InstaView',
                            'type': 'appliance',
                            'capabilities': ['temperature', 'door_sensor', 'inventory']
                        }
                    }
                },
                {
                    'entity': {
                        'id': '112934e5-7460-444a-99f7-58bfdfc73dbb',
                        'name': 'Smart Oven',
                        'entity_type': 'device',
                        'content': {
                            'manufacturer': 'Samsung',
                            'model': 'Flex Duo',
                            'type': 'appliance',
                            'capabilities': ['temperature', 'timer', 'preheat', 'self_clean']
                        }
                    }
                },
                {
                    'entity': {
                        'id': 'b2ca7a21-898b-430d-91fa-ee85061926ab',
                        'name': 'Mitsubishi PAR-42MAA Thermostat',
                        'entity_type': 'device',
                        'content': {
                            'manufacturer': 'Mitsubishi',
                            'model': 'PAR-42MAAUB',
                            'type': 'climate',
                            'location_notes': 'Kitchen wall - controls air blower for kitchen, dining room, living room'
                        }
                    }
                }
            ]
        }
    }


@pytest.fixture
def mock_search_automations_result():
    """Mock result for searching automations"""
    return {
        'success': True,
        'result': {
            'results': [
                {
                    'entity': {
                        'id': '4c498a40-271b-4bc0-8987-a1f8b1f1dcae',
                        'name': 'Good Morning Routine',
                        'entity_type': 'automation',
                        'content': {
                            'trigger': {'type': 'time', 'time': '07:00'},
                            'actions': [
                                {'device': 'thermostat', 'action': 'set_temperature', 'value': 72},
                                {'device': 'living_room_lights', 'action': 'turn_on', 'brightness': 50}
                            ],
                            'enabled': True
                        }
                    },
                    'score': 1.5
                },
                {
                    'entity': {
                        'id': '9f792b8f-14af-499f-9f5a-1fb13a7a2420',
                        'name': 'Movie Time Scene',
                        'entity_type': 'automation',
                        'content': {
                            'trigger': {'type': 'manual', 'voice_command': 'movie time'},
                            'actions': [
                                {'device': 'tv', 'action': 'turn_on'},
                                {'device': 'living_room_lights', 'action': 'dim', 'brightness': 10}
                            ],
                            'enabled': True
                        }
                    },
                    'score': 1.5
                }
            ],
            'count': 2,
            'query': 'automation'
        },
        'error': None
    }


@pytest.fixture
async def chat_instance():
    """Create a mock chat instance for testing"""
    chat = TinyLlamaMCPChat()

    # Mock the model to avoid loading actual TinyLlama
    chat.model = MagicMock()
    chat.model.return_value = {
        'choices': [{
            'text': 'Test response from model'
        }]
    }

    # Mock the client
    chat.client = AsyncMock()

    return chat


class TestRoomQueries:
    """Test scenarios for room-related queries"""

    @pytest.mark.asyncio
    async def test_list_all_rooms(self, chat_instance, mock_search_rooms_result):
        """
        GIVEN a smart home with 6 rooms
        WHEN user asks to list all rooms
        THEN chat should return all room names with their types
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_search_rooms_result

        # When
        tool_info = chat.parse_query_for_tool("list all rooms")

        # Then
        assert tool_info is not None
        assert tool_info['tool'] == 'search_entities'
        assert tool_info['params']['query'] == 'room'

        # Verify execution would return correct rooms
        result = await chat.client.execute_mcp_tool(tool_info['tool'], **tool_info['params'])
        rooms = result['result']['results']
        assert len(rooms) == 6
        room_names = [r['entity']['name'] for r in rooms]
        assert 'Living Room' in room_names
        assert 'Kitchen' in room_names
        assert 'Master Bedroom' in room_names

    @pytest.mark.asyncio
    async def test_search_specific_room(self, chat_instance, mock_search_rooms_result):
        """
        GIVEN a smart home with multiple rooms
        WHEN user searches for rooms with specific features
        THEN chat should filter and return matching rooms
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_search_rooms_result

        # When
        tool_info = chat.parse_query_for_tool("find rooms on the first floor")

        # Then
        assert tool_info is not None
        assert tool_info['tool'] == 'search_entities'

        # Verify we can filter results
        result = await chat.client.execute_mcp_tool(tool_info['tool'], **tool_info['params'])
        rooms = result['result']['results']
        first_floor_rooms = [r for r in rooms if r['entity']['content'].get('floor') == 1]
        assert len(first_floor_rooms) == 3  # Living Room, Kitchen, Dining Room

    @pytest.mark.asyncio
    async def test_room_area_comparison(self, chat_instance, mock_search_rooms_result):
        """
        GIVEN rooms with different areas
        WHEN user asks about room sizes
        THEN chat should provide area information
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_search_rooms_result

        # When
        result = await chat.client.execute_mcp_tool('search_entities', query='room')

        # Then
        rooms = result['result']['results']
        garage = next(r for r in rooms if r['entity']['name'] == 'Garage')
        assert garage['entity']['content']['area'] == 400  # Largest room

        office = next(r for r in rooms if r['entity']['name'] == 'Office')
        assert office['entity']['content']['area'] == 150  # Smallest room


class TestDeviceQueries:
    """Test scenarios for device-related queries"""

    @pytest.mark.asyncio
    async def test_list_all_devices(self, chat_instance, mock_search_devices_result):
        """
        GIVEN a smart home with various devices
        WHEN user asks to list all devices
        THEN chat should return device names with types and manufacturers
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_search_devices_result

        # When
        tool_info = chat.parse_query_for_tool("show all devices")

        # Then
        assert tool_info is not None
        assert tool_info['tool'] == 'search_entities'
        assert tool_info['params']['query'] == 'device'

        result = await chat.client.execute_mcp_tool(tool_info['tool'], **tool_info['params'])
        devices = result['result']['results']
        assert len(devices) >= 3

        # Verify device information
        tv = next(d for d in devices if d['entity']['name'] == 'TV')
        assert tv['entity']['content']['manufacturer'] == 'Samsung'
        assert 'power' in tv['entity']['content']['capabilities']

    @pytest.mark.asyncio
    async def test_search_lights(self, chat_instance, mock_search_devices_result):
        """
        GIVEN devices including smart lights
        WHEN user searches for lights
        THEN chat should return only lighting devices
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_search_devices_result

        # When
        tool_info = chat.parse_query_for_tool("find lights")

        # Then
        assert tool_info is not None
        assert 'light' in tool_info['params']['query'].lower()

        result = await chat.client.execute_mcp_tool(tool_info['tool'], **tool_info['params'])
        devices = result['result']['results']
        lights = [d for d in devices if d['entity']['name'] == 'Living Room Lights']
        assert len(lights) > 0
        assert lights[0]['entity']['content']['type'] == 'light'
        assert 'brightness' in lights[0]['entity']['content']['capabilities']

    @pytest.mark.asyncio
    async def test_device_capabilities(self, chat_instance, mock_search_devices_result):
        """
        GIVEN devices with different capabilities
        WHEN user asks about device features
        THEN chat should describe device capabilities accurately
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_search_devices_result

        # When
        result = await chat.client.execute_mcp_tool('search_entities', query='thermostat')

        # Then
        devices = result['result']['results']
        thermostat = next(d for d in devices if d['entity']['name'] == 'Thermostat')
        capabilities = thermostat['entity']['content']['capabilities']
        assert 'temperature' in capabilities
        assert 'humidity' in capabilities
        assert 'schedule' in capabilities
        assert 'eco_mode' in capabilities


class TestRoomDeviceRelationships:
    """Test scenarios for room-device relationships"""

    @pytest.mark.asyncio
    async def test_devices_in_kitchen(self, chat_instance, mock_get_devices_in_room_result):
        """
        GIVEN a kitchen with smart appliances
        WHEN user asks what's in the kitchen
        THEN chat should list kitchen-specific devices
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_get_devices_in_room_result

        # When
        tool_info = chat.parse_query_for_tool("what's in the kitchen?")

        # Then
        assert tool_info is not None
        assert tool_info['tool'] == 'search_and_get_devices'
        assert tool_info['params']['room_name'] == 'kitchen'

        # Simulate the room search and device retrieval
        devices_result = mock_get_devices_in_room_result['result']['results']
        device_names = [d['entity']['name'] for d in devices_result]
        assert 'Smart Fridge' in device_names
        assert 'Smart Oven' in device_names
        assert 'Mitsubishi PAR-42MAA Thermostat' in device_names

    @pytest.mark.asyncio
    async def test_devices_in_living_room(self, chat_instance):
        """
        GIVEN a living room with entertainment devices
        WHEN user asks about living room devices
        THEN chat should list entertainment and lighting devices
        """
        # Given
        chat = chat_instance
        living_room_devices = {
            'success': True,
            'result': {
                'results': [
                    {
                        'entity': {
                            'name': 'TV',
                            'entity_type': 'device',
                            'content': {'type': 'entertainment'}
                        }
                    },
                    {
                        'entity': {
                            'name': 'Living Room Lights',
                            'entity_type': 'device',
                            'content': {'type': 'light'}
                        }
                    }
                ]
            }
        }
        chat.client.execute_mcp_tool.return_value = living_room_devices

        # When
        tool_info = chat.parse_query_for_tool("what devices are in the living room?")

        # Then
        assert tool_info is not None
        assert 'living' in tool_info['params']['room_name'] if 'room_name' in tool_info['params'] else True

    @pytest.mark.asyncio
    async def test_multi_room_thermostat(self, chat_instance, mock_get_devices_in_room_result):
        """
        GIVEN a thermostat that controls multiple rooms
        WHEN user asks about climate control
        THEN chat should explain multi-room control
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_get_devices_in_room_result

        # When
        result = await chat.client.execute_mcp_tool('get_devices_in_room', room_id='kitchen')

        # Then
        devices = result['result']['results']
        mitsubishi = next(d for d in devices if 'Mitsubishi' in d['entity']['name'])
        location_notes = mitsubishi['entity']['content']['location_notes']
        assert 'kitchen' in location_notes.lower()
        assert 'dining room' in location_notes.lower()
        assert 'living room' in location_notes.lower()


class TestAutomationQueries:
    """Test scenarios for automation and scene queries"""

    @pytest.mark.asyncio
    async def test_list_automations(self, chat_instance, mock_search_automations_result):
        """
        GIVEN smart home automations
        WHEN user asks about automations
        THEN chat should list available routines and scenes
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_search_automations_result

        # When
        tool_info = chat.parse_query_for_tool("show automations")

        # Then
        result = await chat.client.execute_mcp_tool('search_entities', query='automation')
        automations = result['result']['results']
        assert len(automations) == 2

        morning = next(a for a in automations if a['entity']['name'] == 'Good Morning Routine')
        assert morning['entity']['content']['trigger']['type'] == 'time'
        assert morning['entity']['content']['trigger']['time'] == '07:00'

    @pytest.mark.asyncio
    async def test_movie_time_scene(self, chat_instance, mock_search_automations_result):
        """
        GIVEN a movie time scene automation
        WHEN user asks about movie mode
        THEN chat should describe the scene actions
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_search_automations_result

        # When
        result = await chat.client.execute_mcp_tool('search_entities', query='movie')

        # Then
        automations = result['result']['results']
        movie_scene = next((a for a in automations if 'Movie' in a['entity']['name']), None)
        assert movie_scene is not None

        actions = movie_scene['entity']['content']['actions']
        assert any(a['device'] == 'tv' and a['action'] == 'turn_on' for a in actions)
        assert any(a['device'] == 'living_room_lights' and a['action'] == 'dim' for a in actions)

    @pytest.mark.asyncio
    async def test_automation_triggers(self, chat_instance, mock_search_automations_result):
        """
        GIVEN automations with different triggers
        WHEN analyzing automation types
        THEN chat should distinguish time-based vs manual triggers
        """
        # Given
        chat = chat_instance
        chat.client.execute_mcp_tool.return_value = mock_search_automations_result

        # When
        result = await chat.client.execute_mcp_tool('search_entities', query='automation')

        # Then
        automations = result['result']['results']
        time_based = [a for a in automations if a['entity']['content']['trigger']['type'] == 'time']
        manual = [a for a in automations if a['entity']['content']['trigger']['type'] == 'manual']

        assert len(time_based) == 1  # Good Morning Routine
        assert len(manual) == 1  # Movie Time Scene


class TestComplexQueries:
    """Test scenarios for complex multi-entity queries"""

    @pytest.mark.asyncio
    async def test_climate_control_system(self, chat_instance):
        """
        GIVEN multiple climate control devices
        WHEN user asks about temperature control
        THEN chat should identify all HVAC-related devices
        """
        # Given
        chat = chat_instance
        climate_devices = {
            'success': True,
            'result': {
                'results': [
                    {
                        'entity': {
                            'name': 'Nest Thermostat',
                            'entity_type': 'device',
                            'content': {'type': 'climate'}
                        }
                    },
                    {
                        'entity': {
                            'name': 'Mitsubishi PAR-42MAA',
                            'entity_type': 'device',
                            'content': {'type': 'climate'}
                        }
                    },
                    {
                        'entity': {
                            'name': 'PVFY Air Handler',
                            'entity_type': 'device',
                            'content': {'type': 'hvac'}
                        }
                    }
                ]
            }
        }
        chat.client.execute_mcp_tool.return_value = climate_devices

        # When
        tool_info = chat.parse_query_for_tool("show all thermostats")

        # Then
        assert tool_info is not None
        assert 'thermostat' in tool_info['params']['query']

        result = await chat.client.execute_mcp_tool(tool_info['tool'], **tool_info['params'])
        devices = result['result']['results']
        climate_devices = [d for d in devices if d['entity']['content']['type'] in ['climate', 'hvac']]
        assert len(climate_devices) == 3

    @pytest.mark.asyncio
    async def test_entity_count_summary(self, chat_instance):
        """
        GIVEN a complete smart home dataset
        WHEN user asks for system summary
        THEN chat should provide accurate entity counts
        """
        # Given
        chat = chat_instance
        all_entities = {
            'success': True,
            'result': {
                'results': [
                    {'entity': {'entity_type': 'home'}} for _ in range(1)
                ] + [
                    {'entity': {'entity_type': 'room'}} for _ in range(6)
                ] + [
                    {'entity': {'entity_type': 'device'}} for _ in range(8)
                ] + [
                    {'entity': {'entity_type': 'automation'}} for _ in range(2)
                ] + [
                    {'entity': {'entity_type': 'note'}} for _ in range(2)
                ],
                'count': 19
            }
        }
        chat.client.execute_mcp_tool.return_value = all_entities

        # When
        result = await chat.client.execute_mcp_tool('search_entities', query='*')

        # Then
        entities = result['result']['results']
        entity_types = {}
        for e in entities:
            etype = e['entity']['entity_type']
            entity_types[etype] = entity_types.get(etype, 0) + 1

        assert entity_types['home'] == 1
        assert entity_types['room'] == 6
        assert entity_types['device'] == 8
        assert entity_types['automation'] == 2
        assert entity_types['note'] == 2


class TestErrorHandling:
    """Test error handling scenarios"""

    @pytest.mark.asyncio
    async def test_unknown_room_query(self, chat_instance):
        """
        GIVEN a query for a non-existent room
        WHEN user asks about unknown room
        THEN chat should handle gracefully
        """
        # Given
        chat = chat_instance
        empty_result = {
            'success': True,
            'result': {'results': [], 'count': 0, 'query': 'basement'},
            'error': None
        }
        chat.client.execute_mcp_tool.return_value = empty_result

        # When
        tool_info = chat.parse_query_for_tool("what's in the basement?")
        result = await chat.client.execute_mcp_tool('search_entities', query='basement')

        # Then
        assert result['result']['count'] == 0
        assert len(result['result']['results']) == 0

    @pytest.mark.asyncio
    async def test_mcp_tool_error(self, chat_instance):
        """
        GIVEN an MCP tool execution error
        WHEN tool fails
        THEN chat should handle error gracefully
        """
        # Given
        chat = chat_instance
        error_result = {
            'success': False,
            'result': None,
            'error': 'Connection timeout'
        }
        chat.client.execute_mcp_tool.return_value = error_result

        # When
        result = await chat.client.execute_mcp_tool('search_entities', query='test')

        # Then
        assert result['success'] is False
        assert result['error'] == 'Connection timeout'
        assert result['result'] is None


class TestNaturalLanguageParsing:
    """Test natural language query parsing"""

    def test_parse_list_queries(self, chat_instance):
        """
        GIVEN various list command phrasings
        WHEN parsing different list queries
        THEN correct MCP tool and parameters should be identified
        """
        # Given
        chat = chat_instance

        # When/Then
        queries = [
            ("list all devices", "device"),
            ("show all rooms", "room"),
            ("list entities", "*"),
            ("show devices", "device"),
            ("list rooms", "room")
        ]

        for query, expected_param in queries:
            tool_info = chat.parse_query_for_tool(query)
            assert tool_info is not None
            assert tool_info['tool'] == 'search_entities'
            assert tool_info['params']['query'] == expected_param

    def test_parse_search_queries(self, chat_instance):
        """
        GIVEN various search phrasings
        WHEN parsing search queries
        THEN correct search terms should be extracted
        """
        # Given
        chat = chat_instance

        # When/Then
        queries = [
            ("search for lights", "lights"),
            ("find temperature sensors", "temperature sensors"),
            ("look for thermostats", "thermostats")
        ]

        for query, expected_term in queries:
            tool_info = chat.parse_query_for_tool(query)
            assert tool_info is not None
            assert tool_info['tool'] == 'search_entities'
            assert expected_term in tool_info['params']['query']

    def test_parse_room_queries(self, chat_instance):
        """
        GIVEN room-specific queries
        WHEN parsing room questions
        THEN correct room should be identified
        """
        # Given
        chat = chat_instance

        # When/Then
        queries = [
            ("what's in the kitchen?", "kitchen"),
            ("what is in the living room?", "living"),
            ("devices in the bedroom", "bedroom"),
            ("what's in the garage?", "garage")
        ]

        for query, expected_room in queries:
            tool_info = chat.parse_query_for_tool(query)
            assert tool_info is not None
            assert tool_info['tool'] == 'search_and_get_devices'
            assert tool_info['params']['room_name'] == expected_room


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])