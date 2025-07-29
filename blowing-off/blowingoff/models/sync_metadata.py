"""
Blowing-Off Client - Sync Metadata Model

DEVELOPMENT CONTEXT:
Created as part of the Inbetweenies protocol implementation in January 2024.
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
- 2024-01-15: Initial implementation with basic tracking
- 2024-01-18: Added retry scheduling support
- 2024-01-20: Enhanced failure tracking and recovery
- 2024-01-22: Added conflict counting

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

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Text
from .base import Base


class SyncMetadata(Base):
    """Track overall sync state and history."""
    
    __tablename__ = "sync_metadata"
    
    id = Column(Integer, primary_key=True)
    client_id = Column(String(50), nullable=False, unique=True)
    last_sync_time = Column(DateTime, nullable=True)
    last_sync_success = Column(DateTime, nullable=True)
    last_sync_error = Column(Text, nullable=True)
    sync_failures = Column(Integer, default=0)
    total_syncs = Column(Integer, default=0)
    total_conflicts = Column(Integer, default=0)
    
    # Connection info
    server_url = Column(String(255), nullable=True)
    auth_token = Column(String(500), nullable=True)
    
    # Sync state
    sync_in_progress = Column(Integer, default=0)  # Boolean as int
    next_retry_time = Column(DateTime, nullable=True)
    
    def record_sync_start(self):
        """Record that a sync has started."""
        self.sync_in_progress = 1
        self.last_sync_time = datetime.now()
        
    def record_sync_success(self):
        """Record successful sync completion."""
        self.sync_in_progress = 0
        self.last_sync_success = datetime.now()
        self.last_sync_error = None
        self.sync_failures = 0
        self.total_syncs += 1
        self.next_retry_time = None
        
    def record_sync_failure(self, error: str, next_retry: datetime):
        """Record sync failure."""
        self.sync_in_progress = 0
        self.last_sync_error = error
        self.sync_failures += 1
        self.total_syncs += 1
        self.next_retry_time = next_retry