"""
Client-side Sync Tracking Model

DEVELOPMENT CONTEXT:
Created in July 2025 to implement local sync tracking for entities without
modifying the shared Inbetweenies models. This enables the client to detect
which entities have pending changes that need to be synced to the server,
resolving the TODO items in the repository base class.

FUNCTIONALITY:
- Tracks sync status per entity (pending, synced, conflict)
- Records last sync timestamp and operation type
- Maintains conflict information with retry counts
- Supports change detection for incremental sync
- Enables get_pending() and get_conflicts() repository methods
- Works alongside shared HomeKit-compatible models

PURPOSE:
Enables local change tracking for the sync engine without polluting
the shared models with client-specific sync fields. This allows the
Inbetweenies protocol to detect and sync local changes properly.

KNOWN ISSUES:
- No automatic cleanup of old sync records
- No bulk operations for large datasets

REVISION HISTORY:
- 2025-07-29: Initial implementation with sync status tracking
- 2025-07-29: Added conflict tracking and retry logic
- 2025-07-29: Integrated with repository base class methods

DEPENDENCIES:
- inbetweenies.models.Base for declarative base
- SQLAlchemy for ORM mapping
- datetime for UTC timestamp handling

USAGE:
    # Automatically created by repository operations
    await repo.create(id="test-1", name="Test Entity")  # Creates pending record
    await repo.update("test-1", name="Updated")         # Marks as pending
    await repo.mark_synced("test-1", datetime.now())    # Marks as synced

    # Query sync status
    pending_entities = await repo.get_pending()
    conflict_entities = await repo.get_conflicts()
"""

from datetime import datetime, UTC
from sqlalchemy import Column, String, DateTime, Text, Integer
from inbetweenies.models import Base

class ClientSyncTracking(Base):
    """Track sync status for individual entities."""

    __tablename__ = "client_sync_tracking"

    id = Column(Integer, primary_key=True)
    entity_id = Column(String(36), nullable=False)  # References the actual entity
    entity_type = Column(String(50), nullable=False)  # home, room, accessory, user

    # Sync status
    sync_status = Column(String(20), nullable=False, default="pending")  # pending, synced, conflict
    operation = Column(String(10), nullable=False, default="update")  # create, update, delete

    # Timestamps
    entity_updated_at = Column(DateTime, nullable=False)  # When entity was last modified
    last_sync_at = Column(DateTime, nullable=True)  # When last synced to server
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    # Conflict tracking
    conflict_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.retry_count is None:
            self.retry_count = 0

    def mark_pending(self, operation: str = "update"):
        """Mark entity as having pending changes."""
        self.sync_status = "pending"
        self.operation = operation
        self.conflict_reason = None
        self.entity_updated_at = datetime.now(UTC)

    def mark_synced(self):
        """Mark entity as successfully synced."""
        self.sync_status = "synced"
        self.last_sync_at = datetime.now(UTC)
        self.conflict_reason = None
        self.retry_count = 0

    def mark_conflict(self, reason: str):
        """Mark entity as having sync conflict."""
        self.sync_status = "conflict"
        self.conflict_reason = reason
        self.retry_count += 1

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "sync_status": self.sync_status,
            "operation": self.operation,
            "entity_updated_at": self.entity_updated_at.isoformat() if self.entity_updated_at else None,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "conflict_reason": self.conflict_reason,
            "retry_count": self.retry_count
        }
