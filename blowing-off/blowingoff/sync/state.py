"""
Blowing-Off Client - Re-export shared sync state types

This module now re-exports the shared sync types from inbetweenies
to maintain backward compatibility while using the shared protocol definitions.
"""

# Import shared sync types from inbetweenies
from inbetweenies.sync import (
    SyncOperation,
    Change,
    Conflict,
    SyncState,
    SyncResult
)

# Re-export for backward compatibility
__all__ = [
    'SyncOperation',
    'Change', 
    'Conflict',
    'SyncState',
    'SyncResult'
]