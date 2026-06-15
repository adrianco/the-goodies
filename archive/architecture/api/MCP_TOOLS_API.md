# MCP Tools API Specification

## Overview

This document defines the Model Context Protocol (MCP) tools exposed by WildThing and FunkyGibbon for AI assistants to interact with smart home knowledge graphs. These tools follow the MCP standard for seamless integration with AI systems.

## WildThing MCP Tools

### Query Tools

#### 1. get_devices_in_room

**Description**: Retrieve all devices located in a specific room.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "room_name": {
      "type": "string",
      "description": "Name of the room to query"
    },
    "device_types": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Optional filter by device types",
      "required": false
    },
    "include_offline": {
      "type": "boolean",
      "description": "Include offline devices",
      "default": true,
      "required": false
    }
  },
  "required": ["room_name"]
}
```

**Example Request**:
```json
{
  "room_name": "Living Room",
  "device_types": ["light", "switch"],
  "include_offline": false
}
```

**Example Response**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "Found 3 devices in Living Room:\n• Ceiling Light (light) - Online\n• Table Lamp (light) - Online\n• Wall Switch (switch) - Online"
    },
    {
      "type": "resource",
      "resource": {
        "uri": "wildthing://room/living-room/devices",
        "mimeType": "application/json",
        "text": "[{\"id\": \"device-123\", \"name\": \"Ceiling Light\", \"type\": \"light\", \"online\": true}]"
      }
    }
  ]
}
```

#### 2. find_device_controls

**Description**: Get available controls and current state for a specific device.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "device_name": {
      "type": "string",
      "description": "Name of the device"
    },
    "device_id": {
      "type": "string",
      "description": "Device ID (alternative to name)",
      "required": false
    }
  },
  "required": ["device_name"]
}
```

**Example Response**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "Controls for 'Living Room Light':\n• Power: on/off (currently: on)\n• Brightness: 0-100 (currently: 75)\n• Color Temperature: 2700-6500K (currently: 3000K)"
    },
    {
      "type": "resource",
      "resource": {
        "uri": "wildthing://device/device-123/controls",
        "mimeType": "application/json",
        "text": "{\"power\": {\"type\": \"boolean\", \"value\": true}, \"brightness\": {\"type\": \"integer\", \"min\": 0, \"max\": 100, \"value\": 75}}"
      }
    }
  ]
}
```

#### 3. get_room_connections

**Description**: Find doors, passages, and connections between rooms.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "from_room": {
      "type": "string",
      "description": "Starting room name"
    },
    "to_room": {
      "type": "string",
      "description": "Destination room name (optional)",
      "required": false
    }
  },
  "required": ["from_room"]
}
```

**Example Response**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "Connections from Living Room:\n• Kitchen (via archway)\n• Hallway (via door)\n• Dining Room (via French doors)"
    },
    {
      "type": "resource",
      "resource": {
        "uri": "wildthing://room/living-room/connections",
        "mimeType": "application/json",
        "text": "[{\"to\": \"Kitchen\", \"via\": \"archway\", \"type\": \"passage\"}]"
      }
    }
  ]
}
```

#### 4. search_entities

**Description**: Search for entities by name, content, or properties.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Search query"
    },
    "entity_types": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Filter by entity types",
      "required": false
    },
    "limit": {
      "type": "integer",
      "description": "Maximum results",
      "default": 20,
      "required": false
    }
  },
  "required": ["query"]
}
```

### Entity Management Tools

#### 5. create_entity

**Description**: Create a new entity in the home graph.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "entity_type": {
      "type": "string",
      "enum": ["home", "room", "device", "accessory", "service", "zone", "door", "window", "procedure", "manual", "note", "schedule", "automation"],
      "description": "Type of entity to create"
    },
    "name": {
      "type": "string",
      "description": "Name of the entity"
    },
    "properties": {
      "type": "object",
      "description": "Additional properties",
      "required": false
    },
    "location": {
      "type": "string",
      "description": "Room ID for devices",
      "required": false
    }
  },
  "required": ["entity_type", "name"]
}
```

**Example Request**:
```json
{
  "entity_type": "device",
  "name": "Smart Thermostat",
  "properties": {
    "manufacturer": "Nest",
    "model": "Learning Thermostat",
    "capabilities": ["temperature", "humidity", "scheduling"]
  },
  "location": "room-456"
}
```

#### 6. update_entity

**Description**: Update an existing entity's properties.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "entity_id": {
      "type": "string",
      "description": "Entity ID to update"
    },
    "updates": {
      "type": "object",
      "description": "Properties to update"
    },
    "merge": {
      "type": "boolean",
      "description": "Merge with existing properties",
      "default": true,
      "required": false
    }
  },
  "required": ["entity_id", "updates"]
}
```

#### 7. delete_entity

**Description**: Delete an entity from the home graph.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "entity_id": {
      "type": "string",
      "description": "Entity ID to delete"
    },
    "cascade": {
      "type": "boolean",
      "description": "Delete related entities",
      "default": false,
      "required": false
    }
  },
  "required": ["entity_id"]
}
```

