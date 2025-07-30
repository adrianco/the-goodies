"""
Conflict resolution strategies for entity synchronization.

Provides multiple strategies for resolving conflicts when the same entity
has been modified on different devices.
"""

from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone
from dataclasses import dataclass
import json

from inbetweenies.models import Entity


class ConflictStrategy(Enum):
    """Available conflict resolution strategies"""
    LAST_WRITE_WINS = "last_write_wins"
    MERGE = "merge"
    MANUAL = "manual"
    CUSTOM = "custom"
    CLIENT_WINS = "client_wins"
    SERVER_WINS = "server_wins"


@dataclass
class ConflictResolution:
    """Result of conflict resolution"""
    strategy: ConflictStrategy
    resolved_entity: Optional[Entity]
    requires_manual: bool = False
    merge_conflicts: List[Dict] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "strategy": self.strategy.value,
            "resolved": self.resolved_entity is not None,
            "requires_manual": self.requires_manual,
            "merge_conflicts": self.merge_conflicts or []
        }


class ConflictResolver:
    """Advanced conflict resolution strategies"""
    
    def __init__(self):
        self.custom_rules: Dict[str, Callable] = {}
        self.pending_manual_resolutions: List[Dict] = []
        
    def register_custom_rule(self, entity_type: str, rule_func: Callable):
        """Register a custom conflict resolution rule for an entity type"""
        self.custom_rules[entity_type] = rule_func
    
    def resolve_conflict(self, local: Entity, remote: Entity, 
                        strategy: ConflictStrategy) -> ConflictResolution:
        """Resolve conflicts based on strategy"""
        
        if strategy == ConflictStrategy.LAST_WRITE_WINS:
            return self._last_write_wins(local, remote)
        elif strategy == ConflictStrategy.MERGE:
            return self._merge_entities(local, remote)
        elif strategy == ConflictStrategy.MANUAL:
            return self._queue_for_manual_resolution(local, remote)
        elif strategy == ConflictStrategy.CUSTOM:
            return self._apply_custom_rules(local, remote)
        elif strategy == ConflictStrategy.CLIENT_WINS:
            return ConflictResolution(strategy=strategy, resolved_entity=local)
        elif strategy == ConflictStrategy.SERVER_WINS:
            return ConflictResolution(strategy=strategy, resolved_entity=remote)
        else:
            raise ValueError(f"Unknown conflict strategy: {strategy}")
    
    def _last_write_wins(self, local: Entity, remote: Entity) -> ConflictResolution:
        """Resolve by choosing the most recently modified version"""
        local_time = local.updated_at or local.created_at or datetime.min.replace(tzinfo=timezone.utc)
        remote_time = remote.updated_at or remote.created_at or datetime.min.replace(tzinfo=timezone.utc)
        
        if local_time >= remote_time:
            winner = local
        else:
            winner = remote
            
        return ConflictResolution(
            strategy=ConflictStrategy.LAST_WRITE_WINS,
            resolved_entity=winner
        )
    
    def _merge_entities(self, local: Entity, remote: Entity) -> ConflictResolution:
        """Intelligent content merging
        
        Attempts to merge non-conflicting changes. If conflicts exist,
        they are tracked for potential manual resolution.
        """
        # If versions are the same, no conflict
        if local.version == remote.version:
            return ConflictResolution(
                strategy=ConflictStrategy.MERGE,
                resolved_entity=local
            )
        
        # Start with local as base
        merged_content = {}
        merge_conflicts = []
        
        local_content = local.content or {}
        remote_content = remote.content or {}
        
        # Get all keys from both versions
        all_keys = set(local_content.keys()) | set(remote_content.keys())
        
        for key in all_keys:
            local_value = local_content.get(key)
            remote_value = remote_content.get(key)
            
            if local_value == remote_value:
                # No conflict, use the common value
                if local_value is not None:
                    merged_content[key] = local_value
            elif local_value is None:
                # Key only exists in remote
                merged_content[key] = remote_value
            elif remote_value is None:
                # Key only exists in local
                merged_content[key] = local_value
            else:
                # Conflict: different values for same key
                # Try to merge if both are dicts
                if isinstance(local_value, dict) and isinstance(remote_value, dict):
                    merged_value, sub_conflicts = self._merge_dicts(local_value, remote_value)
                    merged_content[key] = merged_value
                    if sub_conflicts:
                        merge_conflicts.append({
                            "key": key,
                            "type": "nested_conflicts",
                            "conflicts": sub_conflicts
                        })
                else:
                    # Can't auto-merge, record conflict and use local value
                    merged_content[key] = local_value
                    merge_conflicts.append({
                        "key": key,
                        "local_value": local_value,
                        "remote_value": remote_value,
                        "resolution": "used_local"
                    })
        
        # Create merged entity with both as parents
        merged_entity = Entity(
            id=local.id,
            version=Entity.create_version("sync-merge"),
            entity_type=local.entity_type,
            name=local.name if (local.updated_at or local.created_at or datetime.min.replace(tzinfo=timezone.utc)) >= (remote.updated_at or remote.created_at or datetime.min.replace(tzinfo=timezone.utc)) else remote.name,
            content=merged_content,
            source_type=local.source_type,
            user_id="sync-merge",
            parent_versions=[local.version, remote.version]
        )
        
        return ConflictResolution(
            strategy=ConflictStrategy.MERGE,
            resolved_entity=merged_entity,
            merge_conflicts=merge_conflicts if merge_conflicts else None
        )
    
    def _merge_dicts(self, dict1: Dict, dict2: Dict) -> tuple[Dict, List[Dict]]:
        """Recursively merge two dictionaries"""
        merged = {}
        conflicts = []
        
        all_keys = set(dict1.keys()) | set(dict2.keys())
        
        for key in all_keys:
            val1 = dict1.get(key)
            val2 = dict2.get(key)
            
            if val1 == val2:
                if val1 is not None:
                    merged[key] = val1
            elif val1 is None:
                merged[key] = val2
            elif val2 is None:
                merged[key] = val1
            elif isinstance(val1, dict) and isinstance(val2, dict):
                sub_merged, sub_conflicts = self._merge_dicts(val1, val2)
                merged[key] = sub_merged
                if sub_conflicts:
                    conflicts.extend([{**c, "path": f"{key}.{c.get('path', c.get('key', ''))}"} 
                                    for c in sub_conflicts])
            else:
                # Conflict - default to val1
                merged[key] = val1
                conflicts.append({
                    "key": key,
                    "value1": val1,
                    "value2": val2
                })
        
        return merged, conflicts
    
    def _queue_for_manual_resolution(self, local: Entity, remote: Entity) -> ConflictResolution:
        """Queue conflict for manual resolution"""
        conflict_id = f"{local.id}-{local.version}-{remote.version}"
        
        self.pending_manual_resolutions.append({
            "id": conflict_id,
            "entity_id": local.id,
            "local": {
                "version": local.version,
                "name": local.name,
                "content": local.content,
                "updated_at": local.updated_at.isoformat() if local.updated_at else None
            },
            "remote": {
                "version": remote.version,
                "name": remote.name,
                "content": remote.content,
                "updated_at": remote.updated_at.isoformat() if remote.updated_at else None
            },
            "queued_at": datetime.now(timezone.utc).isoformat()
        })
        
        return ConflictResolution(
            strategy=ConflictStrategy.MANUAL,
            resolved_entity=None,
            requires_manual=True
        )
    
    def _apply_custom_rules(self, local: Entity, remote: Entity) -> ConflictResolution:
        """Apply custom rules based on entity type"""
        entity_type = local.entity_type.value if hasattr(local.entity_type, 'value') else str(local.entity_type)
        
        if entity_type in self.custom_rules:
            rule_func = self.custom_rules[entity_type]
            try:
                resolved_entity = rule_func(local, remote)
                return ConflictResolution(
                    strategy=ConflictStrategy.CUSTOM,
                    resolved_entity=resolved_entity
                )
            except Exception as e:
                # If custom rule fails, fall back to last-write-wins
                print(f"Custom rule failed for {entity_type}: {e}")
                return self._last_write_wins(local, remote)
        else:
            # No custom rule, fall back to merge
            return self._merge_entities(local, remote)
    
    def get_pending_resolutions(self) -> List[Dict]:
        """Get all conflicts pending manual resolution"""
        return self.pending_manual_resolutions.copy()
    
    def resolve_manual_conflict(self, conflict_id: str, resolution: Dict) -> bool:
        """Resolve a manual conflict with user input"""
        # Find and remove the conflict
        conflict_idx = None
        for idx, conflict in enumerate(self.pending_manual_resolutions):
            if conflict["id"] == conflict_id:
                conflict_idx = idx
                break
        
        if conflict_idx is not None:
            self.pending_manual_resolutions.pop(conflict_idx)
            return True
        
        return False
    
    def clear_pending_resolutions(self):
        """Clear all pending manual resolutions"""
        self.pending_manual_resolutions.clear()


