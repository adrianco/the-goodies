"""
Sync Metadata API endpoints.
"""

from typing import List, Optional
from datetime import datetime, UTC, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...database import get_db
from ...models import SyncMetadata

router = APIRouter()


@router.post("/", response_model=dict)
async def create_sync_metadata(
    client_id: str,
    server_url: str,
    auth_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Create or update sync metadata for a client."""
    # Check if metadata already exists for this client
    result = await db.execute(
        select(SyncMetadata).where(SyncMetadata.client_id == client_id)
    )
    metadata = result.scalar_one_or_none()
    
    if metadata:
        # Update existing
        metadata.server_url = server_url
        metadata.auth_token = auth_token
        metadata.updated_at = datetime.now(UTC)
    else:
        # Create new
        metadata = SyncMetadata(
            client_id=client_id,
            server_url=server_url,
            auth_token=auth_token
        )
        db.add(metadata)
    
    await db.commit()
    return metadata.to_dict()


@router.get("/{client_id}", response_model=dict)
async def get_sync_metadata(
    client_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get sync metadata for a client."""
    result = await db.execute(
        select(SyncMetadata).where(SyncMetadata.client_id == client_id)
    )
    metadata = result.scalar_one_or_none()
    
    if not metadata:
        raise HTTPException(status_code=404, detail="Sync metadata not found")
    
    return metadata.to_dict()


@router.get("/", response_model=List[dict])
async def list_sync_metadata(
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """List all sync metadata entries."""
    result = await db.execute(
        select(SyncMetadata).limit(limit)
    )
    metadata_list = result.scalars().all()
    return [metadata.to_dict() for metadata in metadata_list]


@router.post("/{client_id}/sync-start")
async def record_sync_start(
    client_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Record that a sync has started for a client."""
    result = await db.execute(
        select(SyncMetadata).where(SyncMetadata.client_id == client_id)
    )
    metadata = result.scalar_one_or_none()
    
    if not metadata:
        raise HTTPException(status_code=404, detail="Sync metadata not found")
    
    metadata.record_sync_start()
    await db.commit()
    
    return {"status": "sync_started", "client_id": client_id}


@router.post("/{client_id}/sync-success")
async def record_sync_success(
    client_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Record successful sync completion for a client."""
    result = await db.execute(
        select(SyncMetadata).where(SyncMetadata.client_id == client_id)
    )
    metadata = result.scalar_one_or_none()
    
    if not metadata:
        raise HTTPException(status_code=404, detail="Sync metadata not found")
    
    metadata.record_sync_success()
    await db.commit()
    
    return {"status": "sync_success", "client_id": client_id}


@router.post("/{client_id}/sync-failure")
async def record_sync_failure(
    client_id: str,
    error: str,
    next_retry: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Record sync failure for a client."""
    result = await db.execute(
        select(SyncMetadata).where(SyncMetadata.client_id == client_id)
    )
    metadata = result.scalar_one_or_none()
    
    if not metadata:
        raise HTTPException(status_code=404, detail="Sync metadata not found")
    
    if next_retry:
        next_retry_time = datetime.fromisoformat(next_retry.replace('Z', '+00:00'))
    else:
        # Default retry in 30 seconds with exponential backoff
        import math
        backoff_seconds = 30 * (2 ** min(metadata.sync_failures, 6))  # Cap at 30 * 2^6 = 1920 seconds
        next_retry_time = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(seconds=backoff_seconds)
    
    metadata.record_sync_failure(error, next_retry_time)
    await db.commit()
    
    return {
        "status": "sync_failure",
        "client_id": client_id,
        "next_retry": next_retry_time.isoformat()
    }


@router.get("/{client_id}/status", response_model=dict)
async def get_sync_status(
    client_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get current sync status for a client."""
    result = await db.execute(
        select(SyncMetadata).where(SyncMetadata.client_id == client_id)
    )
    metadata = result.scalar_one_or_none()
    
    if not metadata:
        return {
            "client_id": client_id,
            "last_sync": None,
            "last_success": None,
            "sync_failures": 0,
            "total_syncs": 0,
            "total_conflicts": 0,
            "sync_in_progress": False,
            "last_error": None
        }
    
    return {
        "client_id": client_id,
        "last_sync": metadata.last_sync_time.isoformat() if metadata.last_sync_time else None,
        "last_success": metadata.last_sync_success.isoformat() if metadata.last_sync_success else None,
        "sync_failures": metadata.sync_failures,
        "total_syncs": metadata.total_syncs,
        "total_conflicts": metadata.total_conflicts,
        "sync_in_progress": bool(metadata.sync_in_progress),
        "last_error": metadata.last_sync_error,
        "next_retry": metadata.next_retry_time.isoformat() if metadata.next_retry_time else None
    }


@router.delete("/{client_id}")
async def delete_sync_metadata(
    client_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete sync metadata for a client."""
    result = await db.execute(
        select(SyncMetadata).where(SyncMetadata.client_id == client_id)
    )
    metadata = result.scalar_one_or_none()
    
    if not metadata:
        raise HTTPException(status_code=404, detail="Sync metadata not found")
    
    await db.delete(metadata)
    await db.commit()
    
    return {"status": "deleted", "client_id": client_id}