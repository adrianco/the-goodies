"""
Delta synchronization engine for efficient data transfer.

Implements merkle trees and delta calculation for minimizing
sync bandwidth usage.
"""

from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from inbetweenies.models import Entity, EntityRelationship, EntityType


@dataclass
class SyncDelta:
    """Changes since last sync"""
    added_entities: List[Entity]
    modified_entities: List[Entity]
    deleted_entity_ids: List[str]
    added_relationships: List[EntityRelationship]
    deleted_relationship_ids: List[str]
    from_timestamp: datetime
    to_timestamp: datetime
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "added_entities": len(self.added_entities),
            "modified_entities": len(self.modified_entities),
            "deleted_entities": len(self.deleted_entity_ids),
            "added_relationships": len(self.added_relationships),
            "deleted_relationships": len(self.deleted_relationship_ids),
            "from_timestamp": self.from_timestamp.isoformat(),
            "to_timestamp": self.to_timestamp.isoformat()
        }


@dataclass
class SyncResult:
    """Result of applying sync delta"""
    entities_created: int
    entities_updated: int
    entities_deleted: int
    relationships_created: int
    relationships_deleted: int
    conflicts: List[Dict]
    duration_ms: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "entities_created": self.entities_created,
            "entities_updated": self.entities_updated,
            "entities_deleted": self.entities_deleted,
            "relationships_created": self.relationships_created,
            "relationships_deleted": self.relationships_deleted,
            "conflicts": self.conflicts,
            "duration_ms": self.duration_ms
        }


class MerkleNode:
    """Node in a Merkle tree for efficient comparison"""
    
    def __init__(self, entity_id: str = None, entity_version: str = None):
        self.entity_id = entity_id
        self.entity_version = entity_version
        self.children: Dict[str, 'MerkleNode'] = {}
        self._hash: Optional[str] = None
    
    def add_entity(self, entity: Entity):
        """Add an entity to the tree"""
        # Use first 2 chars of ID for tree branching
        if len(entity.id) >= 2:
            prefix = entity.id[:2]
            if prefix not in self.children:
                self.children[prefix] = MerkleNode()
            self.children[prefix].entity_id = entity.id
            self.children[prefix].entity_version = entity.version
            self._hash = None  # Invalidate hash
    
    def calculate_hash(self) -> str:
        """Calculate hash of this node and its children"""
        if self._hash is not None:
            return self._hash
            
        hasher = hashlib.sha256()
        
        # Hash own data
        if self.entity_id:
            hasher.update(self.entity_id.encode())
        if self.entity_version:
            hasher.update(self.entity_version.encode())
        
        # Hash children in sorted order
        for key in sorted(self.children.keys()):
            hasher.update(key.encode())
            hasher.update(self.children[key].calculate_hash().encode())
        
        self._hash = hasher.hexdigest()
        return self._hash
    
    def find_differences(self, other: 'MerkleNode') -> Set[str]:
        """Find entity IDs that differ between trees"""
        differences = set()
        
        # If hashes match, subtrees are identical
        if self.calculate_hash() == other.calculate_hash():
            return differences
        
        # Check own entity
        if self.entity_id and (
            self.entity_id != other.entity_id or 
            self.entity_version != other.entity_version
        ):
            differences.add(self.entity_id)
        
        # Check all keys
        all_keys = set(self.children.keys()) | set(other.children.keys())
        
        for key in all_keys:
            if key in self.children and key in other.children:
                # Both have this branch, recurse
                differences.update(
                    self.children[key].find_differences(other.children[key])
                )
            elif key in self.children:
                # Only we have this branch, all entities are different
                differences.update(self._collect_all_entities(self.children[key]))
            else:
                # Only other has this branch, all entities are different  
                differences.update(self._collect_all_entities(other.children[key]))
        
        return differences
    
    def _collect_all_entities(self, node: 'MerkleNode') -> Set[str]:
        """Collect all entity IDs in a subtree"""
        entities = set()
        if node.entity_id:
            entities.add(node.entity_id)
        for child in node.children.values():
            entities.update(self._collect_all_entities(child))
        return entities


