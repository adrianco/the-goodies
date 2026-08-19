# The Goodies — a temporal, replicated knowledge graph for a house

## 🏠 Overview

The Goodies stores what a house *is* — rooms, devices, manuals, photos, automations —
as a graph, and serves it to AI agents over the **Model Context Protocol (MCP)**.

Two things make it different from a typical smart-home data store, and both come
from the same decision: **nothing is ever overwritten.**

**It remembers.** Most home-automation stores answer "where is this thermostat?"
The Goodies is built to answer "where was it in March?" Entities are immutable
version rows, and edges are *interval* rows with a start and an end — so moving a
device to another room adds history rather than destroying it. A question about
the past is a query, not an archaeology project.

**It replicates without losing writes.** Clients hold the whole graph and stay
useful offline. When two of them edit the same thing, the server arbitrates, and
the write that loses is *kept* — stored as a version row, acknowledged, and
recoverable. A concurrent write can lose prominence; it can never lose existence.
Replicas then verify they actually agree, rather than assuming it.

The design is written down: 13 [ADRs](docs/adr/) covering the datastore, the
temporal model, the sync protocol, and the domain abstraction, each with the
alternatives that were rejected and why.

**Current status**: **installed and running in a real house since March 2026**,
with a second install at another house. Authenticated data endpoints, a
protocol-correct sync engine (see [`inbetweenies/PROTOCOL.md`](inbetweenies/PROTOCOL.md)),
12 MCP tools, backup/restore, and data-migration + upgrade tooling. The Python
**blowing-off** client also runs as an MCP server, mirroring the TypeScript port
(*KittenKong*). CI runs the test suites on Linux and macOS across Python
3.11–3.14. Latest release: `v0.4.0` — the final `inbetweenies-v2` release before
the temporal cutover described below.

> ⚠️ Authentication is enforced: every data endpoint (`/graph`, `/mcp`, `/sync`,
> `/sync-metadata`, `/backup`) requires a bearer token. Only `/health` and
> `/api/v1/auth/*` are public. Configure it with `funkygibbon setup-auth`.

**Related Projects**: adrianco/consciousness is an early prototype of the backend server that will be rewritten from scratch later. adrianco/c11s-house-ios is a native Swift iOS app that is the front end for the system. This repo is the knowledge graph protocol that interfaces the app to the backend, and includes the **Blowing-Off** Python client (a reference implementation, and now also an MCP server). The maintained port of the client is **KittenKong** (TypeScript, adrianco/the-goodies-typescript). An earlier Swift port (adrianco/the-goodies-swift / *WildThing*) is untested and has been abandoned.

