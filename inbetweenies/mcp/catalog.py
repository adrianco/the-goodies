"""The canonical MCP tool catalog — one definition, every transport.

These schemas used to exist twice, hand-maintained: ``funkygibbon/mcp/tools.py``
for the REST wrapper and ``blowing-off/blowingoff/mcp/server.py`` for the stdio
MCP server. They happened to agree, but nothing made them agree, and a tool
added to one would silently be missing from the other.

They live here now because this is the package both sides already depend on.
``ToolSpec`` carries the schema once and renders it either way:

* ``.as_rest()``  -> ``{"name", "description", "parameters"}``  (the REST wrapper)
* ``.as_mcp()``   -> ``{"name", "description", "inputSchema"}`` (the MCP spec)

The two key names are not interchangeable: the MCP specification says
``inputSchema``, and the REST wrapper has always said ``parameters``. Keeping
both renderings is what lets the wrapper stay backward-compatible while the
stdio server stays spec-conformant.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool: its name, what it does, and the arguments it accepts."""

    name: str
    description: str
    parameters: Dict[str, Any]

    def as_rest(self) -> Dict[str, Any]:
        """The shape ``GET /api/v1/mcp/tools`` has always returned."""
        return {"name": self.name, "description": self.description,
                "parameters": self.parameters}

    def as_mcp(self) -> Dict[str, Any]:
        """The shape the MCP specification defines."""
        return {"name": self.name, "description": self.description,
                "inputSchema": self.parameters}


