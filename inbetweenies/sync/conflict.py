"""
Inbetweenies Protocol - Conflict Resolution

DEVELOPMENT CONTEXT:
Created in July 2025 as part of the Inbetweenies protocol implementation.
This module implements the last-write-wins conflict resolution strategy
for bidirectional sync between FunkyGibbon server and clients.

FUNCTIONALITY:
- Last-write-wins conflict resolution
- Timezone-aware timestamp comparison
- Sync ID tiebreaker for same-second conflicts
- Handles string and datetime timestamps
- Returns detailed resolution information

PURPOSE:
Provides a consistent conflict resolution strategy across all implementations
of the Inbetweenies protocol. This ensures data consistency when multiple
clients modify the same entity.

KNOWN ISSUES:
- Resolution within 1 second uses sync_id (arbitrary)
- No merge strategies (only last-write-wins)
- Timezone handling could be more robust

REVISION HISTORY:
- 2025-07-28: Initial implementation
- 2025-07-29: Enhanced timezone handling
- 2025-07-29: Fixed None sync_id comparison

DEPENDENCIES:
- datetime: Timezone-aware comparisons
- enum: Resolution result types
"""

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any, Dict


@dataclass
class ConflictResolution:
    """Represents the result of conflict resolution between local and remote entities."""
    winner: Dict[str, Any]
    loser: Dict[str, Any]
    reason: str
    timestamp_diff_ms: int


class ConflictResolver:
    """Handles last-write-wins conflict resolution for the Inbetweenies protocol."""
    
    @staticmethod
    def resolve(local: Dict[str, Any], remote: Dict[str, Any]) -> ConflictResolution:
        """
        Resolve conflicts using last-write-wins strategy.
        
        Args:
            local: Local entity data
            remote: Remote entity data
            
        Returns:
            ConflictResolution with winner and reason
        """
        # Handle both string and datetime objects, normalize to UTC
        def normalize_datetime(dt):
            """Normalize datetime to UTC timezone-aware."""
            if isinstance(dt, str):
                # Handle string format
                if dt.endswith('Z'):
                    dt = dt.replace('Z', '+00:00')
                parsed = datetime.fromisoformat(dt)
                # If still timezone-naive after parsing, assume UTC
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed
            else:
                # Handle datetime object
                if dt.tzinfo is None:
                    # Timezone-naive, assume UTC
                    return dt.replace(tzinfo=UTC)
                else:
                    # Already timezone-aware, convert to UTC
                    return dt.astimezone(UTC)
        
        local_ts = normalize_datetime(local["updated_at"])
        remote_ts = normalize_datetime(remote["updated_at"])
        
        # Calculate millisecond difference
        diff_ms = int((remote_ts - local_ts).total_seconds() * 1000)
        
        if abs(diff_ms) < 1000:  # Within 1 second, use sync_id as tiebreaker
            remote_sync_id = remote.get("sync_id") or ""
            local_sync_id = local.get("sync_id") or ""
            if remote_sync_id > local_sync_id:
                return ConflictResolution(
                    winner=remote,
                    loser=local,
                    reason="timestamps equal, remote has higher sync_id",
                    timestamp_diff_ms=diff_ms
                )
            else:
                return ConflictResolution(
                    winner=local,
                    loser=remote,
                    reason="timestamps equal, local has higher sync_id",
                    timestamp_diff_ms=diff_ms
                )
        
        if remote_ts > local_ts:
            return ConflictResolution(
                winner=remote,
                loser=local,
                reason="remote has newer timestamp",
                timestamp_diff_ms=diff_ms
            )
        else:
            return ConflictResolution(
                winner=local,
                loser=remote,
                reason="local has newer timestamp",
                timestamp_diff_ms=diff_ms
            )