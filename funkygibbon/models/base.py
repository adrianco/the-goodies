"""
FunkyGibbon Base Models - Essential classes for sync operations
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from inbetweenies.models import Base


@dataclass
class ConflictResolution:
    """Represents the result of conflict resolution between local and remote entities."""
    winner: Dict[str, Any]
    loser: Dict[str, Any]
    reason: str
    timestamp_diff_ms: int


# Export BaseEntity if needed - using inbetweenies base
BaseEntity = Base

__all__ = [
    'ConflictResolution',
    'BaseEntity',
    'Base'
]
