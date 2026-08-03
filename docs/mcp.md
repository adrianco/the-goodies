# Talking to FunkyGibbon

How to read and write the knowledge graph from a skill, a script or an agent.

There are **two surfaces**, and they are not equivalent. Read [Which surface](#which-surface)
before writing anything.

> **The vocabulary changed in ADR-013.** `has_blob` no longer exists, a photo is
> its own entity type, and the boolean `is_blob` / `has_blob` content flags are
> gone. If you are updating an existing script, read
> [Writing conformant data](#writing-conformant-data) first — the old shapes
> still *look* like they work today and will be rejected once endpoint
> validation is enabled on every write path (ADR-013 §5).

---

## Which surface

| | MCP tools | REST API |
|---|---|---|
| Path | `/api/v1/mcp/tools/{name}` | `/api/v1/graph/...` |
| Read the graph | ✅ 12 tools | ✅ |
| Create entity / relationship | ✅ | ✅ |
| Update entity | ✅ | ✅ |
| **Delete** anything | ❌ | ✅ |
| **Blobs / photos** | ❌ **nothing** | ✅ (see below) |
| Entity version history | ❌ | ✅ `/entities/{id}/versions` |
| Aliases, status | ❌ | ✅ |
| Graph statistics | ❌ | ✅ `/statistics` |

**Use MCP when** an agent is exploring or reasoning about the graph — the tools
are shaped as questions (`get_devices_in_room`, `find_path`,
`get_procedures_for_device`) and return summarised results ready to reason over.

**Use REST when** you need anything in the ❌ column. In particular **anything
involving a photo or a PDF must use REST** — there is no blob tool in MCP at all.
This is why `room-walk` and `room-edit` use `kittenkong_helper.py` rather than
MCP: their core job is attaching photos.

Never touch the SQLite file directly. Both surfaces maintain `is_latest`,
`server_seq` and the version chain (ADR-002); a direct write corrupts them
silently.

## Authentication

Both surfaces sit behind the same auth. Get a token once and reuse it:

```bash
curl -sX POST localhost:8000/api/v1/auth/admin/login \
  -H 'Content-Type: application/json' -d '{"password":"..."}'
```

Then send `Authorization: Bearer <token>` on every request. `kittenkong_helper.py`
caches the token and refreshes it; prefer it over hand-rolling.

> The production server on port 8000 belongs to another account. Test against
> your own instance on a different port.

## MCP: the 12 tools

```bash
# list them, with schemas
curl -s localhost:8000/api/v1/mcp/tools -H "Authorization: Bearer $TOK"

# call one
curl -sX POST localhost:8000/api/v1/mcp/tools/get_devices_in_room \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"arguments": {"room_id": "..."}}'
```

The POST body is always `{"arguments": {...}}` — the tool name is in the path,
not the body.

| Tool | Arguments |
|---|---|
| `get_devices_in_room` | `room_id` |
| `get_room_connections` | `room_id` |
| `find_device_controls` | `device_id` |
| `get_procedures_for_device` | `device_id` |
| `get_automations_in_room` | `room_id` |
| `search_entities` | `query`, `entity_types?`, `limit?` |
| `get_entity_details` | `entity_id`, `include_relationships?`, `include_connected?` |
| `find_similar_entities` | `entity_id`, `threshold?`, `limit?` |
| `find_path` | `from_entity_id`, `to_entity_id`, `max_depth?` |
| `create_entity` | `entity_type`, `name`, `content?` |
| `create_relationship` | `from_entity_id`, `to_entity_id`, `relationship_type`, `properties?` |
| `update_entity` | `entity_id`, `changes`, `user_id` |

`update_entity` creates a **new version** — entities are immutable (ADR-002).
Nothing is edited in place and nothing is destroyed.

### Two gotchas

1. **The REST wrapper uses `parameters`, the MCP protocol uses `inputSchema`.**
   `GET /api/v1/mcp/tools` returns each tool with a `parameters` key. A strict
   MCP client expects `inputSchema`. The stdio MCP server in
   `blowing-off/blowingoff/mcp/server.py` emits the correct `input_schema`; the
   REST wrapper is a convenience surface, not a spec-conformant MCP transport.

2. **The tool list exists twice.** `funkygibbon/mcp/tools.py` (REST) and
   `blowing-off/blowingoff/mcp/server.py` (stdio) each hand-maintain all 12
   schemas. They agree today — verified — but nothing enforces it. Change one,
   change the other.

## REST: what MCP cannot do

```
GET    /api/v1/graph/entities?entity_type=room
POST   /api/v1/graph/entities
GET    /api/v1/graph/entities/{id}
PUT    /api/v1/graph/entities/{id}
GET    /api/v1/graph/entities/{id}/versions
GET    /api/v1/graph/entities/{id}/connected
GET    /api/v1/graph/entities/{id}/similar
POST   /api/v1/graph/relationships
GET    /api/v1/graph/relationships
DELETE /api/v1/graph/relationships/{id}
POST   /api/v1/graph/search
POST   /api/v1/graph/path
GET    /api/v1/graph/statistics
```

There is **no dedicated blob endpoint.** A blob reaches the server as base64
inside an entity's `content`, and the server moves it into the `blobs` table.
See below for the shape to send.

---

## Writing conformant data

This is the part that breaks silently. Endpoint rules are currently enforced on
the MCP path only — REST has the check commented out and sync never checks — so
a wrong shape is *accepted today* and rejected once ADR-013 §5 lands.

### Attaching a photo

**One rule: an entity that carries a blob is an attachment entity, and top-level
`content.blob_id` is the only link to the blobs table.** The entity type says
what kind of document it is, so there is no "this has a blob" flag — the type is
the flag.

```
device --has_photo--> photo  --content.blob_id--> blobs     (images)
device --documented_by--> manual --content.blob_id--> blobs (PDFs)
```

Create the attachment entity with the image inline, and the server extracts it:

```json
POST /api/v1/graph/entities
{
  "entity_type": "photo",
  "name": "keypad-workshop-door.jpg",
  "content": {
    "filename": "keypad-workshop-door.jpg",
    "mime_type": "image/jpeg",
    "data_b64": "...",
    "description": "8-button Vantage keypad by the Workshop door"
  }
}
```

Then link it **from the thing, to the photo**:

```json
POST /api/v1/graph/relationships
{ "from_entity_id": "<device-id>", "to_entity_id": "<photo-id>",
  "relationship_type": "has_photo" }
```

A PDF is a `manual`, not a `photo`, and attaches with `documented_by` instead.
Route on mime type.

### What not to write

| Don't | Do | Why |
|---|---|---|
| `entity_type: "note"` for an image | `entity_type: "photo"` | `note` is text. A JPEG and a walk transcript were the same type; that is what ADR-013 split. |
| `relationship_type: "has_blob"` | `"has_photo"` (image) or `"documented_by"` (PDF) | `has_blob` never pointed at a blob — it pointed at a note carrying one. Deleted. |
| `"is_blob": true` / `"has_blob": true` in content | nothing | The entity type is the flag. Two names for one flag existed; both are gone. |
| `"blob_reference"`, `"blob_references"`, `"screenshot_blob_ids"` | `"blob_id"` | Four spellings of one link. One survives. |
| photo → device | device → photo | Direction matters. Four edges in the live data ran backwards because nothing rejected them. |
| `contained_in`, `controlled_by_app` | `located_in`, `manages` | Deleted as exact duplicates/inverses. |

### Ordered sequences stay inline

One attachment is an entity. An **ordered sequence** of attachments belonging to
one entity is an inline list, each element carrying its own `blob_id`:

```json
{ "images": [
    {"step": 1, "label": "Press MENU", "mime_type": "image/jpeg", "data_b64": "..."},
    {"step": 2, "label": "Select Zone 2", "mime_type": "image/jpeg", "data_b64": "..."}
] }
```

Relationships are an unordered set, so splitting a sequence into entities leaves
its order nowhere to live except a `step` integer in edge properties that every
reader must know to sort by.

**The test:** if removing an item would change what the remaining items mean, it
is a sequence — keep it inline. Otherwise it is an entity.

### The vocabulary

Entity and relationship types are **not** free strings. They come from the
domain manifest, and unknown values are rejected. See
[domains/house/README.md](../domains/house/README.md) for the full list with
live usage counts, and [domains.md](domains.md) for how a domain declares one.

Briefly, for the house: entities are `home`, `zone`, `room`, `device`, `door`,
`window`, `note`, `photo`, `manual`, `procedure`, `schedule`, `automation`,
`app`. The edges you will actually use are `located_in` (where a thing is),
`part_of` (what it is a component of — *not* containment), `connects_to`,
`has_photo`, `documented_by`, and `manages`.

---

## Known gaps

- **No blob capability in MCP.** Any photo workflow must use REST. If MCP is to
  become the primary surface, this is the gap to close first.
- **Endpoint validation runs on one write path of three** (ADR-013 §5). Until
  that is fixed, a malformed relationship is accepted by REST and by sync.
- **`kittenkong_helper.upload_blob()` writes the pre-ADR-013 shape** — an
  `entity_type=note` with inline base64 plus a `has_blob` edge. It needs updating
  to the shape above before the next photo is uploaded; its own docstring already
  flags the guess ("FunkyGibbon's blob schema may differ").
- **Tool schemas are duplicated** between the REST wrapper and the stdio server.
