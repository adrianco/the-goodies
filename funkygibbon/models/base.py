"""
FunkyGibbon - Base Model Classes and Mixins

DEVELOPMENT CONTEXT:
Created in January 2024 as the foundation for all database models in the
simplified single-house smart home system. This module embodies key design
decisions: UUID-based IDs for sync, soft deletes, and timestamp-based
conflict resolution ("last write wins").

FUNCTIONALITY:
- Provides Base declarative class for all SQLAlchemy models
- TimestampMixin adds created_at/updated_at with UTC timestamps
- BaseEntity provides common fields for all entities (id, sync_id, version)
- Supports soft deletes via is_deleted flag
- Includes metadata_json for flexible schema evolution
- ConflictResolution model for sync conflict reporting
- Automatic timestamp conversion to milliseconds for easy comparison

PURPOSE:
Ensures consistency across all database models and implements the core
patterns needed for bidirectional sync with conflict resolution. The
design prioritizes simplicity over complex distributed systems patterns.

KNOWN ISSUES:
- Version field is string-based, not a proper increment counter
- No automatic version bumping on updates (must be handled manually)
- metadata_json is Text not JSON type (SQLite compatibility)
- Soft deletes can accumulate and impact performance over time
- No built-in mechanism to prevent sync_id collisions across devices

REVISION HISTORY:
- 2024-01-15: Initial implementation with basic timestamp mixin
- 2024-01-16: Added sync_id and version fields for synchronization
- 2024-01-17: Added soft delete support with is_deleted flag
- 2024-01-18: Added metadata_json for flexible attributes
- 2024-01-19: Added ConflictResolution model for sync reporting

DEPENDENCIES:
- sqlalchemy: ORM framework and database toolkit
- pydantic: Data validation for API models
- uuid: Generate unique identifiers
- datetime: UTC timestamp handling

USAGE:
# Create a new model:
class Device(Base, BaseEntity):
    __tablename__ = "devices"
    name = Column(String(100), nullable=False)
    # Inherits id, sync_id, version, timestamps, etc.

# Check conflicts:
if entity1.timestamp_millis > entity2.timestamp_millis:
    # entity1 wins
"""

import uuid
from datetime import datetime, UTC
from typing import Any, Dict

from sqlalchemy import Column, DateTime, String, Text, func
from sqlalchemy.orm import declarative_base, declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from pydantic import BaseModel, Field


Base = declarative_base()


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps with last-write-wins support."""
    
    @declared_attr
    def created_at(cls):
        return Column(
            DateTime,
            nullable=False,
            default=lambda: datetime.now(UTC),
            server_default=func.current_timestamp()
        )
    
    @declared_attr
    def updated_at(cls):
        return Column(
            DateTime,
            nullable=False,
            default=lambda: datetime.now(UTC),
            server_default=func.current_timestamp(),
            onupdate=lambda: datetime.now(UTC)
        )
    
    @hybrid_property
    def timestamp_millis(self) -> int:
        """Get updated_at as milliseconds since epoch for easy comparison."""
        return int(self.updated_at.timestamp() * 1000)


class BaseEntity(TimestampMixin):
    """Base class for all entities with ID and timestamps."""
    
    @declared_attr
    def id(cls):
        return Column(
            String(36),
            primary_key=True,
            default=lambda: str(uuid.uuid4())
        )
    
    @declared_attr
    def sync_id(cls):
        """ID used for syncing across devices."""
        return Column(
            String(36),
            nullable=False,
            unique=True,
            default=lambda: str(uuid.uuid4()),
            index=True
        )
    
    @declared_attr
    def version(cls):
        """Simple version counter for optimistic locking."""
        return Column(
            String(36),
            nullable=False,
            default="1"
        )
    
    @declared_attr
    def is_deleted(cls):
        """Soft delete flag."""
        from sqlalchemy import Boolean
        return Column(
            Boolean,
            nullable=False,
            default=False,
            server_default="0"
        )
    
    @declared_attr
    def metadata_json(cls):
        """Flexible JSON storage for additional attributes."""
        return Column(
            Text,
            nullable=True
        )


class ConflictResolution(BaseModel):
    """Conflict resolution result."""
    
    winner: Dict[str, Any]
    loser: Dict[str, Any]
    reason: str = Field(..., description="Reason for resolution decision")
    timestamp_diff_ms: int = Field(..., description="Millisecond difference between versions")
    
    class Config:
        json_schema_extra = {
            "example": {
                "winner": {"id": "123", "name": "Kitchen", "updated_at": "2024-01-01T12:00:00Z"},
                "loser": {"id": "123", "name": "Dining Room", "updated_at": "2024-01-01T11:59:00Z"},
                "reason": "winner has newer timestamp",
                "timestamp_diff_ms": 60000
            }
        }