**About the names**: the project and its components are named after [**The Goodies**](https://en.wikipedia.org/wiki/The_Goodies_(TV_series)), the 1970s British comedy series — and its songs and episodes. *FunkyGibbon* (the server) and *Inbetweenies* (the protocol) are both Goodies singles ("The Funky Gibbon", "The Inbetweenies"); *KittenKong* (the TypeScript client) is one of the show's best-known episodes; *Wild Thing* and the rest follow the same theme.

## 🏗️ Architecture

### Core Components

1. **🚀 FunkyGibbon** (Server) - Python-based backend server
   - FastAPI REST API with graph operations
   - 12 MCP tools for smart home management
   - Entity-relationship knowledge graph
   - SQLite database with immutable versioning
   - **Security**: JWT authentication, rate limiting, audit logging
   - **Access Control**: Admin and guest roles with QR code access

2. **📱 Blowing-Off** (Client) - Python synchronization client
   - Real-time sync with server
   - Local graph operations and caching
   - CLI interface matching server functionality
   - Conflict resolution and offline queue

3. **🛠️ Oook** (CLI) - Development and testing CLI
   - Direct server MCP tool access
   - Graph exploration and debugging
   - Database population and management

4. **🔗 Inbetweenies** (Protocol) - Shared synchronization protocol
   - Entity and relationship models
   - MCP tool implementations
   - Conflict resolution strategies
   - Graph operations abstraction

## ⏳ The temporal model

*Design: [ADR-004](docs/adr/ADR-004-version-retention-and-tombstones.md). Entity
versioning is shipped; interval edges and as-of queries are landing in v3 — see
[status](#what-is-shipped-vs-landing) below.*

### Nothing is overwritten

An entity is not a row that changes. It is a series of immutable `(id, version)`
rows, where the version string carries a timestamp prefix that sorts
lexically — so "the state of this device at time T" is a max-version-≤-T lookup.

Edges got the same discipline in v3. A relationship row carries `valid_from` and
`valid_to`, and is true over the half-open interval `valid_from ≤ T < valid_to`.
Re-pointing an edge **ends the old row and inserts a new one**; deleting ends the
row. Nothing is mutated, nothing is deleted.

That interval is closed at the start and open at the end for a specific reason:
ending one row and starting its successor at the same instant leaves exactly one
edge current at that instant — never zero, never two.

### Why the old approach could not work

Edges used to carry composite *version pins*: which entity version each endpoint
pointed at when the edge was created. This looks temporal and is temporally
useless. A pin says nothing about when an edge *stopped* being true, and it
forces an edge rewrite every time an endpoint gains a version. When a device
moved rooms, the old `located_in` edge was overwritten and the prior topology was
simply gone.

The pins are removed in v3. Endpoints resolve by **id + T** instead, so the time
axis does the work the pin was only pretending to do.

### Two clocks, deliberately not merged

There are two timelines here, and conflating them silently mis-answers a whole
class of question:

| Axis | What it is | What it is for |
|---|---|---|
| **Valid time** | when the edit was *made*, per the editing client | the as-of query axis |
| **Transaction time** (`server_seq`) | when the server *learned* of it | replication: sync cursors, pagination, audit |

An offline phone edit at 14:00 that syncs at 18:00 carries **14:00**. Ask "what
did the house look like at 15:00?" and you want the edit; ask "what changed since
my last sync?" and you want the arrival order. Queries never consult `server_seq`;
sync never consults valid time.

This has an honest consequence, recorded rather than hidden: **an as-of answer can
improve later.** The record of 14:00 gets better at 18:00 when the offline phone
syncs. That is correct behaviour for history — and once every client has synced,
every replica computes identical snapshots.

## 🌐 The distributed model

*Design: [ADR-005](docs/adr/ADR-005-protocol-v3-clocks-and-conflicts.md) and
[ADR-011](docs/adr/ADR-011-sync-robustness-no-silent-loss.md). Shipped in v0.4.0.*

Clients are not caches. Each holds the whole graph — small enough that a phone
carries years of history comfortably — and stays fully useful offline.

### No write is ever silently lost

This is the guarantee the sync design is built around, and it took four
mechanisms that only work together:

**A pending edit is a lock against pull-apply.** Sync pulls before it pushes. If
the pull overwrote local storage first, the subsequent push would send the
server's *own* version back, get idempotently acknowledged, and destroy the local
edit with the server never having seen it. An entity with a pending local change
is therefore never overwritten by a pull.

**The loser is acknowledged.** When a push loses conflict resolution, the server
still acks it. That sounds wrong and is essential: withholding the ack leaves the
client's pending mark in place, the guard above keeps blocking the incoming
winner, and the entity never converges — a livelock triggered by the exact
scenario the guard exists for. Acking ends the ambiguity between "lost" and "not
received".

**The loser is kept.** A version that loses is stored as a non-latest row, so the
content is recoverable from history by any human who goes looking. Acking is only
safe *because* the content is preserved first.

**One transaction per push batch.** All changes apply and commit together. A crash
mid-batch leaves nothing applied and nothing acked — the client simply retries.
Never a half-applied push.

### Convergence is verified, not assumed

Every sync response carries a `sha256` digest over the sorted set of current
`(id, version)` pairs. The client computes the same over its own replica and
compares. A mismatch triggers a full resync and reports loudly.

Tests prove the algorithm; the digest proves *this pair of databases*. They catch
different failures — bit-rot, a missed invalidation, someone editing the database
by hand.

### Per-id acknowledgement

Clients clear a pending change only when the server names that id as applied.
Aggregate counts cannot express a partially-applied batch, so anything not
explicitly acked is retried on the next sync.

## What is shipped vs landing

Being precise, because the temporal work is real but mostly unreleased:

| | Status |
|---|---|
| Immutable entity versioning, full history retained | **shipped** |
| Pull-guard, loser-ack, losers stored, atomic push batches | **shipped** |
| Convergence digest, per-id acks | **shipped** |
| `server_seq` replication axis, paginated sync, `is_latest` | **shipped** ([ADR-002](docs/adr/ADR-002-data-access-layer.md)) |
| FTS5 search with BM25 ranking | **shipped** ([ADR-006](docs/adr/ADR-006-search-fts-and-similarity.md)) |
| Domain abstraction — vocabulary in a manifest, not the schema | **shipped** ([ADR-012](docs/adr/ADR-012-domain-abstraction.md)) |
| Interval edges (`valid_from` / `valid_to`), `inbetweenies-v3` wire | **landing** — implemented, not yet released |
| `snapshot(T)`, `diff(T1,T2)`, `at` on every read | **designed, not built** |
| Second domain (`vehicles`) instantiated | **designed, not built** |
| Vector similarity via sqlite-vec | **deferred** — conditional on embeddings having an owner |

The v3 cutover is a **hard** one: no compatibility window, no version
negotiation. Both installations are owner-controlled, and what the migration must
preserve is database *content*, not wire compatibility.

## 🚀 Quick Start

### Prerequisites
- Python 3.11 or higher
- pip package manager
- curl (for testing authentication)

### Installation Options

#### Option 1: Quick Install (Recommended)
```bash
# Navigate to project root
cd /workspaces/the-goodies

# Run installer for development mode
./install.sh --dev

# Or run installer for production mode (will prompt for password)
./install.sh
```

#### Option 2: Manual Setup
```bash
# Navigate to project root
cd /workspaces/the-goodies

# Set Python path (required)
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH

# Install everything in one step.
# The repo is a single uv workspace (ADR-010 §6): the root pyproject.toml
# covers funkygibbon, inbetweenies, blowing-off and oook, so this one command
# installs all four editable plus the full dependency set. There is no longer a
# per-component install loop, and funkygibbon/requirements.txt is no longer the
# way dependencies get installed.
pip install -e .

# Or, with uv (resolves from the committed uv.lock instead of pip's resolver):
#   uv sync

# Configure security
export ADMIN_PASSWORD_HASH=""  # For dev mode with "admin" password
export JWT_SECRET="development-secret"

# Populate database
cd funkygibbon && python populate_graph_db.py && cd ..
```

### Starting the System
```bash
# If you used the installer:
./start_funkygibbon.sh

# If you did manual setup:
python -m funkygibbon

# In another terminal, test with Oook CLI
oook stats
oook search "smart"
oook tools
```

### 5. First Time Authentication
```bash
# Login as admin (password is "admin" in dev mode)
curl -X POST http://localhost:8000/api/v1/auth/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password": "admin"}'

# Response will include an access token:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIs...",
#   "token_type": "bearer",
#   "expires_in": 604800,
#   "role": "admin"
# }

# Save the token for API requests
export AUTH_TOKEN="<your-access-token>"

# Test authenticated access
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $AUTH_TOKEN"
```

## 🛠️ MCP Tools (12 Available)

The system provides 12 Model Context Protocol tools for smart home management:

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_devices_in_room` | Find all devices in a specific room | `room_id` |
| `find_device_controls` | Get controls for a device | `device_id` |
| `get_room_connections` | Find connections between rooms | `room_id` |
| `search_entities` | Search entities by name/content | `query`, `entity_types`, `limit` |
| `create_entity` | Create new entity | `entity_type`, `name`, `content` |
| `create_relationship` | Link entities | `from_entity_id`, `to_entity_id`, `relationship_type` |
| `find_path` | Find path between entities | `from_entity_id`, `to_entity_id` |
| `get_entity_details` | Get detailed entity info | `entity_id` |
| `find_similar_entities` | Find similar entities | `entity_id`, `threshold` |
| `get_procedures_for_device` | Get device procedures | `device_id` |
| `get_automations_in_room` | Get room automations | `room_id` |
| `update_entity` | Update entity (versioned) | `entity_id`, `changes`, `user_id` |

## 📊 Entity Types

The knowledge graph supports these entity types:
- **HOME** - Top-level container
- **ROOM** - Physical spaces
- **DEVICE** - Smart devices and appliances
- **ZONE** - Logical groupings
- **DOOR/WINDOW** - Connections
- **PROCEDURE** - Instructions
- **MANUAL** - Documentation
- **NOTE** - User annotations (including photo documentation)
- **SCHEDULE** - Time-based rules
- **AUTOMATION** - Event-based rules
- **APP** - Mobile/web applications that control devices

## 🔄 Client Synchronization

### Blowing-off Client Usage
```bash
# First, ensure Python path is set (required for finding inbetweenies)
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH

# Get an auth token by logging in as admin
curl -X POST http://localhost:8000/api/v1/auth/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password": "admin"}' | jq -r '.access_token'

# Connect to server with the token
blowing-off connect --server-url http://localhost:8000 --auth-token <your-token> --client-id device-1

# Check status
blowing-off status

# Synchronize with server
blowing-off sync

# Use MCP tools locally
blowing-off tools
blowing-off search "smart"
blowing-off execute get_devices_in_room -a room_id="room-123"
```

## 🧪 Testing

The system has comprehensive test coverage:

The maintained suites are `funkygibbon/tests`, `inbetweenies/tests`, and
`blowing-off/tests` (all synchronous), plus `tests/` for cross-cutting cases. CI
runs them on Linux and macOS across Python 3.11/3.12. (Windows is intentionally
excluded — see the parked SQLite-on-Windows issue.)

```bash
# Maintained suites
PYTHONPATH=inbetweenies:funkygibbon python -m pytest funkygibbon/tests inbetweenies/tests

# Client (blowing-off) unit tests
PYTHONPATH=inbetweenies:blowing-off python -m pytest blowing-off/tests/unit

# With coverage
python -m pytest --cov=funkygibbon --cov=blowingoff --cov=inbetweenies --cov-report=term-missing
```

## 📁 Project Structure

```
the-goodies/
├── funkygibbon/          # Server (Python FastAPI)
│   ├── api/             # REST API routes
│   ├── mcp/             # MCP server implementation  
│   ├── graph/           # Graph operations
│   ├── repositories/    # Data access layer
│   └── tests/           # Comprehensive test suite
├── blowing-off/         # Client (Python)
│   ├── cli/             # Command line interface
│   ├── sync/            # Synchronization engine
│   ├── graph/           # Local graph operations
│   └── tests/           # Unit and integration tests
├── oook/                # CLI tool (Python)
│   ├── oook/            # CLI implementation
│   └── examples/        # Usage examples
├── inbetweenies/        # Shared protocol (Python)
│   ├── models/          # Entity and relationship models
│   ├── mcp/             # MCP tool implementations
│   ├── sync/            # Synchronization protocol
│   └── PROTOCOL.md      # Authoritative inbetweenies-v2 spec
├── scripts/             # upgrade.sh and helpers
├── UPGRADE.md           # Install upgrade runbook
└── archive/             # Superseded / historical docs (see archive/README.md)
```

> blowing-off also ships an MCP **server** (`blowingoff/mcp/server.py`) and
> funkygibbon includes `migrate` and `setup_auth` tools.

## 🌟 Key Features

- ✅ **MCP Protocol Support** - 12 standardized tools
- ✅ **Graph-based Data Model** - Flexible entity relationships
- ✅ **Temporal by construction** - immutable versions, full history retained; nothing is overwritten ([ADR-004](docs/adr/ADR-004-version-retention-and-tombstones.md))
- ✅ **No silent loss** - pull-guard, loser-ack, losers preserved, atomic push batches ([ADR-011](docs/adr/ADR-011-sync-robustness-no-silent-loss.md))
- ✅ **Verified convergence** - every sync carries a state digest; divergence is detected, not assumed away
- ✅ **Full replication** - clients hold the whole graph and work offline, not a partial cache
- ✅ **Conflict Resolution** - server-arbitrated, one canonical resolver shared by every client
- ✅ **Search & Discovery** - FTS5 full-text search with BM25 ranking
- ✅ **CLI Interface** - Both server and client CLIs
- ✅ **MCP Server Client** - blowing-off runs as an MCP server (`python -m blowingoff.mcp.server`)
- ✅ **Authentication** - bearer-token auth on all data endpoints; `funkygibbon setup-auth`
- ✅ **Backup / Restore** - with an automated scheduler
- ✅ **User Generated Content** - Support for PDFs, photos, and user notes
- ✅ **BLOB Storage** - Binary data storage with sync capabilities
- ✅ **Device-App Integration** - Link devices to their control apps

## 📸 User Generated Content (UGC) Features

The system supports comprehensive User Generated Content functionality for storing and managing device documentation, photos, and user notes:

### UGC Entity Types

#### APP Entity Type
- Store mobile/web applications that control smart devices
- Link apps to devices using `CONTROLLED_BY_APP` relationship
- Track app metadata (platform, URL scheme, icon, description)

#### BLOB Storage
- Binary large object storage for PDFs and photos
- Support for multiple blob types: PDF, JPEG, PNG, and generic binary
- Automatic checksum generation (SHA-256)
- Sync status tracking (pending upload, uploaded, downloaded)
- Metadata storage for structured information

#### User Notes
- Free-form text notes with categorization
- Link notes to devices using `DOCUMENTED_BY` relationship
- Support for device references within notes
- Photo documentation with blob references

### Key UGC Features

#### PDF Document Management
- Store device manuals and instruction books
- Automatic summary generation from PDF content
- Model number extraction from filenames
- Link manuals to specific devices
- Full-text searchable content

#### Photo Documentation
- Store installation photos and serial numbers
- Extract metadata from photo files
- Categorize photos by type (serial_number, installation, etc.)
- Link photos to devices with the `HAS_PHOTO` relationship
- Support for JPEG and PNG formats

#### Mitsubishi Thermostat Integration
- Specialized support for Mitsubishi PAR-42MAA thermostats
- Store thermostat capabilities and configuration
- Link to Mitsubishi Comfort mobile app
- Track integration details (WiFi adapter, features)

### UGC API Usage Examples

```python
# Create an APP entity
app = Entity(
    entity_type=EntityType.APP,
    name="Mitsubishi Comfort",
    content={
        "platform": "iOS",
        "url_scheme": "mitsubishicomfort://",
        "description": "Control Mitsubishi HVAC systems"
    }
)

# Create a BLOB for PDF storage
pdf_blob = Blob(
    name="PAR-42MAAUB_Manual.pdf",
    blob_type=BlobType.PDF,
    mime_type="application/pdf",
    data=pdf_bytes,
    blob_metadata={"pages": 50, "model": "PAR-42MAAUB"}
)

# Create a PHOTO. An attachment entity carries exactly one blob, via
# top-level content.blob_id -- the only link to the blobs table (ADR-013 3).
# The entity type is the flag: no "has_blob": True is needed or accepted.
photo = Entity(
    entity_type=EntityType.PHOTO,
    name="install-01.jpg",
    content={
        "description": "Photo from HVAC installation",
        "filename": "install-01.jpg",
        "mime_type": "image/jpeg",
        "blob_id": "blob_id_1"
    }
)

# Link device to photo. Note the direction: the device HAS the photo.
relationship = EntityRelationship(
    from_entity_id=device.id,
    to_entity_id=photo.id,
    relationship_type=RelationshipType.HAS_PHOTO,
    properties={}
)

# Link device to the app that manages it. `manages` runs app -> device;
# `controlled_by_app` was its exact inverse and is deleted (ADR-013 4).
relationship = EntityRelationship(
    from_entity_id=app.id,
    to_entity_id=device.id,
    relationship_type=RelationshipType.MANAGES,
    properties={"integration": "wifi_adapter"}
)
```

### UGC Relationship Types
- **MANAGES** - App manages a device, automation or schedule
- **DOCUMENTED_BY** - Entity documented by a note or a `manual` (PDF)
- **HAS_PHOTO** - Entity has an attached `photo`

See [domains/house/README.md](domains/house/README.md) for the complete
vocabulary, and [ADR-013](docs/adr/ADR-013-house-vocabulary-cleanup.md) for how
blobs are linked.

## 🔐 Security Features (Phase 5)

The system includes enterprise-grade security features that have been fully implemented and tested:

### Core Security Features

- ✅ **Authentication System** - Admin password login with Argon2id hashing
- ✅ **JWT Tokens** - Secure token-based API access with configurable expiration
- ✅ **Rate Limiting** - Brute force protection (5 attempts/5 min window)
- ✅ **Audit Logging** - Comprehensive security event tracking with 15 event types
- ✅ **Guest Access** - QR code-based temporary read-only access
- ✅ **Progressive Delays** - Increasing lockout periods (up to 5x) for repeated failures
- ✅ **Permission System** - Role-based access control (admin/guest)

### Security Configuration

#### 1. Development Setup (Quick Start)
```bash
# For development/testing - uses "admin" as the default password
export ADMIN_PASSWORD_HASH=""
export JWT_SECRET="development-secret"

# Start the server
python -m funkygibbon
```

#### 2. Production Setup (Secure)
```bash
# Option A: Use the installer (recommended)
./install.sh
# The installer will:
# - Prompt for a secure admin password
# - Generate password hash automatically
# - Create a secure JWT secret
# - Set up start_funkygibbon.sh with your configuration

# Option B: Manual setup
# Step 1: Generate a secure password hash
python -c "from funkygibbon.auth import PasswordManager; pm = PasswordManager(); print(pm.hash_password('YourSecurePassword123!'))"

# Step 2: Set environment variables with generated values
export ADMIN_PASSWORD_HASH="$argon2id$v=19$m=65536,t=2,p=1$..."  # Use output from step 1
export JWT_SECRET="$(openssl rand -hex 32)"  # Generate secure random string

# Step 3: Start the server
python -m funkygibbon
```

#### 3. Security Environment Variables
| Variable | Description | Default | Production Recommendation |
|----------|-------------|---------|--------------------------|
| `ADMIN_PASSWORD_HASH` | Argon2id hash of admin password | Empty (dev mode) | Required - use strong password |
| `JWT_SECRET` | Secret key for signing JWT tokens | "development-secret" | Required - use random 32+ chars |
| `RATE_LIMIT_ATTEMPTS` | Max login attempts per window | 5 | 3-5 recommended |
| `RATE_LIMIT_WINDOW` | Time window in seconds | 300 (5 min) | 300-900 recommended |
| `AUDIT_LOG_FILE` | Path to security audit log | "security_audit.log" | Secure location with rotation |

### Authentication Usage

#### Admin Login
```bash
# Login with admin password
curl -X POST http://localhost:8000/api/v1/auth/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password": "admin"}'

# Save the access token from response
export AUTH_TOKEN="<access-token-from-response>"

# Use token for authenticated requests
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $AUTH_TOKEN"
```

#### Guest Access (QR Code)
```bash
# Generate guest QR code (requires admin token)
curl -X POST http://localhost:8000/api/v1/auth/guest/generate-qr \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"duration_hours": 24}'

# Response includes QR code image and guest token
```

### Security Implementation Details

#### Rate Limiting
- **Protection**: Prevents brute force attacks on authentication endpoints
- **Configuration**: 5 attempts allowed per 5-minute window per IP address
- **Progressive Delays**: Failed attempts result in increasing lockout periods (up to 5x)
- **Response**: HTTP 429 (Too Many Requests) with Retry-After header
- **Automatic Cleanup**: Old rate limit entries cleaned up hourly

#### Audit Logging
- **Coverage**: All authentication attempts, token operations, and permission checks
- **Event Types**: 15 different security events tracked including:
  - Authentication success/failure/lockout
  - Token creation/verification/expiration
  - Permission grants/denials
  - Guest access generation
  - Suspicious pattern detection
- **Format**: Structured JSON logs for easy analysis
- **Pattern Detection**: Automatic detection of credential stuffing and repeated failures
- **Location**: Logs written to `security_audit.log` (configurable)

## 📚 Documentation

- [Protocol spec](inbetweenies/PROTOCOL.md) — authoritative inbetweenies-v2 sync protocol
- [UPGRADE.md](UPGRADE.md) — install upgrade runbook
- [funkygibbon/README.md](funkygibbon/README.md) — server
- [blowing-off/README.md](blowing-off/README.md) — client + MCP server
- [archive/](archive/) — superseded / historical design docs

## 🎯 Status

A working reference implementation — **installed and running in a real house
since March 2026**, with a second install at another house:
- Authenticated data endpoints (bearer token), `funkygibbon setup-auth`
- Protocol-correct sync: canonical versions, `server_time` watermark, one shared
  conflict resolver, tombstone deletes, per-id acks, convergence digest
- 12 MCP tools; blowing-off also runs as an MCP server
- Backup/restore + scheduler; data-migration and upgrade tooling
- User Generated Content (PDFs, photos, notes) with BLOB storage, carried by sync
- CI green on Linux and macOS across Python 3.11–3.14

**In flight:** the v3 temporal cutover — interval edges and the
`inbetweenies-v3` wire are implemented; `snapshot(T)` and the `at` parameter are
next. See [what is shipped vs landing](#what-is-shipped-vs-landing).

**Why this exists.** A house accumulates history — appliances get replaced,
rooms get repurposed, a manual belongs to a device that has since moved. A store
that only knows the present throws that away every time something changes. This
one keeps it, and lets an agent ask about it.
