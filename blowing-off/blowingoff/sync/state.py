"""
Blowing-Off Client - Sync State Data Structures

DEVELOPMENT CONTEXT:
Created as the core data structures for sync operations in January 2024. These
dataclasses define the shape of all sync-related data flowing through the system.
They provide type safety and clear contracts for the Inbetweenies protocol
implementation. The Swift/WildThing client must implement equivalent structures
to ensure protocol compatibility.

FUNCTIONALITY:
- Defines sync operation types (CREATE, UPDATE, DELETE)
- Models individual changes with full metadata
- Represents conflicts with resolution information
- Tracks overall sync state and progress
- Provides sync result reporting structure
- Ensures type safety throughout sync operations
- Supports serialization for protocol messages

PURPOSE:
These data structures enable:
- Clear contracts between sync components
- Type-safe sync protocol implementation
- Comprehensive conflict tracking
- Detailed sync result reporting
- Easy debugging with structured data
- Protocol compatibility verification

KNOWN ISSUES:
- Missing validation in dataclass constructors
- No support for partial entity updates
- Conflict resolution strategy not encoded in type
- Missing compression markers for large data

REVISION HISTORY:
- 2024-01-15: Initial dataclass definitions
- 2024-01-18: Added conflict representation
- 2024-01-20: Enhanced change tracking with sync IDs
- 2024-01-22: Added sync result metrics

DEPENDENCIES:
- Python dataclasses for structure definition
- datetime for timestamp handling
- Enum for operation type safety
- Type hints for static analysis

USAGE:
    # Track a change
    change = Change(
        entity_type="device",
        entity_id="light-1",
        operation=SyncOperation.UPDATE,
        data={"state": {"on": True}},
        updated_at=datetime.now(),
        sync_id="sync-123"
    )
    
    # Record sync result
    result = SyncResult(
        success=True,
        synced_entities=15,
        conflicts_resolved=2,
        duration=1.5
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum


class SyncOperation(Enum):
    """Sync operation types."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class Change:
    """Represents a single entity change."""
    entity_type: str
    entity_id: str
    operation: SyncOperation
    data: Dict[str, Any]
    updated_at: datetime
    sync_id: str
    client_sync_id: Optional[str] = None
    

@dataclass
class Conflict:
    """Represents a sync conflict."""
    entity_type: str
    entity_id: str
    reason: str
    server_version: Dict[str, Any]
    client_version: Dict[str, Any]
    resolution: str
    

@dataclass
class SyncState:
    """Current sync state."""
    last_sync: Optional[datetime] = None
    pending_changes: List[Change] = field(default_factory=list)
    sync_in_progress: bool = False
    failed_syncs: int = 0
    next_retry: Optional[datetime] = None
    

@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    synced_entities: int = 0
    conflicts_resolved: int = 0
    conflicts: List[Conflict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration: float = 0.0
    server_time: Optional[datetime] = None