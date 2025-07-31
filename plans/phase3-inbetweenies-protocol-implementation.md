# Phase 3: Enhanced Inbetweenies Protocol Implementation Plan

## Overview
This document outlines the implementation strategy for the enhanced Inbetweenies synchronization protocol designed specifically for the knowledge graph architecture. The protocol provides efficient, reliable synchronization with support for entities, relationships, versioning, and binary content.

## Protocol Design

### Core Features
1. **Entity & Relationship Sync**: Full support for graph data structures
2. **Immutable Versioning**: Complete version history with parent tracking
3. **Advanced Conflict Resolution**: Multiple strategies including merge support
4. **Delta Synchronization**: Efficient partial updates
5. **Binary Content Support**: Images, PDFs, and other file types

## Protocol Schema

### Sync Request Schema
```json
{
  "protocol_version": "inbetweenies-v2",
  "device_id": "uuid",
  "user_id": "uuid",
  "sync_type": "full|delta|entities|relationships",
  "vector_clock": {
    "device1": "version1",
    "device2": "version2"
  },
  "changes": [
    {
      "change_type": "create|update|delete",
      "entity": {
        "id": "uuid",
        "version": "timestamp-userid",
        "entity_type": "home|room|device|procedure|...",
        "parent_versions": ["version1", "version2"],
        "content": {},
        "checksum": "sha256"
      },
      "relationships": [
        {
          "id": "uuid",
          "from_entity_id": "uuid",
          "to_entity_id": "uuid",
          "relationship_type": "located_in|controls|...",
          "properties": {}
        }
      ]
    }
  ],
  "cursor": "pagination_cursor",
  "filters": {
    "entity_types": ["room", "device"],
    "since": "2025-07-29T00:00:00Z",
    "modified_by": ["user1", "user2"]
  }
}
```

### Sync Response Schema
```json
{
  "protocol_version": "inbetweenies-v2",
  "sync_type": "full|delta|entities|relationships",
  "changes": [...],
  "conflicts": [
    {
      "entity_id": "uuid",
      "local_version": "version1",
      "remote_version": "version2",
      "resolution_strategy": "last_write_wins|manual|merge",
      "resolved_version": "version3"
    }
  ],
  "vector_clock": {...},
  "cursor": "next_page_cursor",
  "sync_stats": {
    "entities_synced": 150,
    "relationships_synced": 300,
    "conflicts_resolved": 2,
    "duration_ms": 145
  }
}
```

## Implementation Components

### Version Management
```python
# funkygibbon/sync/versioning.py
class VersionManager:
    """Manage immutable entity versions"""
    
    def create_version(self, entity: Entity, parent_versions: List[str]) -> str:
        """Create new version with parent tracking"""
        timestamp = datetime.utcnow().isoformat()
        return f"{timestamp}Z-{entity.user_id}"
    
    def get_version_history(self, entity_id: str) -> List[Entity]:
        """Get complete version history for entity"""
        
    def merge_versions(self, versions: List[Entity]) -> Entity:
        """Merge multiple versions into new version"""
        
    def calculate_version_tree(self, entity_id: str) -> VersionTree:
        """Build version tree for visualization"""
```

### Conflict Resolution Engine
```python
# funkygibbon/sync/conflict_resolution.py
class ConflictResolver:
    """Advanced conflict resolution strategies"""
    
    def resolve_conflict(self, local: Entity, remote: Entity, 
                        strategy: ConflictStrategy) -> Entity:
        """Resolve conflicts based on strategy"""
        
        if strategy == ConflictStrategy.LAST_WRITE_WINS:
            return self._last_write_wins(local, remote)
        elif strategy == ConflictStrategy.MERGE:
            return self._merge_entities(local, remote)
        elif strategy == ConflictStrategy.MANUAL:
            return self._queue_for_manual_resolution(local, remote)
        elif strategy == ConflictStrategy.CUSTOM:
            return self._apply_custom_rules(local, remote)
    
    def _merge_entities(self, local: Entity, remote: Entity) -> Entity:
        """Intelligent content merging"""
        # Deep merge JSON content
        # Preserve both sets of relationships
        # Create new version with both as parents
```

### Delta Sync Engine
```python
# funkygibbon/sync/delta.py
class DeltaSyncEngine:
    """Efficient delta synchronization"""
    
    def calculate_delta(self, last_sync: datetime, 
                       entity_types: List[EntityType] = None) -> SyncDelta:
        """Calculate changes since last sync"""
        
    def apply_delta(self, delta: SyncDelta) -> SyncResult:
        """Apply delta changes to local state"""
        
    def create_merkle_tree(self, entities: List[Entity]) -> MerkleTree:
        """Create merkle tree for efficient comparison"""
        
    def compute_sync_checksum(self, entities: List[Entity]) -> str:
        """Compute overall state checksum"""
```

### Binary Content Handler
```python
# funkygibbon/sync/binary.py
class BinaryContentSync:
    """Handle binary content synchronization"""
    
    def prepare_binary_sync(self, content: BinaryContent) -> dict:
        """Prepare binary content for sync"""
        return {
            "id": content.id,
            "entity_id": content.entity_id,
            "content_type": content.content_type,
            "size": len(content.data),
            "checksum": content.checksum,
            "compression": "gzip",
            "sync_url": self._generate_sync_url(content)
        }
    
    async def sync_binary_content(self, content_id: str, 
                                 sync_url: str) -> BinaryContent:
        """Download/upload binary content with resume support"""
        
    async def validate_content(self, content: BinaryContent) -> bool:
        """Validate content integrity after transfer"""
```

