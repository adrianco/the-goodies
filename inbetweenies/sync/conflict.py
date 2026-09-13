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
- Timezone handling could be more robust

REVISION HISTORY:
- 2026-09-13: three_way_merge -- ADR-005 §2 rung 3. Keys changed on one side
  take that side; keys changed on both are reported so the caller can settle
  them by LWW (rung 4) for that key set only. Deletion-safe: the base
  distinguishes "deleted" from "never existed", which is the defect that made
  the old two-way merge resurrect deletions.
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
    """The single canonical conflict resolver for the Inbetweenies protocol.

    Last-write-wins on ``updated_at`` (UTC), and when two edits land within a
    1-second window, tiebreak on the ``version`` string (lexically greater wins).
    The version encodes UTC time + a monotonic counter + user id, so it is a
    stable, wire-visible tiebreaker — unlike ``sync_id``, which is not part of the
    wire model. This is the one algorithm; clients and server MUST share it
    (PROTOCOL.md §7).
    """

    @staticmethod
    def resolve(local: Dict[str, Any], remote: Dict[str, Any]) -> ConflictResolution:
        """
        Resolve conflicts using last-write-wins with a version tiebreak.

        Args:
            local: Local entity data (must have ``updated_at`` and ``version``)
            remote: Remote entity data (must have ``updated_at`` and ``version``)

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

        if abs(diff_ms) < 1000:  # Within 1 second: tiebreak on the version string
            remote_version = remote.get("version") or ""
            local_version = local.get("version") or ""
            if remote_version > local_version:
                return ConflictResolution(
                    winner=remote,
                    loser=local,
                    reason="timestamps within 1s, remote has greater version",
                    timestamp_diff_ms=diff_ms
                )
            else:
                return ConflictResolution(
                    winner=local,
                    loser=remote,
                    reason="timestamps within 1s, local has greater version",
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


# --------------------------------------------------------------------------- #
# ADR-005 §2 rung 3 -- three-way field merge
# --------------------------------------------------------------------------- #

_MISSING = object()


@dataclass
class MergeResult:
    """Outcome of a three-way merge of two content dicts against their base."""
    merged: Dict[str, Any]
    #: Keys both sides changed, to different values. Not merged here: the
    #: caller settles them by the ordering rule (rung 4) for this key set only.
    conflicted: set
    #: Keys taken from each side, for the conflict record.
    took_local: set
    took_remote: set


def three_way_merge(base: Dict[str, Any], local: Dict[str, Any],
                    remote: Dict[str, Any]) -> MergeResult:
    """Merge ``local`` and ``remote`` against their common ancestor ``base``.

    Per key, over the union of all three:
    - unchanged on both sides         -> keep
    - changed on one side only        -> take that side (a deletion is a change)
    - changed on both, to the same    -> keep (they agree)
    - changed on both, differently    -> conflicted; left at the base value
      here and reported, for the caller to settle by rung 4

    "Changed" is judged against the base, which is what makes this
    deletion-safe: a key absent on one side and present in the base is a
    deletion by that side, not a key the other side never had.
    """
    merged: Dict[str, Any] = {}
    conflicted, took_local, took_remote = set(), set(), set()
    for key in set(base) | set(local) | set(remote):
        b = base.get(key, _MISSING)
        l = local.get(key, _MISSING)
        r = remote.get(key, _MISSING)
        local_changed = l != b
        remote_changed = r != b
        if not local_changed and not remote_changed:
            chosen = b
        elif local_changed and not remote_changed:
            chosen = l; took_local.add(key)
        elif remote_changed and not local_changed:
            chosen = r; took_remote.add(key)
        elif l == r:
            chosen = l
        else:
            conflicted.add(key); chosen = b
        if chosen is not _MISSING:
            merged[key] = chosen
    return MergeResult(merged=merged, conflicted=conflicted,
                       took_local=took_local, took_remote=took_remote)
