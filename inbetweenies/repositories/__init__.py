"""
Inbetweenies Repository Interfaces - Shared repository patterns

This module defines the repository interfaces that both server and client
implementations should follow for consistent data access patterns.
"""

from .interfaces import (
    BaseSyncRepository,
    SyncCapable,
    ConflictAware,
    ChangeTrackable
)

__all__ = [
    'BaseSyncRepository',
    'SyncCapable',
    'ConflictAware',
    'ChangeTrackable'
]
