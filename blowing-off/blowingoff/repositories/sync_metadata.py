"""Repository for sync metadata."""

from typing import Optional
from sqlalchemy import select
from .base import ClientBaseRepository
from ..models import SyncMetadata


class SyncMetadataRepository(ClientBaseRepository[SyncMetadata]):
    """Repository for sync metadata operations."""
    
    def __init__(self, session):
        super().__init__(SyncMetadata, session)
        
    async def get_by_client(self, client_id: str) -> Optional[SyncMetadata]:
        """Get sync metadata for a client."""
        result = await self.session.execute(
            select(SyncMetadata).where(SyncMetadata.client_id == client_id)
        )
        return result.scalar_one_or_none()
        
    async def get_or_create(self, client_id: str) -> SyncMetadata:
        """Get or create sync metadata."""
        metadata = await self.get_by_client(client_id)
        if not metadata:
            metadata = SyncMetadata(client_id=client_id)
            self.session.add(metadata)
            await self.session.flush()
        return metadata
    
    async def get_metadata(self, client_id: str = "default") -> Optional[SyncMetadata]:
        """Get sync metadata (alias for get_by_client)."""
        return await self.get_by_client(client_id)
    
    async def update_sync_time(self, sync_time, client_id: str = "default"):
        """Update the last sync time."""
        metadata = await self.get_or_create(client_id)
        metadata.last_sync_time = sync_time
        await self.session.commit()