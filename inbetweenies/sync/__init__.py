"""
Inbetweenies Sync Protocol - Shared synchronization logic

This module contains the core synchronization protocol components that are
shared between server (FunkyGibbon) and client (Blowing-Off) implementations.
"""

from .conflict import ConflictResolver, ConflictResolution
from .types import SyncOperation, Change, Conflict, SyncState, SyncResult
from .protocol import (
    VectorClock, EntityChange, RelationshipChange, SyncChange,
    SyncFilters, SyncRequest, ConflictInfo, SyncStats, SyncResponse
)

__all__ = [
    'ConflictResolver',
    'ConflictResolution',
    'SyncOperation',
    'Change',
    'Conflict',
    'SyncState',
    'SyncResult',
    # Protocol models
    'VectorClock',
    'EntityChange',
    'RelationshipChange',
    'SyncChange',
    'SyncFilters',
    'SyncRequest',
    'ConflictInfo',
    'SyncStats',
    'SyncResponse'
]
