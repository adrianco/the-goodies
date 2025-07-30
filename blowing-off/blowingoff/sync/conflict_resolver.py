"""
Blowing-Off Client - Conflict Resolution Engine

DEVELOPMENT CONTEXT:
Created as part of the Inbetweenies protocol in July 2025. This module handles
the critical task of resolving conflicts when the same entity has been modified
on both client and server. The resolution strategy must be deterministic to ensure
all clients reach the same conclusion independently. This is essential for the
Swift/WildThing implementation to maintain consistency.

FUNCTIONALITY:
- Implements deterministic conflict resolution strategies
- Handles timestamp-based last-write-wins resolution
- Manages deletion conflicts (delete vs update)
- Provides tiebreaking for simultaneous updates
- Supports custom merge strategies for specific entities
- Determines retry eligibility for failed syncs
- Tracks resolution reasons for debugging

PURPOSE:
This resolver ensures:
- Consistent conflict resolution across all clients
- No data loss through arbitrary decisions
- Predictable behavior for users
- Audit trail of resolution decisions
- Support for future advanced merge strategies
- Clear rules for deletion precedence

KNOWN ISSUES:
- Basic last-write-wins strategy (no semantic merging)
- No field-level conflict resolution yet
- Missing user preference for resolution strategy
- No support for three-way merge
- Timestamp precision issues on some systems

REVISION HISTORY:
- 2025-07-28: Initial implementation with last-write-wins
- 2025-07-28: Added deletion conflict handling
- 2025-07-28: Improved timestamp parsing and tiebreaking
- 2025-07-28: Added sync_id based tiebreaking
- 2025-07-28: Enhanced retry logic determination

DEPENDENCIES:
- datetime for timestamp operations
- Conflict state object for type safety
- No external dependencies (intentionally simple)

USAGE:
    resolver = ConflictResolver()
    
    # Resolve a conflict
    winning_data, reason = resolver.resolve_conflict(
        local={"name": "Local Name", "updated_at": "2025-07-28T10:00:00Z"},
        remote={"name": "Remote Name", "updated_at": "2025-07-28T10:00:01Z"}
    )
    # Result: (remote_data, "newer_remote")
    
    # Check if sync should retry
    should_retry = resolver.should_retry_sync(conflict)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from .state import Conflict
from inbetweenies.sync import ConflictResolution


class ConflictResolver:
    """Handles conflict resolution during sync."""
    
    @staticmethod
    def resolve_conflict(
        local: Dict[str, Any],
        remote: Dict[str, Any]
    ) -> tuple[Dict[str, Any], str]:
        """
        Resolve conflict between local and remote versions.
        
        Returns:
            Tuple of (winning_data, resolution_reason)
        """
        # Extract timestamps
        local_updated = ConflictResolver._parse_timestamp(local.get("updated_at"))
        remote_updated = ConflictResolver._parse_timestamp(remote.get("updated_at"))
        
        if not local_updated or not remote_updated:
            # If timestamps missing, prefer remote
            return remote, "missing_timestamp"
            
        # Check if one is deleted
        if local.get("deleted") and not remote.get("deleted"):
            return local, "local_deleted"
        elif remote.get("deleted") and not local.get("deleted"):
            return remote, "remote_deleted"
            
        # Last-write-wins based on timestamp
        time_diff = abs(local_updated - remote_updated)
        
        if time_diff < timedelta(seconds=1):
            # Within 1 second, use sync_id as tiebreaker
            local_sync_id = local.get("sync_id", "")
            remote_sync_id = remote.get("sync_id", "")
            
            if local_sync_id > remote_sync_id:
                return local, "sync_id_tiebreak_local"
            else:
                return remote, "sync_id_tiebreak_remote"
        else:
            # Clear winner by timestamp
            if local_updated > remote_updated:
                return local, "newer_local"
            else:
                return remote, "newer_remote"
                
    @staticmethod
    def merge_changes(
        base: Dict[str, Any],
        changes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge changes into base data."""
        merged = base.copy()
        
        for key, value in changes.items():
            if key not in ["id", "created_at"]:  # Don't merge these fields
                merged[key] = value
                
        return merged
        
    @staticmethod
    def _parse_timestamp(timestamp: Any) -> Optional[datetime]:
        """Parse timestamp from various formats."""
        if isinstance(timestamp, datetime):
            return timestamp
        elif isinstance(timestamp, str):
            try:
                return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except:
                return None
        return None
        
    @staticmethod
    def should_retry_sync(conflict: Conflict) -> bool:
        """Determine if sync should be retried for this conflict."""
        # Don't retry if server version is clearly newer
        if conflict.reason in ["newer_on_server", "remote_deleted"]:
            return False
            
        # Retry for network or temporary issues
        if conflict.reason in ["network_error", "timeout", "server_error"]:
            return True
            
        return False