TOOL_SPECS: Tuple[ToolSpec, ...] = (
    ToolSpec(
        name='get_devices_in_room',
        description='Get all devices located in a specific room',
        parameters={   'type': 'object',
            'properties': {   'room_id': {   'type': 'string',
                                             'description': 'The ID of the room '
                                                            'entity'}},
            'required': ['room_id']},
    ),
    ToolSpec(
        name='find_device_controls',
        description='Get available controls and services for a device',
        parameters={   'type': 'object',
            'properties': {   'device_id': {   'type': 'string',
                                               'description': 'The ID of the device '
                                                              'entity'}},
            'required': ['device_id']},
    ),
    ToolSpec(
        name='get_room_connections',
        description='Find doors, windows, and passages between rooms',
        parameters={   'type': 'object',
            'properties': {   'room_id': {   'type': 'string',
                                             'description': 'The ID of the room '
                                                            'entity'}},
            'required': ['room_id']},
    ),
    ToolSpec(
        name='search_entities',
        description='Search for entities by name or content',
        parameters={   'type': 'object',
            'properties': {   'query': {   'type': 'string',
                                           'description': 'Search query string'},
                              'entity_types': {   'type': 'array',
                                                  'items': {   'type': 'string',
                                                               'enum': [   'home',
                                                                           'room',
                                                                           'device',
                                                                           'zone',
                                                                           'door',
                                                                           'window',
                                                                           'procedure',
                                                                           'manual',
                                                                           'note',
                                                                           'schedule',
                                                                           'automation']},
                                                  'description': 'Filter by entity '
                                                                 'types (optional)'},
                              'limit': {   'type': 'integer',
                                           'description': 'Maximum number of results '
                                                          '(default: 10)',
                                           'default': 10}},
            'required': ['query']},
    ),
    ToolSpec(
        name='create_entity',
        description='Create a new entity in the knowledge graph',
        parameters={   'type': 'object',
            'properties': {   'entity_type': {   'type': 'string',
                                                 'enum': [   'home',
                                                             'room',
                                                             'device',
                                                             'zone',
                                                             'door',
                                                             'window',
                                                             'procedure',
                                                             'manual',
                                                             'note',
                                                             'schedule',
                                                             'automation'],
                                                 'description': 'Type of entity to '
                                                                'create'},
                              'name': {   'type': 'string',
                                          'description': 'Name of the entity'},
                              'content': {   'type': 'object',
                                             'description': 'Additional properties '
                                                            'for the entity',
                                             'additionalProperties': True}},
            'required': ['entity_type', 'name']},
    ),
    ToolSpec(
        name='create_relationship',
        description='Create a relationship between two entities',
        parameters={   'type': 'object',
            'properties': {   'from_entity_id': {   'type': 'string',
                                                    'description': 'ID of the source '
                                                                   'entity'},
                              'to_entity_id': {   'type': 'string',
                                                  'description': 'ID of the target '
                                                                 'entity'},
                              'relationship_type': {   'type': 'string',
                                                       'enum': [   'located_in',
                                                                   'controls',
                                                                   'connects_to',
                                                                   'part_of',
                                                                   'manages',
                                                                   'documented_by',
                                                                   'procedure_for',
                                                                   'triggered_by',
                                                                   'depends_on',
                                                                   'contained_in',
                                                                   'monitors',
                                                                   'automates'],
                                                       'description': 'Type of '
                                                                      'relationship'},
                              'properties': {   'type': 'object',
                                                'description': 'Additional '
                                                               'properties for the '
                                                               'relationship',
                                                'additionalProperties': True}},
            'required': ['from_entity_id', 'to_entity_id', 'relationship_type']},
    ),
    ToolSpec(
        name='find_path',
        description='Find the shortest path between two entities',
        parameters={   'type': 'object',
            'properties': {   'from_entity_id': {   'type': 'string',
                                                    'description': 'Starting entity '
                                                                   'ID'},
                              'to_entity_id': {   'type': 'string',
                                                  'description': 'Target entity ID'},
                              'max_depth': {   'type': 'integer',
                                               'description': 'Maximum search depth '
                                                              '(default: 10)',
                                               'default': 10}},
            'required': ['from_entity_id', 'to_entity_id']},
    ),
    ToolSpec(
        name='get_entity_details',
        description='Get detailed information about an entity',
        parameters={   'type': 'object',
            'properties': {   'entity_id': {   'type': 'string',
                                               'description': 'The ID of the entity'},
                              'include_relationships': {   'type': 'boolean',
                                                           'description': 'Include '
                                                                          'incoming '
                                                                          'and '
                                                                          'outgoing '
                                                                          'relationships',
                                                           'default': True},
                              'include_connected': {   'type': 'boolean',
                                                       'description': 'Include '
                                                                      'directly '
                                                                      'connected '
                                                                      'entities',
                                                       'default': False}},
            'required': ['entity_id']},
    ),
    ToolSpec(
        name='find_similar_entities',
        description='Find entities similar to a given entity',
        parameters={   'type': 'object',
            'properties': {   'entity_id': {   'type': 'string',
                                               'description': 'Reference entity ID'},
                              'threshold': {   'type': 'number',
                                               'description': 'Similarity threshold '
                                                              '(0-1)',
                                               'default': 0.7,
                                               'minimum': 0,
                                               'maximum': 1},
                              'limit': {   'type': 'integer',
                                           'description': 'Maximum number of results',
                                           'default': 10}},
            'required': ['entity_id']},
    ),
    ToolSpec(
        name='get_procedures_for_device',
        description='Get all procedures and manuals for a specific device',
        parameters={   'type': 'object',
            'properties': {   'device_id': {   'type': 'string',
                                               'description': 'The ID of the '
                                                              'device'}},
            'required': ['device_id']},
    ),
    ToolSpec(
        name='get_automations_in_room',
        description='Get all automations that affect devices in a room',
        parameters={   'type': 'object',
            'properties': {   'room_id': {   'type': 'string',
                                             'description': 'The ID of the room'}},
            'required': ['room_id']},
    ),
    ToolSpec(
        name='update_entity',
        description='Update an entity (creates new version)',
        parameters={   'type': 'object',
            'properties': {   'entity_id': {   'type': 'string',
                                               'description': 'The ID of the entity '
                                                              'to update'},
                              'changes': {   'type': 'object',
                                             'properties': {   'name': {   'type': 'string',
                                                                           'description': 'New '
                                                                                          'name '
                                                                                          '(optional)'},
                                                               'content': {   'type': 'object',
                                                                              'description': 'Content '
                                                                                             'updates '
                                                                                             '(merged '
                                                                                             'with '
                                                                                             'existing)',
                                                                              'additionalProperties': True}}},
                              'user_id': {   'type': 'string',
                                             'description': 'ID of the user making '
                                                            'the change'}},
            'required': ['entity_id', 'changes', 'user_id']},
    ),
    # --- Attachments ------------------------------------------------------
    # There was no first-class way to attach a photo, so callers invented one:
    # an `entity_type=note` holding inline base64, linked by a `has_blob` edge
    # that pointed at the note rather than the blob. That invention became the
    # de-facto schema and took a migration to undo (ADR-013 §3). These tools
    # exist so the intended shape is the easy one.
    ToolSpec(
        name='attach_photo',
        description=(
            'Attach a photo to an entity. Creates a photo entity carrying the '
            'image, stores the bytes in the blobs table, and links it with '
            'has_photo. Use this rather than creating a note with inline data.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'parent_entity_id': {
                    'type': 'string',
                    'description': 'The entity the photo is of (device, room, door, ...)'},
                'filename': {
                    'type': 'string',
                    'description': 'Original filename, used as the photo name'},
                'data_b64': {
                    'type': 'string',
                    'description': 'Base64-encoded image bytes'},
                'mime_type': {
                    'type': 'string',
                    'description': 'e.g. image/jpeg. Defaults to image/jpeg.'},
                'description': {
                    'type': 'string',
                    'description': 'What the photo shows'},
                'user_id': {
                    'type': 'string',
                    'description': 'Who attached it'},
            },
            'required': ['parent_entity_id', 'filename', 'data_b64'],
        },
    ),
    ToolSpec(
        name='attach_document',
        description=(
            'Attach a PDF or other document to an entity. Creates a manual '
            'entity carrying the file and links it with documented_by. A PDF '
            'is a manual, not a photo.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'parent_entity_id': {
                    'type': 'string',
                    'description': 'The entity the document describes'},
                'filename': {'type': 'string', 'description': 'Original filename'},
                'data_b64': {'type': 'string', 'description': 'Base64-encoded file bytes'},
                'mime_type': {
                    'type': 'string',
                    'description': 'e.g. application/pdf. Defaults to application/pdf.'},
                'description': {'type': 'string', 'description': 'What the document covers'},
                'user_id': {'type': 'string', 'description': 'Who attached it'},
            },
            'required': ['parent_entity_id', 'filename', 'data_b64'],
        },
    ),
    ToolSpec(
        name='get_blob',
        description=(
            'Fetch a stored blob by id. Returns metadata always; the bytes '
            'only when include_data is true, since blobs are large.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'blob_id': {'type': 'string', 'description': 'The blob id, from an attachment entity\'s content.blob_id'},
                'include_data': {
                    'type': 'boolean',
                    'description': 'Include base64 bytes. Default false.'},
            },
            'required': ['blob_id'],
        },
    ),
    # --- History and retraction -------------------------------------------
    # The store is append-only: nothing is deleted, and a mistake is marked as
    # such behind a tombstone. There is deliberately no delete tool -- the API
    # has never had a DELETE endpoint for graph data, and the one caller that
    # assumed otherwise was calling a route that does not exist.
    ToolSpec(
        name='get_entity_versions',
        description=(
            'Full version history of an entity, newest first. Entities are '
            'immutable: every edit appends a version and nothing is overwritten.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'entity_id': {'type': 'string', 'description': 'The entity to get history for'},
            },
            'required': ['entity_id'],
        },
    ),
    ToolSpec(
        name='tombstone_entity',
        description=(
            'Retract an entity by appending a tombstone version. Use this to '
            'remove something that is gone, or to mark a record as an error. '
            'Nothing is deleted: earlier versions remain readable, and the '
            'reason is recorded. This is the only way to remove something.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'entity_id': {'type': 'string', 'description': 'The entity to retract'},
                'reason': {
                    'type': 'string',
                    'description': 'Why it is being retracted -- recorded on the tombstone'},
                'is_error': {
                    'type': 'boolean',
                    'description': 'True if the record was wrong, as opposed to the thing no longer existing. Default false.'},
                'user_id': {'type': 'string', 'description': 'Who retracted it'},
            },
            'required': ['entity_id', 'reason'],
        },
    ),
    ToolSpec(
        name='get_statistics',
        description='Counts of entities and relationships by type, for the whole graph.',
        parameters={'type': 'object', 'properties': {}},
    ),
)

#: REST-wrapper view. ``funkygibbon.mcp.tools.MCP_TOOLS`` is this list.
MCP_TOOLS: List[Dict[str, Any]] = [t.as_rest() for t in TOOL_SPECS]

#: Spec-conformant view, for a real MCP transport.
MCP_TOOLS_SPEC: List[Dict[str, Any]] = [t.as_mcp() for t in TOOL_SPECS]

#: Lookup by name, for dispatch.
TOOLS_BY_NAME: Dict[str, ToolSpec] = {t.name: t for t in TOOL_SPECS}