### Relationship Tools

#### 8. create_relationship

**Description**: Create a relationship between two entities.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "from_entity_id": {
      "type": "string",
      "description": "Source entity ID"
    },
    "to_entity_id": {
      "type": "string",
      "description": "Target entity ID"
    },
    "relationship_type": {
      "type": "string",
      "enum": ["located_in", "controls", "connects_to", "part_of", "manages", "documented_by", "procedure_for", "triggered_by", "depends_on"],
      "description": "Type of relationship"
    },
    "properties": {
      "type": "object",
      "description": "Relationship properties",
      "required": false
    }
  },
  "required": ["from_entity_id", "to_entity_id", "relationship_type"]
}
```

#### 9. get_entity_relationships

**Description**: Get all relationships for an entity.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "entity_id": {
      "type": "string",
      "description": "Entity ID"
    },
    "direction": {
      "type": "string",
      "enum": ["from", "to", "both"],
      "description": "Relationship direction",
      "default": "both",
      "required": false
    },
    "relationship_types": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Filter by relationship types",
      "required": false
    }
  },
  "required": ["entity_id"]
}
```

### Content Management Tools

#### 10. add_device_manual

**Description**: Add documentation or manual for a device.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "device_id": {
      "type": "string",
      "description": "Device entity ID"
    },
    "title": {
      "type": "string",
      "description": "Manual title"
    },
    "content": {
      "type": "string",
      "description": "Manual content (markdown supported)"
    },
    "url": {
      "type": "string",
      "description": "External manual URL",
      "required": false
    }
  },
  "required": ["device_id", "title", "content"]
}
```

#### 11. create_procedure

**Description**: Create a step-by-step procedure.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "Procedure title"
    },
    "description": {
      "type": "string",
      "description": "Procedure description"
    },
    "steps": {
      "type": "array",
      "items": {"type": "string"},
      "description": "List of steps"
    },
    "category": {
      "type": "string",
      "description": "Procedure category",
      "default": "general",
      "required": false
    },
    "related_entities": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Related entity IDs",
      "required": false
    }
  },
  "required": ["title", "steps"]
}
```

**Example Request**:
```json
{
  "title": "Reset Smart Light",
  "description": "How to factory reset the smart light",
  "steps": [
    "Turn the light switch off",
    "Turn it on for 2 seconds",
    "Turn it off for 2 seconds",
    "Repeat 5 times",
    "Light will flash to confirm reset"
  ],
  "category": "troubleshooting",
  "related_entities": ["device-123"]
}
```

#### 12. add_device_image

**Description**: Add an image for a device.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "device_id": {
      "type": "string",
      "description": "Device entity ID"
    },
    "image_data": {
      "type": "string",
      "description": "Base64 encoded image data"
    },
    "file_name": {
      "type": "string",
      "description": "Image file name"
    },
    "content_type": {
      "type": "string",
      "description": "MIME type",
      "default": "image/jpeg",
      "required": false
    },
    "caption": {
      "type": "string",
      "description": "Image caption",
      "required": false
    }
  },
  "required": ["device_id", "image_data", "file_name"]
}
```

### Advanced Query Tools

#### 13. find_optimal_path

**Description**: Find the optimal path between two locations.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "from_location": {
      "type": "string",
      "description": "Starting location (room or device)"
    },
    "to_location": {
      "type": "string",
      "description": "Destination location"
    },
    "avoid": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Locations to avoid",
      "required": false
    },
    "accessibility": {
      "type": "boolean",
      "description": "Require accessible path",
      "default": false,
      "required": false
    }
  },
  "required": ["from_location", "to_location"]
}
```

#### 14. analyze_energy_usage

**Description**: Analyze energy consumption patterns.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "period": {
      "type": "string",
      "enum": ["day", "week", "month", "year"],
      "description": "Analysis period",
      "default": "week"
    },
    "entity_id": {
      "type": "string",
      "description": "Specific entity to analyze",
      "required": false
    },
    "group_by": {
      "type": "string",
      "enum": ["device", "room", "type", "hour", "day"],
      "description": "Grouping for analysis",
      "default": "device",
      "required": false
    }
  },
  "required": []
}
```

**Example Response**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "Energy Usage Analysis (Past Week):\n\nTop Consumers:\n1. HVAC System: 45.2 kWh (38%)\n2. Kitchen Appliances: 28.5 kWh (24%)\n3. Lighting: 15.3 kWh (13%)\n\nTotal: 118.7 kWh\nEstimated Cost: $14.24\n\nRecommendations:\n• Schedule HVAC for occupied hours only\n• Replace kitchen lights with LEDs"
    },
    {
      "type": "resource",
      "resource": {
        "uri": "wildthing://analytics/energy/week",
        "mimeType": "application/json",
        "text": "{\"total_kwh\": 118.7, \"by_device\": {...}, \"patterns\": {...}}"
      }
    }
  ]
}
```

