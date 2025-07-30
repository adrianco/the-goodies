"""
Inbetweenies Sync Protocol - Shared synchronization logic

This module contains the core synchronization protocol components that are
shared between server (FunkyGibbon) and client (Blowing-Off) implementations.
"""

from .conflict import ConflictResolver, ConflictResolution
from .types import SyncOperation, Change, Conflict, SyncState, SyncResult

__all__ = [
    'ConflictResolver',
    'ConflictResolution',
    'SyncOperation',
    'Change',
    'Conflict',
    'SyncState',
    'SyncResult'
]