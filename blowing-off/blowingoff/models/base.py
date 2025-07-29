"""
Blowing-Off Client - Base Models and Sync Tracking

DEVELOPMENT CONTEXT:
Created as the foundation for all client-side database models in January 2024.
This module defines the core sync tracking functionality that enables the
Inbetweenies protocol to maintain consistency between local and cloud databases.
Every entity in the system inherits from these base classes to gain sync capabilities.

FUNCTIONALITY:
- Provides SQLAlchemy declarative base for all models
- Implements ClientTimestampMixin with comprehensive sync tracking fields
- Tracks sync status (synced, pending, conflict, error) for each entity
- Maintains timestamps for creation, updates, and sync operations
- Supports optimistic locking with version numbers
- Handles conflict detection and error tracking
- Enables offline-first operation with local change tracking

PURPOSE:
This module ensures:
- Every entity can be tracked for synchronization
- Local changes are properly marked and versioned
- Conflicts can be detected and resolved
- Sync errors are captured for retry logic
- Server and client timestamps remain coordinated
- The Swift/WildThing client can implement identical tracking

KNOWN ISSUES:
- UTC timezone handling requires explicit conversion in some databases
- Version increment logic not fully automated yet
- No automatic cleanup of old sync errors
- Sync ID generation could be more robust

REVISION HISTORY:
- 2024-01-15: Initial implementation with basic sync tracking
- 2024-01-18: Added optimistic locking with version numbers
- 2024-01-20: Enhanced conflict and error tracking
- 2024-01-22: Added local_changes flag for offline detection

DEPENDENCIES:
- SQLAlchemy 2.0+ for async ORM support
- Python datetime with UTC timezone support
- Enum for sync status constants

USAGE:
    from .base import Base, ClientTimestampMixin
    
    class ClientDevice(Base, ClientTimestampMixin):
        __tablename__ = "devices"
        
        # Entity fields...
        
        def update_state(self, new_state):
            self.state = new_state
            self.mark_pending()  # Automatically tracks as needing sync
"""

from datetime import datetime, UTC
from typing import Optional
from sqlalchemy import Column, String, DateTime, Integer, Boolean, Enum
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import declarative_base
import enum

Base = declarative_base()


class SyncStatus(enum.Enum):
    """Sync status for client entities."""
    SYNCED = "synced"
    PENDING = "pending"
    CONFLICT = "conflict"
    ERROR = "error"


class ClientTimestampMixin:
    """Mixin for client-side timestamps and sync tracking."""
    
    @declared_attr
    def created_at(cls):
        return Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    
    @declared_attr
    def updated_at(cls):
        return Column(DateTime, nullable=False, default=lambda: datetime.now(UTC), 
                     onupdate=lambda: datetime.now(UTC))
    
    @declared_attr
    def sync_id(cls):
        """Unique sync identifier for conflict resolution."""
        return Column(String(50), nullable=True)
    
    @declared_attr
    def server_updated_at(cls):
        """Last known server update timestamp."""
        return Column(DateTime, nullable=True)
    
    @declared_attr
    def last_sync_at(cls):
        """When this entity was last synced."""
        return Column(DateTime, nullable=True)
    
    @declared_attr
    def sync_status(cls):
        """Current sync status."""
        return Column(Enum(SyncStatus), nullable=False, default=SyncStatus.PENDING)
    
    @declared_attr
    def sync_error(cls):
        """Last sync error if any."""
        return Column(String(500), nullable=True)
    
    @declared_attr
    def local_changes(cls):
        """Track if entity has local changes."""
        return Column(Boolean, nullable=False, default=False)
    
    @declared_attr
    def sync_version(cls):
        """Version number for optimistic locking."""
        return Column(Integer, nullable=False, default=1)
    
    def mark_synced(self, server_updated_at: datetime):
        """Mark entity as synced with server."""
        self.server_updated_at = server_updated_at
        self.last_sync_at = datetime.now(UTC)
        self.sync_status = SyncStatus.SYNCED
        self.sync_error = None
        self.local_changes = False
        
    def mark_pending(self):
        """Mark entity as having pending changes."""
        self.sync_status = SyncStatus.PENDING
        self.local_changes = True
        
    def mark_conflict(self, error: str):
        """Mark entity as having sync conflict."""
        self.sync_status = SyncStatus.CONFLICT
        self.sync_error = error
        
    def mark_error(self, error: str):
        """Mark entity as having sync error."""
        self.sync_status = SyncStatus.ERROR
        self.sync_error = error