#### 15. suggest_automations

**Description**: Get AI-powered automation suggestions based on usage patterns.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "focus_area": {
      "type": "string",
      "enum": ["energy_saving", "convenience", "security", "comfort", "all"],
      "description": "Type of automations to suggest",
      "default": "all"
    },
    "confidence_threshold": {
      "type": "number",
      "description": "Minimum confidence score (0-1)",
      "default": 0.7,
      "required": false
    }
  },
  "required": []
}
```

## FunkyGibbon MCP Tools (Extended)

### Sync Management Tools

#### 16. get_sync_status

**Description**: Get synchronization status for a device.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "device_id": {
      "type": "string",
      "description": "Device ID to check"
    }
  },
  "required": ["device_id"]
}
```

#### 17. resolve_sync_conflict

**Description**: Manually resolve a sync conflict.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "conflict_id": {
      "type": "string",
      "description": "Conflict ID"
    },
    "resolution": {
      "type": "string",
      "enum": ["keep_local", "keep_server", "merge", "custom"],
      "description": "Resolution strategy"
    },
    "custom_resolution": {
      "type": "object",
      "description": "Custom resolution data",
      "required": false
    }
  },
  "required": ["conflict_id", "resolution"]
}
```

### Analytics Tools

#### 18. get_usage_insights

**Description**: Get detailed usage insights and patterns.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "insight_type": {
      "type": "string",
      "enum": ["daily_patterns", "anomalies", "predictions", "recommendations"],
      "description": "Type of insights"
    },
    "period": {
      "type": "string",
      "description": "Time period (e.g., '7d', '1m')",
      "default": "7d"
    },
    "entity_filter": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Filter by entity IDs",
      "required": false
    }
  },
  "required": ["insight_type"]
}
```

#### 19. generate_report

**Description**: Generate comprehensive reports.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "report_type": {
      "type": "string",
      "enum": ["energy", "maintenance", "activity", "security", "summary"],
      "description": "Type of report"
    },
    "format": {
      "type": "string",
      "enum": ["text", "pdf", "json", "csv"],
      "description": "Output format",
      "default": "text"
    },
    "email_to": {
      "type": "string",
      "description": "Email address for delivery",
      "required": false
    }
  },
  "required": ["report_type"]
}
```

### Integration Tools

#### 20. import_from_service

**Description**: Import data from external services.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "service": {
      "type": "string",
      "enum": ["homekit", "google_home", "alexa", "smartthings", "csv"],
      "description": "Service to import from"
    },
    "credentials": {
      "type": "object",
      "description": "Service credentials",
      "required": false
    },
    "options": {
      "type": "object",
      "description": "Import options",
      "properties": {
        "merge_duplicates": {"type": "boolean", "default": true},
        "update_existing": {"type": "boolean", "default": false},
        "dry_run": {"type": "boolean", "default": false}
      },
      "required": false
    }
  },
  "required": ["service"]
}
```

## Error Handling

All tools follow consistent error handling:

```json
{
  "error": {
    "type": "validation_error|not_found|conflict|permission_denied|rate_limit|internal_error",
    "message": "Human-readable error message",
    "details": {
      "field": "field_name",
      "constraint": "constraint_violated"
    }
  }
}
```

## Rate Limiting

Default rate limits per tool category:

- **Query tools**: 1000 requests/minute
- **Create/Update tools**: 100 requests/minute
- **Delete tools**: 50 requests/minute
- **Analytics tools**: 20 requests/minute
- **Import tools**: 5 requests/minute

## Authentication

All MCP tools require authentication:

```json
{
  "auth": {
    "type": "bearer",
    "token": "jwt-token-here"
  }
}
```

## Batch Operations

Many tools support batch operations:

```json
{
  "batch": true,
  "operations": [
    {"room_name": "Living Room"},
    {"room_name": "Kitchen"},
    {"room_name": "Bedroom"}
  ]
}
```

## Webhooks

Register webhooks for real-time updates:

```json
{
  "webhook": {
    "url": "https://example.com/webhook",
    "events": ["entity.created", "entity.updated", "entity.deleted"],
    "secret": "webhook-secret"
  }
}
```

## SDKs

Official SDKs available for:

- Swift (WildThing native)
- Python (FunkyGibbon native)
- TypeScript/JavaScript
- Go
- Rust

## Versioning

API versioning through headers:

```
X-API-Version: 1.0
Accept: application/vnd.wildthing.v1+json
```

## Best Practices

1. **Pagination**: Use limit/offset for large result sets
2. **Caching**: Respect cache headers for query operations
3. **Idempotency**: Use idempotency keys for create operations
4. **Compression**: Enable gzip for large responses
5. **Monitoring**: Include request IDs for debugging

## Conclusion

The MCP tools API provides comprehensive access to smart home knowledge graph functionality. The consistent interface design and rich feature set enable AI assistants to effectively manage and query home automation data.