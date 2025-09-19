"""
Query Processor for Natural Language Understanding
==================================================

Processes natural language queries to determine MCP tool and parameters.
"""

import re
from dataclasses import dataclass
from typing import Dict, Optional, List, Any


@dataclass
class QueryIntent:
    """Represents the intent extracted from a query"""
    tool: Optional[str] = None
    params: Dict[str, Any] = None
    confidence: float = 0.0
    query_type: str = 'general'


class QueryProcessor:
    """Process natural language queries to MCP tool calls"""

    # Query patterns mapped to tools and extraction logic
    PATTERNS = {
        'list_all_devices': {
            'patterns': ['show all devices', 'list all devices', 'all devices',
                        'show devices', 'list devices'],
            'tool': 'list_entities',
            'params': {'entity_type': 'DEVICE'}
        },
        'list_rooms': {
            'patterns': ['show rooms', 'list rooms', 'all rooms',
                        'show all rooms', 'list all rooms'],
            'tool': 'list_entities',
            'params': {'entity_type': 'ROOM'}
        },
        'devices_in_room': {
            'patterns': ['in the', "what's in", 'devices in', 'show .* room',
                        'list .* room'],
            'tool': 'get_devices_in_room',
            'extract_room': True
        },
        'search_devices': {
            'patterns': ['find', 'search', 'look for', 'show .* devices',
                        'list .* devices', 'find all'],
            'tool': 'search_entities',
            'extract_search': True
        },
        'device_details': {
            'patterns': ['tell me about', 'details of', 'information about',
                        'describe', 'what is'],
            'tool': 'get_entity',
            'extract_entity': True
        },
        'similar_devices': {
            'patterns': ['similar to', 'like', 'same as', 'devices like'],
            'tool': 'find_similar_entities',
            'extract_entity': True
        }
    }

    # Common room names to look for
    ROOM_NAMES = [
        'living room', 'bedroom', 'kitchen', 'bathroom', 'garage',
        'office', 'basement', 'attic', 'dining room', 'hallway',
        'master bedroom', 'guest room', 'laundry', 'pantry'
    ]

    # Device types to recognize
    DEVICE_TYPES = [
        'light', 'lights', 'thermostat', 'lock', 'locks', 'camera', 'cameras',
        'sensor', 'sensors', 'switch', 'switches', 'outlet', 'outlets',
        'fan', 'fans', 'blind', 'blinds', 'door', 'window', 'motion',
        'temperature', 'humidity', 'smoke', 'carbon monoxide'
    ]

    def analyze(self, query: str) -> QueryIntent:
        """
        Analyze query and determine MCP tool to use

        Args:
            query: Natural language query

        Returns:
            QueryIntent with tool and parameters
        """
        query_lower = query.lower().strip()

        # Try to match patterns
        for intent_type, config in self.PATTERNS.items():
            for pattern in config['patterns']:
                if self._matches_pattern(query_lower, pattern):
                    return self._build_intent(query_lower, config, intent_type)

        # Default fallback - try searching
        return self._build_search_intent(query_lower)

    def _matches_pattern(self, query: str, pattern: str) -> bool:
        """Check if query matches pattern"""
        # Handle regex patterns
        if '.*' in pattern:
            return bool(re.search(pattern, query))
        # Handle exact phrase matching
        return pattern in query

    def _build_intent(self, query: str, config: Dict, intent_type: str) -> QueryIntent:
        """Build intent from matched pattern configuration"""
        intent = QueryIntent(
            tool=config['tool'],
            params=config.get('params', {}).copy(),
            query_type=intent_type,
            confidence=0.8
        )

        # Extract additional parameters based on config
        if config.get('extract_room'):
            room = self._extract_room(query)
            if room:
                intent.params = {'room_id': room}
                intent.confidence = 0.9

        elif config.get('extract_search'):
            search_term = self._extract_search_term(query)
            if search_term:
                intent.params = {'query': search_term}
                # Add entity type if we can detect it
                if any(device_type in search_term for device_type in self.DEVICE_TYPES):
                    intent.params['entity_type'] = 'DEVICE'
                intent.confidence = 0.85

        elif config.get('extract_entity'):
            entity_name = self._extract_entity_name(query)
            if entity_name:
                intent.params = {'name': entity_name}
                intent.confidence = 0.8

        return intent

    def _extract_room(self, query: str) -> Optional[str]:
        """Extract room name from query"""
        # Check for known room names
        for room in self.ROOM_NAMES:
            if room in query:
                # Return a pattern that can match partial room names
                return f"*{room}*"

        # Try to extract custom room names after "in the"
        match = re.search(r'in the ([a-z\s]+)(?:\s|$)', query)
        if match:
            return f"*{match.group(1).strip()}*"

        return None

    def _extract_search_term(self, query: str) -> Optional[str]:
        """Extract search term from query"""
        # Remove common prefixes
        prefixes = ['find all ', 'search for ', 'look for ', 'find ', 'search ',
                   'show all ', 'list all ', 'show ', 'list ']

        search_query = query
        for prefix in prefixes:
            if query.startswith(prefix):
                search_query = query[len(prefix):]
                break

        # Remove common suffixes
        suffixes = [' devices', ' in the house', ' in my home', ' please']
        for suffix in suffixes:
            if search_query.endswith(suffix):
                search_query = search_query[:-len(suffix)]

        return search_query.strip() if search_query else None

    def _extract_entity_name(self, query: str) -> Optional[str]:
        """Extract entity name from query"""
        # Try patterns like "tell me about [entity]"
        patterns = [
            r'tell me about (?:the )?([a-z\s]+)',
            r'details (?:of|about) (?:the )?([a-z\s]+)',
            r'information (?:on|about) (?:the )?([a-z\s]+)',
            r'describe (?:the )?([a-z\s]+)',
            r'what is (?:the )?([a-z\s]+)',
            r'similar to (?:the )?([a-z\s]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1).strip()

        return None

    def _build_search_intent(self, query: str) -> QueryIntent:
        """Build a default search intent as fallback"""
        # Extract any meaningful terms from the query
        # Remove common words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'what', 'which',
                     'show', 'me', 'list', 'find', 'please', 'can', 'you'}

        words = query.split()
        search_terms = [w for w in words if w not in stop_words]

        if search_terms:
            return QueryIntent(
                tool='search_entities',
                params={'query': ' '.join(search_terms)},
                query_type='search',
                confidence=0.6
            )

        # Last resort - list all entities
        return QueryIntent(
            tool='list_entities',
            params={},
            query_type='list_all',
            confidence=0.4
        )

    def get_suggested_queries(self) -> List[str]:
        """Get list of example queries that can be processed"""
        return [
            "Show all devices",
            "List all rooms",
            "What's in the living room?",
            "Find all lights",
            "Search for temperature sensors",
            "Tell me about the smart thermostat",
            "Find devices similar to the bedroom light",
            "Show all smart locks",
            "List devices in the kitchen",
            "Find motion sensors"
        ]