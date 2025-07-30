"""
Entity Model for Knowledge Graph

This module defines the generic Entity model that can represent any node
in the knowledge graph (homes, rooms, devices, procedures, etc.).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Any, Optional
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship

from .base import Base, InbetweeniesTimestampMixin


class EntityType(str, Enum):
    """Types of entities in the knowledge graph"""
    # Core entity types
    HOME = "home"
    ROOM = "room"
    DEVICE = "device"
    ZONE = "zone"
    DOOR = "door"
    WINDOW = "window"
    PROCEDURE = "procedure"
    MANUAL = "manual"
    NOTE = "note"
    SCHEDULE = "schedule"
    AUTOMATION = "automation"


class SourceType(str, Enum):
    """Source of entity data"""
    HOMEKIT = "homekit"
    MATTER = "matter"
    MANUAL = "manual"
    IMPORTED = "imported"
    GENERATED = "generated"


class Entity(Base, InbetweeniesTimestampMixin):
    """
    Generic entity that can represent any node in the knowledge graph.
    
    This model supports:
    - Flexible entity types via EntityType enum
    - JSON content for extensible properties
    - Version tracking with parent versions for immutability
    - Source tracking to know where data originated
    """
    __tablename__ = "entities"
    
    # Primary key is composite of id and version for immutability
    id = Column(String(36), primary_key=True)
    version = Column(String(255), primary_key=True)
    
    # Entity metadata
    entity_type = Column(SQLEnum(EntityType), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    
    # Flexible content storage
    content = Column(JSON, nullable=False, default=dict)
    
    # Tracking
    source_type = Column(SQLEnum(SourceType), nullable=False, default=SourceType.MANUAL)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    # Version tracking for immutability
    parent_versions = Column(JSON, default=list)
    
    # Relationships
    user = relationship("User", back_populates="entities")
    
    # Relationships defined in EntityRelationship model
    outgoing_relationships = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.from_entity_id",
        back_populates="from_entity",
        primaryjoin="and_(Entity.id==EntityRelationship.from_entity_id, "
                   "Entity.version==EntityRelationship.from_entity_version)"
    )
    
    incoming_relationships = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.to_entity_id",
        back_populates="to_entity",
        primaryjoin="and_(Entity.id==EntityRelationship.to_entity_id, "
                   "Entity.version==EntityRelationship.to_entity_version)"
    )
    
    def __repr__(self):
        return f"<Entity(id={self.id}, type={self.entity_type.value if self.entity_type else None}, name={self.name}, version={self.version[:8] if self.version else ''})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary for API responses"""
        return {
            "id": self.id,
            "version": self.version,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "content": self.content,
            "source_type": self.source_type.value,
            "user_id": self.user_id,
            "parent_versions": self.parent_versions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def create_version(cls, user_id: str) -> str:
        """Generate a new version string for immutable versioning"""
        timestamp = datetime.now(timezone.utc).isoformat()
        return f"{timestamp}Z-{user_id}"
    
    def create_new_version(self, user_id: str, changes: Dict[str, Any]) -> "Entity":
        """
        Create a new version of this entity with changes.
        
        Args:
            user_id: User making the change
            changes: Dictionary of fields to update
            
        Returns:
            New Entity instance with updated version
        """
        # Create new version data
        new_data = self.to_dict()
        
        # Merge content if provided in changes
        if "content" in changes:
            merged_content = self.content.copy() if self.content else {}
            merged_content.update(changes["content"])
            changes["content"] = merged_content
        
        new_data.update(changes)
        
        # Update version tracking
        new_data["version"] = self.create_version(user_id)
        new_data["parent_versions"] = self.parent_versions + [self.version]
        new_data["user_id"] = user_id
        
        # Remove timestamps as they'll be set automatically
        new_data.pop("created_at", None)
        new_data.pop("updated_at", None)
        
        # Convert enum strings back to enums
        new_data["entity_type"] = EntityType(new_data["entity_type"])
        new_data["source_type"] = SourceType(new_data["source_type"])
        
        return Entity(**new_data)