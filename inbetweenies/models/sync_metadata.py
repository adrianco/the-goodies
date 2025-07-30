"""
Inbetweenies - Sync Metadata Model

DEVELOPMENT CONTEXT:
Created as part of the Inbetweenies protocol implementation in July 2025.
This model tracks the overall synchronization state and history for each client
instance. It serves as the central record of sync operations, failures, and
recovery state, enabling robust offline-first operation.

FUNCTIONALITY:
- Tracks sync operation history and statistics
- Records last successful sync and failure information
- Maintains retry scheduling for failed syncs
- Stores connection credentials securely
- Monitors sync operation progress
- Counts total syncs, failures, and conflicts
- Provides methods for recording sync lifecycle events

PURPOSE:
This metadata enables:
- Reliable sync recovery after failures
- Exponential backoff for retry logic
- Sync health monitoring and diagnostics
- Prevention of concurrent sync operations
- Historical sync performance tracking
- Credential management for server connections

KNOWN ISSUES:
- Auth token stored in plain text (encryption planned)
- No automatic cleanup of old sync history
- Retry logic could be more sophisticated
- Missing sync bandwidth/data usage tracking

REVISION HISTORY:
- 2025-07-28: Initial implementation with basic tracking
- 2025-07-28: Added retry scheduling support
- 2025-07-28: Enhanced failure tracking and recovery
- 2025-07-28: Added conflict counting
- 2025-01-29: Moved to inbetweenies for shared use

DEPENDENCIES:
- SQLAlchemy for ORM mapping
- Base model with standard fields
- datetime for timestamp tracking

USAGE:
    # Track sync lifecycle
    metadata = await repo.get_by_client(client_id)
    
    metadata.record_sync_start()
    try:
        # Perform sync...
        metadata.record_sync_success()
    except Exception as e:
        next_retry = datetime.now() + timedelta(seconds=30 * (2 ** metadata.sync_failures))
        metadata.record_sync_failure(str(e), next_retry)
"""

from datetime import datetime, UTC
from sqlalchemy import Column, String, DateTime, Integer, Text

from .base import Base, InbetweeniesTimestampMixin


class SyncMetadata(Base, InbetweeniesTimestampMixin):
    """Track overall sync state and history."""
    
    __tablename__ = "sync_metadata"
    
    id = Column(Integer, primary_key=True)
    client_id = Column(String(50), nullable=False, unique=True)
    last_sync_time = Column(DateTime, nullable=True)
    last_sync_success = Column(DateTime, nullable=True)
    last_sync_error = Column(Text, nullable=True)
    sync_failures = Column(Integer, default=0, nullable=False)
    total_syncs = Column(Integer, default=0, nullable=False)
    total_conflicts = Column(Integer, default=0, nullable=False)
    
    # Connection info
    server_url = Column(String(255), nullable=True)
    auth_token = Column(String(500), nullable=True)
    
    # Sync state
    sync_in_progress = Column(Integer, default=0)  # Boolean as int
    next_retry_time = Column(DateTime, nullable=True)
    
    def __init__(self, **kwargs):
        """Initialize with default values."""
        super().__init__(**kwargs)
        if self.sync_failures is None:
            self.sync_failures = 0
        if self.total_syncs is None:
            self.total_syncs = 0
        if self.total_conflicts is None:
            self.total_conflicts = 0
        if self.sync_in_progress is None:
            self.sync_in_progress = 0
    
    def record_sync_start(self):
        """Record that a sync has started."""
        self.sync_in_progress = 1
        self.last_sync_time = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        
    def record_sync_success(self):
        """Record successful sync completion."""
        self.sync_in_progress = 0
        self.last_sync_success = datetime.now(UTC)
        self.last_sync_error = None
        self.sync_failures = 0
        self.total_syncs += 1
        self.next_retry_time = None
        self.updated_at = datetime.now(UTC)
        
    def record_sync_failure(self, error: str, next_retry: datetime):
        """Record sync failure."""
        self.sync_in_progress = 0
        self.last_sync_error = error
        self.sync_failures += 1
        self.total_syncs += 1
        self.next_retry_time = next_retry
        self.updated_at = datetime.now(UTC)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "last_sync_success": self.last_sync_success.isoformat() if self.last_sync_success else None,
            "last_sync_error": self.last_sync_error,
            "sync_failures": self.sync_failures,
            "total_syncs": self.total_syncs,
            "total_conflicts": self.total_conflicts,
            "server_url": self.server_url,
            "sync_in_progress": bool(self.sync_in_progress),
            "next_retry_time": self.next_retry_time.isoformat() if self.next_retry_time else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sync_id": self.sync_id
        }