### Chunked Transfer Manager
```python
# funkygibbon/sync/transfer.py
class ChunkedTransfer:
    """Handle large binary transfers with resume support"""
    
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    
    async def upload_chunks(self, data: bytes, 
                           upload_url: str) -> TransferResult:
        """Upload data in chunks with progress tracking"""
        
    async def download_chunks(self, chunk_urls: List[str]) -> bytes:
        """Download and reassemble chunks"""
        
    async def resume_transfer(self, transfer_id: str) -> TransferResult:
        """Resume interrupted transfer"""
```

## Client Implementation

### Enhanced Sync Client
```python
# blowing-off/sync/client.py
class EnhancedSyncClient:
    """Sync client with full graph support"""
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.version_manager = VersionManager()
        self.conflict_resolver = ConflictResolver()
        self.delta_engine = DeltaSyncEngine()
        
    async def sync_entities(self, entity_types: List[EntityType] = None,
                           since: datetime = None) -> SyncResult:
        """Sync entities with filtering and progress tracking"""
        
    async def sync_relationships(self, entity_id: str = None) -> SyncResult:
        """Sync relationships for entities"""
        
    async def resolve_conflicts(self, strategy: ConflictStrategy) -> List[Entity]:
        """Resolve all pending conflicts"""
```

### Sync State Manager
```python
# blowing-off/sync/state.py
class SyncStateManager:
    """Manage local sync state and metadata"""
    
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.vector_clock = {}
        self.pending_changes = []
        
    def update_vector_clock(self, device_id: str, version: str):
        """Update vector clock for device"""
        
    def get_pending_changes(self) -> List[Change]:
        """Get changes pending sync"""
        
    def mark_synced(self, entity_id: str, version: str):
        """Mark entity version as synced"""
        
    def get_sync_metrics(self) -> SyncMetrics:
        """Get sync performance metrics"""
```

## Server Implementation

### Sync Server Handler
```python
# funkygibbon/api/sync.py
class SyncHandler:
    """Handle sync protocol requests"""
    
    async def handle_sync_request(self, request: SyncRequest) -> SyncResponse:
        """Process sync request and return changes"""
        
    async def validate_vector_clock(self, clock: dict) -> bool:
        """Validate vector clock consistency"""
        
    async def process_changes(self, changes: List[Change]) -> ProcessResult:
        """Apply incoming changes to server state"""
```

## Testing Strategy

### Unit Tests
```python
# tests/unit/test_version_manager.py
- Test version string generation
- Test parent version tracking
- Test version history retrieval
- Test version merging logic

# tests/unit/test_conflict_resolution.py
- Test each resolution strategy
- Test merge algorithm correctness
- Test manual conflict queuing
- Test custom rule application

# tests/unit/test_delta_sync.py
- Test delta calculation accuracy
- Test merkle tree generation
- Test checksum computation
- Test delta application
```

### Integration Tests
```python
# tests/integration/test_sync_flow.py
- Test complete sync cycle
- Test multi-device synchronization
- Test conflict generation and resolution
- Test binary content sync

# tests/integration/test_performance.py
- Test sync with 10k+ entities
- Test delta sync efficiency
- Test concurrent sync operations
- Test network failure recovery
```

### End-to-End Tests
```python
# tests/e2e/test_sync_scenarios.py
- Test offline-first operation
- Test multi-user collaboration
- Test large file synchronization
- Test sync under poor network conditions
```

## Performance Targets

- **Sync Latency**: < 500ms for typical sync
- **Delta Efficiency**: > 80% bandwidth reduction vs full sync
- **Conflict Resolution**: < 100ms per conflict
- **Binary Transfer**: > 5MB/s sustained transfer rate
- **Concurrent Clients**: Support 100+ simultaneous sync operations

## Implementation Timeline

### Week 1: Core Protocol
- **Day 1**: Implement version management system
- **Day 2**: Build conflict resolution engine
- **Day 3**: Create delta sync calculations
- **Day 4**: Implement sync state management
- **Day 5**: Unit testing and integration

### Week 2: Advanced Features
- **Day 1**: Add binary content support
- **Day 2**: Implement chunked transfers
- **Day 3**: Build sync server handlers
- **Day 4**: Create monitoring and metrics
- **Day 5**: Performance testing and optimization

## Risk Assessment

### Technical Risks
- **Risk**: Complex conflict resolution scenarios
  - **Mitigation**: Provide clear resolution strategies, extensive testing
  
- **Risk**: Network reliability issues
  - **Mitigation**: Implement resume support, retry logic, offline queue

### Operational Risks  
- **Risk**: Storage growth from version history
  - **Mitigation**: Implement version pruning, compression strategies

- **Risk**: Sync performance at scale
  - **Mitigation**: Use efficient data structures, implement caching

## Success Criteria

1. **Reliability**: 99.9% sync success rate
2. **Performance**: Meet all latency targets
3. **Efficiency**: 80%+ bandwidth reduction with delta sync
4. **Scalability**: Handle 100+ concurrent clients
5. **Data Integrity**: Zero data loss, accurate conflict resolution

## Next Steps

Upon completion of Phase 3:
1. Deploy sync infrastructure with monitoring
2. Implement Phase 4: Swift/WildThing client
3. Add real-time sync via WebSockets
4. Build sync analytics dashboard