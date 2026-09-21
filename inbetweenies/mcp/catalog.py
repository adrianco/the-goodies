"""The canonical MCP tool catalog — one definition, every transport.

The ENGINE's tools are defined here. A domain's tools are declared in its
manifest (ADR-012 §2) and rendered by ``catalog_for(manifest)``, which is what
every transport serves: nothing here names a room or a car.

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


#: The as-of argument every graph read accepts (ADR-004 §3; SQL:2011 AS OF).
_AT_PARAM = {
    'type': 'string',
    'description': ('Answer as of this instant (ISO-8601 UTC), e.g. "2026-04-01T00:00:00Z". '
                    'Omitted means now.'),
}

ENGINE_TOOL_SPECS: Tuple[ToolSpec, ...] = (
    ToolSpec(
        name='search_entities',
        description='Search for entities by name or content',
        parameters={   'type': 'object',
            'properties': {   'query': {   'type': 'string',
                                           'description': 'Search query string'},
                              'entity_types': {   'type': 'array',
                                                  'items': {   'type': 'string'},
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
                                                 'description': 'Type of entity to '
                                                                'create (one of the '
                                                                "domain's declared "
                                                                'types)'},
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
                                                       'description': 'Type of '
                                                                      'relationship (one of '
                                                                      "the domain's declared "
                                                                      'types)'},
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
            'reason is recorded. Its open edges are ended at the same moment '
            '(kept as history). This is the only way to remove something.'
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
    # ------------------------------------------------------------------
    # Relationship parity (issue #85) and the as-of surface (ADR-004 §3).
    #
    # MCP is the client interface (ADR-015): anything a client must be able
    # to do to the graph has to be a tool. These were the three edge
    # operations that were not, plus the temporal queries the interval model
    # exists to answer. `delete` is `end_relationship`: the store is
    # append-only and an ended interval is kept as history.
    # ------------------------------------------------------------------
    ToolSpec(
        name='list_relationships',
        description=(
            'List edges, filtered by endpoint and/or type. Current edges by '
            'default; pass `at` for the graph as of an instant, or '
            '`include_history` for every interval ever recorded.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'from_entity_id': {'type': 'string', 'description': 'Filter by source entity'},
                'to_entity_id': {'type': 'string', 'description': 'Filter by target entity'},
                'relationship_type': {'type': 'string', 'description': 'Filter by type, e.g. located_in'},
                'include_history': {'type': 'boolean', 'description': 'Include retired intervals. Default false.'},
                'at': _AT_PARAM,
            },
        },
    ),
    ToolSpec(
        name='get_connected',
        description=(
            'Every entity one edge away from an entity, with the edge, in '
            'either direction. The generic neighbourhood query; the room and '
            'device tools are specialisations of it.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'entity_id': {'type': 'string', 'description': 'The centre entity'},
                'relationship_type': {'type': 'string', 'description': 'Optional filter by edge type'},
                'direction': {'type': 'string', 'enum': ['outgoing', 'incoming', 'both'],
                              'description': 'Default both'},
                'at': _AT_PARAM,
            },
            'required': ['entity_id'],
        },
    ),
    ToolSpec(
        name='end_relationship',
        description=(
            'Remove an edge by ending its interval. This is the delete: the '
            'row is kept as history with its end recorded, so past state '
            'still answers. To move an edge, end it and create the new one. '
            'Idempotent.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'relationship_id': {'type': 'string', 'description': 'The edge to end'},
                'reason': {'type': 'string', 'description': 'Why -- recorded in the result'},
                'user_id': {'type': 'string', 'description': 'Who ended it'},
                'at': {'type': 'string',
                       'description': 'When it stopped being true (ISO-8601 UTC). Default now.'},
            },
            'required': ['relationship_id'],
        },
    ),
    ToolSpec(
        name='list_entities',
        description=(
            'List entities, optionally by type, paged. Current by default; '
            'with `at`, the entities that existed then, each at its version then.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'entity_type': {'type': 'string', 'description': 'Optional filter, e.g. room'},
                'limit': {'type': 'integer', 'description': 'Page size, default 100'},
                'offset': {'type': 'integer', 'description': 'Page start, default 0'},
                'at': _AT_PARAM,
            },
        },
    ),
    ToolSpec(
        name='get_graph_diff',
        description=(
            'What changed between two instants: entities that gained a version, '
            'edges that started, edges that ended. Deletions appear as '
            'tombstone versions and ended edges, never as absences.'
        ),
        parameters={
            'type': 'object',
            'properties': {
                'since': {'type': 'string', 'description': 'Start of the window, exclusive (ISO-8601 UTC)'},
                'until': {'type': 'string', 'description': 'End of the window, inclusive. Default now.'},
            },
            'required': ['since'],
        },
    ),
)

#: The engine tools whose reads answer "as of `at`" (ADR-004 §3). Any tool
#: that reads the graph takes it; omitted means now. Domain tools always do.
AS_OF_TOOLS = frozenset({
    'find_path', 'get_entity_details', 'list_relationships', 'get_connected', 'list_entities',
})


def _with_at(spec: ToolSpec) -> ToolSpec:
    if 'at' in spec.parameters.get('properties', {}):
        return spec
    props = dict(spec.parameters.get('properties', {}))
    props['at'] = _AT_PARAM
    return ToolSpec(spec.name, spec.description, {**spec.parameters, 'properties': props})


ENGINE_TOOL_SPECS = tuple(_with_at(t) if t.name in AS_OF_TOOLS else t for t in ENGINE_TOOL_SPECS)

#: Engine tools that take vocabulary, and which parameter carries it. The
#: catalog for a domain narrows these to an ``enum`` of what that domain
#: declares, so a client sees `vehicle`/`part` on a vehicles server and
#: `room`/`device` on a house server, from the same engine definition.
_VOCABULARY_PARAMS = {
    'search_entities': ('entity_types', 'entity_types'),
    'create_entity': ('entity_type', 'entity_types'),
    'create_relationship': ('relationship_type', 'relationship_types'),
    'list_entities': ('entity_type', 'entity_types'),
}


def _with_vocabulary(spec: ToolSpec, manifest) -> ToolSpec:
    if spec.name not in _VOCABULARY_PARAMS:
        return spec
    param, attr = _VOCABULARY_PARAMS[spec.name]
    values = sorted(getattr(manifest, attr))
    props = {k: dict(v) for k, v in spec.parameters['properties'].items()}
    target = props[param]
    if target.get('type') == 'array':
        target['items'] = {**target.get('items', {}), 'enum': values}
    else:
        target['enum'] = values
    return ToolSpec(spec.name, spec.description, {**spec.parameters, 'properties': props})


def catalog_for(manifest) -> Tuple[ToolSpec, ...]:
    """The full tool catalog a server or replica of ``manifest`` exposes.

    Engine tools first, with their vocabulary parameters narrowed to the
    domain's declared types, then the domain's own declared tools. This is
    the contract every transport renders (ADR-015): the REST wrapper, the
    stdio server, and ``GET /api/v1/mcp/tools`` all come from here.
    """
    from .domain_tools import domain_tool_specs  # local: domain_tools imports this module
    engine = [_with_vocabulary(t, manifest) for t in ENGINE_TOOL_SPECS]
    domain = domain_tool_specs(manifest)
    clash = {t.name for t in engine} & {t.name for t in domain}
    if clash:
        raise ValueError(f"domain {manifest.name!r} redeclares engine tools: {sorted(clash)}")
    return tuple(engine + domain)


def rest_tools_for(manifest) -> List[Dict[str, Any]]:
    """``GET /api/v1/mcp/tools`` view (a ``parameters`` key)."""
    return [t.as_rest() for t in catalog_for(manifest)]


def mcp_tools_for(manifest) -> List[Dict[str, Any]]:
    """Spec-conformant view (``inputSchema``), for a real MCP transport."""
    return [t.as_mcp() for t in catalog_for(manifest)]


#: Engine-only lookups. A domain's full set is ``catalog_for(manifest)``.
ENGINE_TOOLS_BY_NAME: Dict[str, ToolSpec] = {t.name: t for t in ENGINE_TOOL_SPECS}
