"""
Shared sync protocol models for the Inbetweenies v2 protocol.

These models define the structure of sync requests and responses
used between FunkyGibbon server and clients like Blowing-Off.
"""

from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class VectorClock(BaseModel):
    """Vector clock for tracking sync state"""
    clocks: Dict[str, str] = Field(default_factory=dict)


class EntityChange(BaseModel):
    """Entity change in sync request"""
    id: str
    version: str
    entity_type: str
    name: str
    content: Dict
    source_type: str
    user_id: str
    parent_versions: List[str] = Field(default_factory=list)
    checksum: Optional[str] = None


class RelationshipChange(BaseModel):
    """Relationship change in sync request"""
    id: str
    from_entity_id: str
    from_entity_version: str
    to_entity_id: str
    to_entity_version: str
    relationship_type: str
    properties: Dict = Field(default_factory=dict)


class SyncChange(BaseModel):
    """Individual change in sync request"""
    change_type: str = Field(..., pattern="^(create|update|delete)$")
    entity: Optional[EntityChange] = None
    relationships: List[RelationshipChange] = Field(default_factory=list)


class SyncFilters(BaseModel):
    """Filters for sync request"""
    entity_types: Optional[List[str]] = None
    since: Optional[datetime] = None
    modified_by: Optional[List[str]] = None


class SyncRequest(BaseModel):
    """Sync request from client"""
    protocol_version: str = "inbetweenies-v2"
    device_id: str
    user_id: str
    sync_type: str = Field(..., pattern="^(full|delta|entities|relationships)$")
    vector_clock: VectorClock = Field(default_factory=VectorClock)
    changes: List[SyncChange] = Field(default_factory=list)
    cursor: Optional[str] = None
    filters: Optional[SyncFilters] = None


class ConflictInfo(BaseModel):
    """Conflict information in sync response"""
    entity_id: str
    local_version: str
    remote_version: str
    resolution_strategy: str
    resolved_version: Optional[str] = None


class SyncStats(BaseModel):
    """Sync statistics"""
    entities_synced: int = 0
    relationships_synced: int = 0
    conflicts_resolved: int = 0
    duration_ms: float = 0


class SyncResponse(BaseModel):
    """Sync response to client"""
    protocol_version: str = "inbetweenies-v2"
    sync_type: str
    changes: List[SyncChange] = Field(default_factory=list)
    conflicts: List[ConflictInfo] = Field(default_factory=list)
    vector_clock: VectorClock = Field(default_factory=VectorClock)
    cursor: Optional[str] = None
    sync_stats: SyncStats = Field(default_factory=SyncStats)