# Example custom rules for specific entity types
def device_conflict_rule(local: Entity, remote: Entity) -> Entity:
    """Custom rule for device conflicts - preserve capabilities"""
    local_caps = set(local.content.get("capabilities", []))
    remote_caps = set(remote.content.get("capabilities", []))
    
    # Union of capabilities
    merged_caps = list(local_caps | remote_caps)
    
    # Use most recent base content
    if local.updated_at >= remote.updated_at:
        base = local
    else:
        base = remote
    
    # Create merged entity
    merged_content = base.content.copy()
    merged_content["capabilities"] = sorted(merged_caps)
    
    return Entity(
        id=base.id,
        version=Entity.create_version("device-merge"),
        entity_type=base.entity_type,
        name=base.name,
        content=merged_content,
        source_type=base.source_type,
        user_id="device-merge",
        parent_versions=[local.version, remote.version]
    )


def automation_conflict_rule(local: Entity, remote: Entity) -> Entity:
    """Custom rule for automation conflicts - prefer enabled state"""
    # If one is enabled and other isn't, keep enabled version
    local_enabled = local.content.get("enabled", False)
    remote_enabled = remote.content.get("enabled", False)
    
    if local_enabled and not remote_enabled:
        return local
    elif remote_enabled and not local_enabled:
        return remote
    else:
        # Both same state, use last write wins
        if local.updated_at and remote.updated_at and local.updated_at >= remote.updated_at:
            return local
        else:
            return remote