class DeltaSyncEngine:
    """Efficient delta synchronization"""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self._last_sync_times: Dict[str, datetime] = {}
    
    async def calculate_delta(self, last_sync: datetime, 
                            entity_types: List[EntityType] = None) -> SyncDelta:
        """Calculate changes since last sync"""
        current_time = datetime.now(timezone.utc)
        
        # Query for entities changed since last sync
        # Ensure last_sync is timezone-aware
        if last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=timezone.utc)
            
        entity_query = select(Entity).where(
            or_(
                Entity.created_at >= last_sync,
                Entity.updated_at >= last_sync
            )
        )
        
        if entity_types:
            entity_query = entity_query.where(Entity.entity_type.in_(entity_types))
        
        result = await self.db_session.execute(entity_query)
        changed_entities = list(result.scalars().all())
        
        # Separate into added and modified
        added_entities = []
        modified_entities = []
        
        for entity in changed_entities:
            # Handle timezone-aware comparison
            entity_created_at = entity.created_at
            if entity_created_at.tzinfo is None:
                entity_created_at = entity_created_at.replace(tzinfo=timezone.utc)
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
                
            if entity_created_at >= last_sync:
                added_entities.append(entity)
            else:
                modified_entities.append(entity)
        
        # Query for relationships changed since last sync
        rel_query = select(EntityRelationship).where(
            EntityRelationship.created_at >= last_sync
        )
        
        rel_result = await self.db_session.execute(rel_query)
        added_relationships = list(rel_result.scalars().all())
        
        # Note: This implementation doesn't track deletions
        # In a real system, you'd need a separate deletion log
        
        return SyncDelta(
            added_entities=added_entities,
            modified_entities=modified_entities,
            deleted_entity_ids=[],  # Would need deletion tracking
            added_relationships=added_relationships,
            deleted_relationship_ids=[],  # Would need deletion tracking
            from_timestamp=last_sync,
            to_timestamp=current_time
        )
    
    async def apply_delta(self, delta: SyncDelta) -> SyncResult:
        """Apply delta changes to local state"""
        start_time = datetime.now(timezone.utc)
        conflicts = []
        
        entities_created = 0
        entities_updated = 0
        entities_deleted = 0
        relationships_created = 0
        relationships_deleted = 0
        
        # Apply entity additions
        for entity in delta.added_entities:
            # Check if entity already exists (conflict)
            existing = await self.db_session.get(Entity, entity.id)
            if existing:
                conflicts.append({
                    "type": "entity_exists",
                    "entity_id": entity.id,
                    "local_version": existing.version,
                    "remote_version": entity.version
                })
            else:
                self.db_session.add(entity)
                entities_created += 1
        
        # Apply entity modifications
        for entity in delta.modified_entities:
            existing = await self.db_session.get(Entity, entity.id)
            if existing:
                if existing.version != entity.version:
                    # Version conflict
                    conflicts.append({
                        "type": "version_conflict",
                        "entity_id": entity.id,
                        "local_version": existing.version,
                        "remote_version": entity.version
                    })
                else:
                    # Update entity
                    existing.name = entity.name
                    existing.content = entity.content
                    existing.updated_at = entity.updated_at
                    entities_updated += 1
            else:
                # Entity doesn't exist, add it
                self.db_session.add(entity)
                entities_created += 1
        
        # Apply entity deletions
        for entity_id in delta.deleted_entity_ids:
            entity = await self.db_session.get(Entity, entity_id)
            if entity:
                await self.db_session.delete(entity)
                entities_deleted += 1
        
        # Apply relationship additions
        for rel in delta.added_relationships:
            # Check if relationship already exists
            existing_query = select(EntityRelationship).where(
                and_(
                    EntityRelationship.from_entity_id == rel.from_entity_id,
                    EntityRelationship.to_entity_id == rel.to_entity_id,
                    EntityRelationship.relationship_type == rel.relationship_type
                )
            )
            existing_result = await self.db_session.execute(existing_query)
            existing = existing_result.scalar_one_or_none()
            
            if not existing:
                self.db_session.add(rel)
                relationships_created += 1
        
        # Apply relationship deletions
        for rel_id in delta.deleted_relationship_ids:
            rel = await self.db_session.get(EntityRelationship, rel_id)
            if rel:
                await self.db_session.delete(rel)
                relationships_deleted += 1
        
        # Commit changes
        await self.db_session.commit()
        
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        return SyncResult(
            entities_created=entities_created,
            entities_updated=entities_updated,
            entities_deleted=entities_deleted,
            relationships_created=relationships_created,
            relationships_deleted=relationships_deleted,
            conflicts=conflicts,
            duration_ms=duration_ms
        )
    
    async def create_merkle_tree(self, entities: List[Entity]) -> MerkleNode:
        """Create merkle tree for efficient comparison"""
        root = MerkleNode()
        
        for entity in entities:
            root.add_entity(entity)
        
        return root
    
    def compute_sync_checksum(self, entities: List[Entity]) -> str:
        """Compute overall state checksum"""
        hasher = hashlib.sha256()
        
        # Sort entities for consistent hashing
        sorted_entities = sorted(entities, key=lambda e: e.id)
        
        for entity in sorted_entities:
            hasher.update(entity.id.encode())
            hasher.update(entity.version.encode())
            hasher.update(str(entity.entity_type).encode())
            hasher.update(entity.name.encode())
            if entity.content:
                hasher.update(json.dumps(entity.content, sort_keys=True).encode())
        
        return hasher.hexdigest()
    
    async def find_missing_entities(self, local_ids: Set[str], 
                                  remote_ids: Set[str]) -> Tuple[Set[str], Set[str]]:
        """Find entities missing on each side"""
        missing_locally = remote_ids - local_ids
        missing_remotely = local_ids - remote_ids
        
        return missing_locally, missing_remotely
    
    def update_last_sync_time(self, device_id: str, timestamp: datetime):
        """Update last sync time for a device"""
        self._last_sync_times[device_id] = timestamp
    
    def get_last_sync_time(self, device_id: str) -> Optional[datetime]:
        """Get last sync time for a device"""
        return self._last_sync_times.get(device_id)
    
    async def calculate_sync_size(self, delta: SyncDelta) -> Dict[str, int]:
        """Calculate approximate size of sync data"""
        size_info = {
            "entity_count": len(delta.added_entities) + len(delta.modified_entities),
            "relationship_count": len(delta.added_relationships),
            "estimated_bytes": 0
        }
        
        # Estimate entity sizes
        for entity in delta.added_entities + delta.modified_entities:
            # Basic entity overhead
            size = 200  # ID, version, type, timestamps
            size += len(entity.name)
            if entity.content:
                size += len(json.dumps(entity.content))
            size_info["estimated_bytes"] += size
        
        # Estimate relationship sizes
        for rel in delta.added_relationships:
            size = 150  # IDs, type, timestamps
            if rel.properties:
                size += len(json.dumps(rel.properties))
            size_info["estimated_bytes"] += size
        
        return size_info