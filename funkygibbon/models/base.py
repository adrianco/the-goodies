"""
Base model classes for FunkyGibbon entities.
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