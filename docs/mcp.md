# Talking to FunkyGibbon

How to read and write the knowledge graph from a skill, a script or an agent.

**MCP is the interface.** Not one of two options — the one way. Every read and
every write goes through the tools below. Do not build a REST helper; that is
how the system got into the state ADR-013 had to migrate out of.

> **The vocabulary changed in ADR-013.** `has_blob` no longer exists, a photo is
> its own entity type, and the boolean `is_blob` / `has_blob` content flags are
> gone. If you are updating an existing script, read
> [Writing conformant data](#writing-conformant-data) first — the old shapes
> still *look* like they work today and will be rejected once endpoint
> validation is enabled on every write path (ADR-013 §5).

---

## Why there is only one way

Every gap in this surface has been filled by invention, and each invention
became a de-facto schema that took a migration to undo:

| The gap | What got invented | Cost |
|---|---|---|
| No way to attach a photo | `entity_type=note` + inline base64 + a `has_blob` edge pointing at the note | Six blob-linking conventions across two installs; ADR-013 §3 |
| MCP writes silently discarded (see below) | a whole parallel REST helper | Two ways to write, only one enforced |
| No delete (by design) | a `DELETE /relationships/{id}` call to a route that has never existed | Silent 404s |

The tools now cover the whole job, so there is no gap left to paper over. If you
find one, say so — do not route around it.

**Never touch the SQLite file directly.** The tools maintain `is_latest`,
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

## The REST graph API

Still mounted, and still used by the sync protocol, but **not the interface for
skills or agents**. Do not add new callers. `kittenkong_helper.py` is being
retired, not replaced.

For reference, what it exposes:

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

## Fixed, and worth knowing about

- **MCP writes were never committed.** `get_db` never commits and the graph
  operations only *flush*, so every write through `/api/v1/mcp/tools/{name}` was
  rolled back when the request ended: `create_entity` and `create_relationship`
  returned success and persisted nothing. The graph router always committed; the
  two disagreed and MCP lost. That is the most likely reason a REST helper was
  written in the first place — the documented surface did not work. Fixed, with
  a test.
- **Attachments wrote a null author.** The sync wire model declares
  `user_id: str`, so an author-less entity broke *reads* for every client that
  later pulled it. Fixed.
- **Tool schemas were maintained twice** and have been collapsed into one
  catalog (`inbetweenies/mcp/catalog.py`) rendered for both transports.

## Still open

- **Endpoint validation runs on one write path of three** (ADR-013 §5). The data
  now conforms, so enabling it on REST and sync is safe — and is what makes "one
  way" enforced rather than merely documented.
- **Local-first attachments.** The intended design is that KittenKong writes
  through MCP into its own local store and syncs to FunkyGibbon in the
  background. Attachments cannot do that yet: the Inbetweenies protocol has no
  blob carriage, so `attach_photo` currently goes to the server and arrives back
  on the next sync. Closing this means adding blobs to the sync protocol — not
  a local blob store bolted on beside it.
- **Replica size.** Clients hold the whole graph, which is comfortably small
  today (423 and 94 entities). If it outgrows memory, the answer is a per-client
  filter that hides old or irrelevant parts — not a partial, ad-hoc replica.
- **`kittenkong_helper.py` is being retired.** Nothing should gain a new
  dependency on it.
