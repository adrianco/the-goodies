"""
MCP Tool Definitions for FunkyGibbon

This module defines the tools available through the MCP protocol
for interacting with the knowledge graph.
"""

from typing import Dict, Any, List

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_devices_in_room",
        "description": "Get all devices located in a specific room",
        "parameters": {
            "type": "object",
            "properties": {
                "room_id": {
                    "type": "string",
                    "description": "The ID of the room entity"
                }
            },
            "required": ["room_id"]
        }
    },
    {
        "name": "find_device_controls",
        "description": "Get available controls and services for a device",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The ID of the device entity"
                }
            },
            "required": ["device_id"]
        }
    },
    {
        "name": "get_room_connections",
        "description": "Find doors, windows, and passages between rooms",
        "parameters": {
            "type": "object",
            "properties": {
                "room_id": {
                    "type": "string",
                    "description": "The ID of the room entity"
                }
            },
            "required": ["room_id"]
        }
    },
    {
        "name": "search_entities",
        "description": "Search for entities by name or content",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string"
                },
                "entity_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["home", "room", "device", "zone", "door", "window",
                                "procedure", "manual", "note", "schedule", "automation"]
                    },
                    "description": "Filter by entity types (optional)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_entity",
        "description": "Create a new entity in the knowledge graph",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["home", "room", "device", "zone", "door", "window",
                            "procedure", "manual", "note", "schedule", "automation"],
                    "description": "Type of entity to create"
                },
                "name": {
                    "type": "string",
                    "description": "Name of the entity"
                },
                "content": {
                    "type": "object",
                    "description": "Additional properties for the entity",
                    "additionalProperties": True
                }
            },
            "required": ["entity_type", "name"]
        }
    },
    {
        "name": "create_relationship",
        "description": "Create a relationship between two entities",
        "parameters": {
            "type": "object",
            "properties": {
                "from_entity_id": {
                    "type": "string",
                    "description": "ID of the source entity"
                },
                "to_entity_id": {
                    "type": "string",
                    "description": "ID of the target entity"
                },
                "relationship_type": {
                    "type": "string",
                    "enum": ["located_in", "controls", "connects_to", "part_of",
                            "manages", "documented_by", "procedure_for", "triggered_by",
                            "depends_on", "contained_in", "monitors", "automates"],
                    "description": "Type of relationship"
                },
                "properties": {
                    "type": "object",
                    "description": "Additional properties for the relationship",
                    "additionalProperties": True
                }
            },
            "required": ["from_entity_id", "to_entity_id", "relationship_type"]
        }
    },
    {
        "name": "find_path",
        "description": "Find the shortest path between two entities",
        "parameters": {
            "type": "object",
            "properties": {
                "from_entity_id": {
                    "type": "string",
                    "description": "Starting entity ID"
                },
                "to_entity_id": {
                    "type": "string",
                    "description": "Target entity ID"
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum search depth (default: 10)",
                    "default": 10
                }
            },
            "required": ["from_entity_id", "to_entity_id"]
        }
    },
    {
        "name": "get_entity_details",
        "description": "Get detailed information about an entity",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "The ID of the entity"
                },
                "include_relationships": {
                    "type": "boolean",
                    "description": "Include incoming and outgoing relationships",
                    "default": True
                },
                "include_connected": {
                    "type": "boolean",
                    "description": "Include directly connected entities",
                    "default": False
                }
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "find_similar_entities",
        "description": "Find entities similar to a given entity",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Reference entity ID"
                },
                "threshold": {
                    "type": "number",
                    "description": "Similarity threshold (0-1)",
                    "default": 0.7,
                    "minimum": 0,
                    "maximum": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10
                }
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "get_procedures_for_device",
        "description": "Get all procedures and manuals for a specific device",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The ID of the device"
                }
            },
            "required": ["device_id"]
        }
    },
    {
        "name": "get_automations_in_room",
        "description": "Get all automations that affect devices in a room",
        "parameters": {
            "type": "object",
            "properties": {
                "room_id": {
                    "type": "string",
                    "description": "The ID of the room"
                }
            },
            "required": ["room_id"]
        }
    },
    {
        "name": "update_entity",
        "description": "Update an entity (creates new version)",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "The ID of the entity to update"
                },
                "changes": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "New name (optional)"
                        },
                        "content": {
                            "type": "object",
                            "description": "Content updates (merged with existing)",
                            "additionalProperties": True
                        }
                    }
                },
                "user_id": {
                    "type": "string",
                    "description": "ID of the user making the change"
                }
            },
            "required": ["entity_id", "changes", "user_id"]
        }
    }
]
