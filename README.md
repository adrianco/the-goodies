# The Goodies - Smart Home Knowledge Graph System

## 🏠 Overview

The Goodies is a modern smart home knowledge graph data store layer built around the **Model Context Protocol (MCP)** architecture. The system provides a unified interface for managing smart home devices, relationships, and automations through a graph-based data model.

**Current status**: a working single-house reference implementation — authenticated
data endpoints, a protocol-correct sync engine (see
[`inbetweenies/PROTOCOL.md`](inbetweenies/PROTOCOL.md)), 12 MCP tools, backup/restore,
and data-migration + upgrade tooling. The Python **blowing-off** client also runs
as an MCP server, mirroring the TypeScript port (*KittenKong*). CI runs the test
suites on Linux and macOS. Released tags: see the GitHub releases (latest `v0.2.2`).

> ⚠️ Authentication is enforced: every data endpoint (`/graph`, `/mcp`, `/sync`,
> `/sync-metadata`, `/backup`) requires a bearer token. Only `/health` and
> `/api/v1/auth/*` are public. Configure it with `funkygibbon setup-auth`.

**Related Projects**: adrianco/consciousness is an early prototype of the backend server that will be rewritten from scratch later. adrianco/c11s-house-ios is a native Swift iOS app that is the front end for the system. This repo is the knowledge graph protocol that interfaces the app to the backend, and includes the **Blowing-Off** Python client (a reference implementation, and now also an MCP server). The maintained port of the client is **KittenKong** (TypeScript, rolandcanyon-cmd/the-goodies-typescript). An earlier Swift port (adrianco/the-goodies-swift / *WildThing*) is untested and has been abandoned.

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

# Install dependencies
cd funkygibbon && pip install -r requirements.txt && cd ..
cd inbetweenies && pip install -e . && cd ..
cd oook && pip install -e . && cd ..
cd blowing-off && pip install -e . && cd ..

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
- ✅ **Real-time Synchronization** - Client-server sync
- ✅ **Immutable Versioning** - Complete change history
- ✅ **Conflict Resolution** - Multiple strategies available
- ✅ **Search & Discovery** - Full-text entity search
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
- Link photos to devices with `HAS_BLOB` relationship
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

# Create a user NOTE with photo references
photo_note = Entity(
    entity_type=EntityType.NOTE,
    name="Installation Photos",
    content={
        "content": "Photos from HVAC installation",
        "category": "photo_documentation",
        "has_blob": True,
        "blob_references": ["blob_id_1", "blob_id_2"]
    }
)

# Link device to app
relationship = EntityRelationship(
    from_entity_id=device.id,
    to_entity_id=app.id,
    relationship_type=RelationshipType.CONTROLLED_BY_APP,
    properties={"integration": "wifi_adapter"}
)
```

### UGC Relationship Types
- **CONTROLLED_BY_APP** - Device controlled by mobile/web app
- **DOCUMENTED_BY** - Entity documented by note or manual
- **HAS_BLOB** - Entity has associated binary data

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

A working single-house reference implementation:
- Authenticated data endpoints (bearer token), `funkygibbon setup-auth`
- Protocol-correct sync (canonical versions, server_time watermark, one conflict
  resolver, tombstone deletes)
- 12 MCP tools; blowing-off also runs as an MCP server
- Backup/restore + scheduler; data-migration and upgrade tooling
- User Generated Content (PDFs, photos, notes) with BLOB storage
- CI green on Linux/macOS

Ready for deployment and use! 🚀
