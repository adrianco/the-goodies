<!--
The Goodies - Inbetweenies Synchronization Protocol

DEVELOPMENT CONTEXT:
Created to define the synchronization protocol between FunkyGibbon server
and Blowing-Off/WildThing clients. Designed for offline-first operation
with eventual consistency.

DOCUMENT PURPOSE:
Technical specification for the bidirectional sync protocol that enables
distributed clients to maintain consistency with the central server while
supporting offline operation.

REVISION HISTORY:
- 2024-01-15: Initial protocol design with five-phase sync
- 2024-01-15: Added conflict resolution rules
- 2024-01-15: Defined message formats and error handling

KEY DESIGN DECISIONS:
- Delta sync for efficiency
- Idempotent operations for reliability
- Explicit conflict reporting
- Client-tracked sync state
- JSON over HTTPS for simplicity

IMPLEMENTATION STATUS:
- Python (Blowing-Off): ✅ Complete
- Swift (WildThing): 📋 Pending
-->

# Inbetweenies Synchronization Protocol

## Overview

The Inbetweenies protocol enables efficient bidirectional synchronization between FunkyGibbon servers and Blowing-off/WildThing clients. It's designed for:
- Low-bandwidth operation
- Conflict resolution with last-write-wins
- Offline resilience
- Batch efficiency

## Protocol Design

### Core Principles

1. **Delta Sync**: Only changed entities since last sync
2. **Batch Operations**: Multiple changes in single request
3. **Idempotent**: Safe to retry failed syncs
4. **Stateless Server**: Client tracks sync state
5. **Conflict Transparency**: Explicit conflict reporting

### Sync Flow

```
Client                          Server
  |                               |
  |-------- 1. SYNC_REQUEST ----->|
  |         (last_sync_time)      |
  |                               |
  |<------- 2. SYNC_DELTA --------|
  |      (changes + conflicts)    |
  |                               |
  |-------- 3. SYNC_PUSH -------->|
  |       (local changes)         |
  |                               |
  |<------- 4. SYNC_RESULT -------|
  |     (applied + conflicts)     |
  |                               |
  |-------- 5. SYNC_ACK --------->|
  |       (confirm complete)      |
```

## Message Formats

### 1. Sync Request
```json
{
  "type": "sync_request",
  "client_id": "uuid",
  "last_sync": "2024-01-15T10:30:00Z",
  "entity_types": ["devices", "entity_states", "rooms"],
  "include_deleted": false
}
```

### 2. Sync Delta Response
```json
{
  "type": "sync_delta",
  "server_time": "2024-01-15T10:35:00Z",
  "changes": [
    {
      "entity_type": "device",
      "entity_id": "device-123",
      "operation": "update",
      "data": { ... },
      "updated_at": "2024-01-15T10:33:00Z",
      "sync_id": "server-abc"
    }
  ],
  "conflicts": [],
  "more": false
}
```

### 3. Sync Push
```json
{
  "type": "sync_push",
  "client_id": "uuid",
  "changes": [
    {
      "entity_type": "entity_state",
      "entity_id": "state-456",
      "operation": "update",
      "data": {
        "state": {"power": "on"},
        "updated_at": "2024-01-15T10:34:00Z"
      },
      "client_sync_id": "client-xyz"
    }
  ]
}
```

### 4. Sync Result
```json
{
  "type": "sync_result",
  "applied": [
    {
      "client_sync_id": "client-xyz",
      "server_sync_id": "server-def",
      "status": "applied"
    }
  ],
  "conflicts": [
    {
      "entity_type": "device",
      "entity_id": "device-789",
      "reason": "newer_on_server",
      "server_version": { ... },
      "client_version": { ... },
      "resolution": "server_wins"
    }
  ]
}
```

### 5. Sync Acknowledgment
```json
{
  "type": "sync_ack",
  "client_id": "uuid",
  "sync_completed_at": "2024-01-15T10:35:00Z"
}
```

## Conflict Resolution

### Last-Write-Wins Rules

1. **Timestamp Comparison**: Entity with latest `updated_at` wins
2. **Tie Breaking**: If timestamps within 1 second, higher `sync_id` wins
3. **Delete Priority**: Deletes always win over updates with same timestamp
4. **Client Notification**: All conflicts reported to client

### Conflict Types

- **UPDATE_UPDATE**: Both client and server updated same entity
- **UPDATE_DELETE**: One side updated, other deleted
- **CREATE_CREATE**: Both created entity with same ID (rare)

## Optimization Strategies

### Compression
- Gzip compression for payloads >1KB
- Binary encoding for state data
- Field omission for unchanged values

### Batching
- Max 1000 entities per sync cycle
- Pagination for large changesets
- Priority ordering (states > devices > rooms)

### Polling
- Adaptive intervals based on activity
- Minimum: 5 seconds
- Maximum: 5 minutes
- Instant push for critical changes

## Error Handling

### Retry Strategy
- Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s
- Max retries: 5
- Persistent failures: Enter offline mode

### Error Codes
- `SYNC_CONFLICT`: Unresolvable conflict
- `INVALID_SYNC_STATE`: Client too far behind
- `RATE_LIMITED`: Too many sync requests
- `AUTH_EXPIRED`: Re-authentication needed

## Security

### Authentication
- Bearer token in Authorization header
- Token refresh before expiry
- Secure token storage on client

### Data Integrity
- HMAC signature for sync messages
- TLS for transport encryption
- Entity-level access control

## Implementation Details

### Server Endpoints
- `POST /api/v1/sync/request` - Initiate sync
- `POST /api/v1/sync/push` - Push changes
- `POST /api/v1/sync/ack` - Acknowledge completion

### Client State
```python
@dataclass
class SyncState:
    last_sync: datetime
    pending_changes: List[Change]
    sync_in_progress: bool
    failed_syncs: int
    next_retry: datetime
```

### Performance Targets
- Sync latency: <500ms for typical home
- Bandwidth: <10KB per sync cycle
- Battery impact: <1% per hour
- Memory usage: <50MB client-side

## Testing Scenarios

1. **Basic Sync**: Client and server in sync
2. **Conflict Resolution**: Concurrent updates
3. **Offline Recovery**: Extended offline period
4. **Large Dataset**: 1000+ entity changes
5. **Network Failures**: Mid-sync interruptions
6. **Clock Skew**: Client/server time mismatch
7. **Authentication**: Token expiry during sync
8. **Concurrent Clients**: Multiple clients syncing

## Future Enhancements

1. **Push Notifications**: Server-initiated sync
2. **Selective Sync**: Sync specific rooms/devices
3. **Sync History**: Audit trail of all syncs
4. **Mesh Sync**: Peer-to-peer client sync
5. **Differential Compression**: Smart deltas