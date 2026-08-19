# Components and supported access patterns

Who may talk to what, and over which credential. Anything not drawn here is not
a supported path — the system's recurring failure has been callers inventing one
when the supported path had a gap.

```mermaid
graph TB
    subgraph agents["Agents and skills"]
        SKILL["room-walk / room-edit<br/>and other skills"]
        CLAUDE["Claude Code /<br/>Claude Desktop"]
    end

    subgraph clients["Inbetweenies clients — hold a full local replica"]
        KK["<b>KittenKong</b> (TypeScript)<br/>local store + MCP server"]
        BO["<b>Blowing-Off</b> (Python)<br/>local store + MCP server"]
    end

    subgraph server["FunkyGibbon — the authority"]
        AUTH["/api/v1/auth/*"]
        SYNC["/api/v1/sync/<br/>Inbetweenies v2"]
        REST["/api/v1/graph/*<br/><i>local only</i>"]
        DB[("SQLite<br/>entities · relationships · blobs")]
    end

    OOOK["<b>oook</b><br/>local admin CLI"]

    SKILL -->|MCP| KK
    CLAUDE -->|MCP stdio| KK
    CLAUDE -->|MCP stdio| BO

    KK -->|bearer token| AUTH
    KK -->|bearer token| SYNC
    BO -->|bearer token| AUTH
    BO -->|bearer token| SYNC

    OOOK -->|bearer token +<br/>X-FunkyGibbon-Local-Key| REST

    SYNC --- DB
    REST --- DB

    classDef authority fill:#1f4e5f,stroke:#0d2b35,color:#fff
    classDef client fill:#2d5a3d,stroke:#173021,color:#fff
    classDef caller fill:#5a4a2d,stroke:#302617,color:#fff
    class AUTH,SYNC,REST,DB authority
    class KK,BO client
    class SKILL,CLAUDE,OOOK caller
```

## The three access patterns

| Caller | Reaches | Credential | Why |
|---|---|---|---|
| **Agents / skills** | a client's MCP server | none (local process) | All reads and writes are MCP tools against a local replica. |
| **KittenKong, Blowing-Off** | `auth` + `sync` **only** | bearer token | They hold the whole graph locally. Sync is the only thing they need from the server. |
| **`oook`** | `auth` + `graph` REST | bearer token **plus** `X-FunkyGibbon-Local-Key` | Local administration and testing, on the server's own machine. |

**FunkyGibbon serves no MCP.** MCP is the client-side interface, served against
a local replica. A server-side MCP endpoint was a third way to write the same
data — and the one whose writes were never committed, so everything using it
silently did nothing.

## Why the boundary is enforced, not documented

Every one of these was a real invention filling a real gap:

| Gap | What got invented | Cost |
|---|---|---|
| No way to attach a photo | `note` + inline base64 + a `has_blob` edge pointing at the note | Six blob conventions across two installs; a migration to undo |
| MCP writes silently discarded | a parallel REST helper | Two write paths, one enforced |
| No delete (append-only by design) | `DELETE /relationships/{id}` to a route that never existed | Silent 404s |
| Sync could not carry bytes | direct server calls for attachments | The boundary this diagram exists to draw |

The second credential exists so the first column cannot recur quietly: a sync
client that reaches for the REST API gets a 403 explaining which door it should
be using.

## Writes

```mermaid
sequenceDiagram
    participant S as Skill
    participant K as KittenKong
    participant F as FunkyGibbon

    S->>K: attach_photo (MCP)
    K->>K: photo entity + blob + has_photo<br/>written to the local store
    Note over K: the write is complete and<br/>readable before any network
    K-->>S: attachment_id, blob_id

    loop background
        K->>F: POST /api/v1/sync/ — changes carry entity,<br/>relationships and blobs
        F->>F: verify checksum, persist, assign server_seq
        F-->>K: per-id acks
    end
```

Local-first: the write lands in the replica and syncs. Blob bytes travel in the
sync payload (`SyncChange.blobs`), which is what removes the last reason to call
the server directly.

## Append-only

Nothing is deleted. Removal appends a tombstone version; a record that was
simply *wrong* is marked as an error behind that tombstone. "This was removed"
and "this was never here" are different facts, and history keeps both. There is
no delete tool and no DELETE endpoint for graph data.

## Data model in one line

An entity carrying a blob is an **attachment entity** — `photo` for an image,
`manual` for a PDF — and top-level `content.blob_id` is the only link to the
blobs table. The entity type is the flag; no relationship ever points at a blob.
An *ordered* sequence of attachments stays inline as `content.images[]`, because
relationships are an unordered set. See
[ADR-013 §3](adr/ADR-013-house-vocabulary-cleanup.md).
