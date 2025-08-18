"""
Inbetweenies Sync Types - Shared data structures for synchronization

This module defines the common types used by both server and client
implementations of the Inbetweenies sync protocol.
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Dict, List, Optional


class SyncOperation(Enum):
    """Types of sync operations."""
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
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
