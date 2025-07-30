"""
Version management for immutable entity versioning.

Handles version creation, history tracking, and version tree operations
for the enhanced Inbetweenies synchronization protocol.
"""

from datetime import datetime, timezone
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from inbetweenies.models import Entity


@dataclass
class VersionNode:
    """Node in a version tree"""
    entity: Entity
    children: List['VersionNode']
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "version": self.entity.version,
            "user_id": self.entity.user_id,
            "created_at": self.entity.created_at.isoformat() if self.entity.created_at else None,
            "parent_versions": self.entity.parent_versions,
            "children": [child.to_dict() for child in self.children]
        }


@dataclass  
class VersionTree:
    """Complete version tree for an entity"""
    entity_id: str
    root_nodes: List[VersionNode]
    all_versions: Dict[str, Entity]
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "entity_id": self.entity_id,
            "total_versions": len(self.all_versions),
            "roots": [node.to_dict() for node in self.root_nodes]
        }
    
    def find_common_ancestor(self, version1: str, version2: str) -> Optional[str]:
        """Find the most recent common ancestor of two versions"""
        ancestors1 = self._get_ancestors(version1)
        ancestors2 = self._get_ancestors(version2)
        
        # Find intersection of ancestor sets
        common = ancestors1 & ancestors2
        if not common:
            return None
            
        # Return the most recent common ancestor
        return max(common, key=lambda v: self.all_versions[v].created_at)
    
    def _get_ancestors(self, version: str) -> Set[str]:
        """Get all ancestors of a version"""
        ancestors = set()
        to_visit = [version]
        
        while to_visit:
            current = to_visit.pop()
            if current in ancestors:
                continue
                
            ancestors.add(current)
            if current in self.all_versions:
                entity = self.all_versions[current]
                to_visit.extend(entity.parent_versions)
                
        return ancestors


class VersionManager:
    """Manage immutable entity versions"""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        
    def create_version(self, entity: Entity, parent_versions: List[str]) -> str:
        """Create new version with parent tracking"""
        timestamp = datetime.now(timezone.utc).isoformat()
        return f"{timestamp}Z-{entity.user_id}"
    
    async def get_version_history(self, entity_id: str) -> List[Entity]:
        """Get complete version history for entity"""
        query = select(Entity).where(Entity.id == entity_id).order_by(Entity.created_at)
        result = await self.db_session.execute(query)
        return list(result.scalars().all())
    
    async def get_specific_version(self, entity_id: str, version: str) -> Optional[Entity]:
        """Get a specific version of an entity"""
        query = select(Entity).where(
            and_(Entity.id == entity_id, Entity.version == version)
        )
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()
    
    def merge_versions(self, versions: List[Entity]) -> Entity:
        """Merge multiple versions into new version
        
        Uses a simple last-write-wins strategy for conflicting fields,
        but preserves all parent versions for history tracking.
        """
        if not versions:
            raise ValueError("Cannot merge empty version list")
            
        if len(versions) == 1:
            return versions[0]
            
        # Sort by created_at to ensure consistent merge order
        sorted_versions = sorted(versions, key=lambda e: e.created_at or datetime.min.replace(tzinfo=timezone.utc))
        
        # Start with the oldest version as base
        base_entity = sorted_versions[0]
        merged_content = base_entity.content.copy() if base_entity.content else {}
        
        # Apply changes from each subsequent version
        for entity in sorted_versions[1:]:
            if entity.content:
                merged_content.update(entity.content)
        
        # Create new entity with merged content
        merged_entity = Entity(
            id=base_entity.id,
            version=self.create_version(base_entity, [v.version for v in versions]),
            entity_type=base_entity.entity_type,
            name=sorted_versions[-1].name,  # Use most recent name
            content=merged_content,
            source_type=base_entity.source_type,
            user_id="system-merge",
            parent_versions=[v.version for v in versions]
        )
        
        return merged_entity
    
    async def calculate_version_tree(self, entity_id: str) -> VersionTree:
        """Build version tree for visualization"""
        # Get all versions
        versions = await self.get_version_history(entity_id)
        if not versions:
            return VersionTree(entity_id=entity_id, root_nodes=[], all_versions={})
        
        # Build lookup maps
        version_map = {v.version: v for v in versions}
        children_map = defaultdict(list)
        
        # Build parent-child relationships
        for version in versions:
            for parent_version in version.parent_versions:
                if parent_version in version_map:
                    children_map[parent_version].append(version.version)
        
        # Find root nodes (versions with no parents in the tree)
        root_versions = [v for v in versions if not any(
            pv in version_map for pv in v.parent_versions
        )]
        
        # Build tree recursively
        def build_node(version: str) -> VersionNode:
            entity = version_map[version]
            children = [build_node(child) for child in children_map.get(version, [])]
            return VersionNode(entity=entity, children=children)
        
        root_nodes = [build_node(v.version) for v in root_versions]
        
        return VersionTree(
            entity_id=entity_id,
            root_nodes=root_nodes,
            all_versions=version_map
        )
    
    async def get_latest_version(self, entity_id: str) -> Optional[Entity]:
        """Get the most recent version of an entity"""
        query = select(Entity).where(Entity.id == entity_id).order_by(Entity.created_at.desc()).limit(1)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()
    
    def calculate_version_diff(self, old_entity: Entity, new_entity: Entity) -> Dict:
        """Calculate differences between two versions"""
        diff = {
            "version_change": {
                "from": old_entity.version,
                "to": new_entity.version
            },
            "content_changes": {},
            "name_changed": old_entity.name != new_entity.name
        }
        
        if diff["name_changed"]:
            diff["name_change"] = {
                "from": old_entity.name,
                "to": new_entity.name
            }
        
        # Calculate content differences
        old_content = old_entity.content or {}
        new_content = new_entity.content or {}
        
        # Find added keys
        added_keys = set(new_content.keys()) - set(old_content.keys())
        for key in added_keys:
            diff["content_changes"][key] = {
                "type": "added",
                "value": new_content[key]
            }
        
        # Find removed keys
        removed_keys = set(old_content.keys()) - set(new_content.keys())
        for key in removed_keys:
            diff["content_changes"][key] = {
                "type": "removed",
                "old_value": old_content[key]
            }
        
        # Find modified keys
        common_keys = set(old_content.keys()) & set(new_content.keys())
        for key in common_keys:
            if old_content[key] != new_content[key]:
                diff["content_changes"][key] = {
                    "type": "modified",
                    "old_value": old_content[key],
                    "new_value": new_content[key]
                }
        
        return diff