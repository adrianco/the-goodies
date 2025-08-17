"""
Binary Large Object (BLOB) Model for storing PDFs, photos, and other binary data

This module defines the Blob model for storing binary files like PDFs, images, etc.
that are associated with entities in the knowledge graph.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional
from sqlalchemy import Column, String, LargeBinary, Integer, DateTime, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship

from .base import Base, InbetweeniesTimestampMixin


class BlobType(str, Enum):
    """Types of binary data stored"""
    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"
    ICON = "icon"
    DOCUMENT = "document"
    DATA = "data"


class BlobStatus(str, Enum):
    """Sync status of the blob"""
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    PENDING_DOWNLOAD = "pending_download"
    DOWNLOADED = "downloaded"
    SYNC_ERROR = "sync_error"


class Blob(Base, InbetweeniesTimestampMixin):
    """
    Stores binary large objects (BLOBs) like PDFs and photos.
    
    This model supports:
    - Binary data storage
    - Metadata about the blob
    - Server sync tracking
    - Checksums for integrity
    """
    __tablename__ = "blobs"
    
    id = Column(String(36), primary_key=True)
    
    # Blob metadata
    name = Column(String(255), nullable=False)
    blob_type = Column(SQLEnum(BlobType), nullable=False, index=True)
    mime_type = Column(String(100), nullable=True)
    size = Column(Integer, nullable=False)  # Size in bytes
    
    # Binary data
    data = Column(LargeBinary, nullable=True)  # Can be null if not yet downloaded
    
    # Content metadata
    blob_metadata = Column(JSON, default=dict)  # Flexible metadata storage
    checksum = Column(String(64), nullable=True)  # SHA256 hash for integrity
    
    # Sync tracking
    sync_status = Column(SQLEnum(BlobStatus), nullable=False, default=BlobStatus.PENDING_UPLOAD)
    server_url = Column(String(500), nullable=True)  # URL on server if synced
    last_sync_at = Column(DateTime, nullable=True)
    
    # User tracking
    user_id = Column(String(36), nullable=True)
    
    # Summary for documents (like PDF manuals)
    summary = Column(String(2000), nullable=True)
    
    def __repr__(self):
        return f"<Blob(id={self.id}, name={self.name}, type={self.blob_type.value if self.blob_type else None}, size={self.size})>"
    
    def to_dict(self, include_data: bool = False) -> Dict[str, Any]:
        """Convert blob to dictionary for API responses"""
        result = {
            "id": self.id,
            "name": self.name,
            "blob_type": self.blob_type.value if hasattr(self.blob_type, 'value') else str(self.blob_type),
            "mime_type": self.mime_type,
            "size": self.size,
            "blob_metadata": self.blob_metadata,
            "checksum": self.checksum,
            "sync_status": self.sync_status.value if hasattr(self.sync_status, 'value') else str(self.sync_status),
            "server_url": self.server_url,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "user_id": self.user_id,
            "summary": self.summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_data and self.data:
            # Convert binary data to base64 for JSON serialization
            import base64
            result["data"] = base64.b64encode(self.data).decode('utf-8')
        
        return result
    
    def set_data(self, data: bytes):
        """Set binary data and update metadata"""
        import hashlib
        
        self.data = data
        self.size = len(data)
        self.checksum = hashlib.sha256(data).hexdigest()
        self.sync_status = BlobStatus.PENDING_UPLOAD
    
    def mark_uploaded(self, server_url: str):
        """Mark blob as successfully uploaded to server"""
        self.server_url = server_url
        self.sync_status = BlobStatus.UPLOADED
        self.last_sync_at = datetime.now(timezone.utc)
    
    def mark_downloaded(self):
        """Mark blob as successfully downloaded from server"""
        self.sync_status = BlobStatus.DOWNLOADED
        self.last_sync_at = datetime.now(timezone.utc)