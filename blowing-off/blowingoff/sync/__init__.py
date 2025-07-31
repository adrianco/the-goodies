"""
Blowing-Off Client - Synchronization Package

DEVELOPMENT CONTEXT:
Created as the core synchronization implementation in July 2025. This package
contains all components needed to implement the Inbetweenies protocol for
bidirectional sync between local and cloud databases. It's the most critical
package that the Swift/WildThing client must replicate accurately to ensure
protocol compatibility.

FUNCTIONALITY:
- Implements complete Inbetweenies protocol specification
- Orchestrates sync cycles with proper state management
- Handles conflict detection and resolution
- Manages sync metadata and recovery
- Provides protocol message serialization
- Ensures atomic sync operations
- Tracks sync performance metrics

PURPOSE:
This package enables:
- Offline-first operation with eventual consistency
- Multi-client synchronization
- Conflict resolution without data loss
- Automatic retry and recovery
- Protocol compatibility across platforms
- Efficient incremental synchronization

KNOWN ISSUES:
- No compression for sync payloads
- Limited to HTTP transport currently
- Missing partial sync for large datasets
- Basic conflict resolution strategy

REVISION HISTORY:
- 2025-07-28: Initial protocol implementation
- 2025-07-28: Added conflict resolution
- 2025-07-28: Enhanced state management
- 2025-07-28: Added performance tracking
- 2025-07-28: Improved error recovery

DEPENDENCIES:
- httpx for async HTTP communication
- Internal state management objects
- Repository layer for data access
- Conflict resolver for merge logic

USAGE:
    from blowingoff.sync import SyncEngine
    
    # Create and run sync
    engine = SyncEngine(session, server_url, auth_token)
    result = await engine.sync()
    
    if result.success:
        print(f"Synced {result.synced_entities} entities")
    else:
        print(f"Sync failed: {result.errors}")
"""

from .protocol import InbetweeniesProtocol
from .engine import SyncEngine
from .conflict_resolver import ConflictResolver
from inbetweenies.sync import SyncState, SyncResult

__all__ = [
    "InbetweeniesProtocol",
    "SyncEngine",
    "ConflictResolver",
    "SyncState",
    "SyncResult",
]