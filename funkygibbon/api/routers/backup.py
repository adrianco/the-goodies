"""
Backup and Restore API endpoints.

Provides endpoints for creating, listing, and restoring database backups.
All endpoints require admin authentication.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from ...backup import BackupService
from ...auth import TokenManager, require_admin

import os


# Initialize router
router = APIRouter(prefix="/backup", tags=["backup"])
security = HTTPBearer()

# Initialize backup service
backup_service = BackupService()

# Initialize token manager for authentication
token_manager = TokenManager(secret_key=os.getenv("JWT_SECRET", "development-secret-key"))


# Request/Response models
class CreateBackupRequest(BaseModel):
    """Request to create a new backup."""
    description: Optional[str] = Field(None, description="Optional description for the backup")


class BackupInfo(BaseModel):
    """Backup metadata information."""
    backup_id: str
    created_at: str
    description: str
    size_bytes: int
    checksum: str
    integrity_ok: bool
    error: Optional[str] = None


class CreateBackupResponse(BaseModel):
    """Response after creating a backup."""
    backup_id: str
    message: str
    size_bytes: int


class RestoreBackupRequest(BaseModel):
    """Request to restore from a backup."""
    verify_checksum: bool = Field(True, description="Whether to verify backup integrity before restore")


class RestoreBackupResponse(BaseModel):
    """Response after restoring a backup."""
    message: str
    backup_id: str
    warning: Optional[str] = None


# Helper function to verify admin token
async def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Verify the bearer token is valid and belongs to an admin."""
    token = credentials.credentials

    try:
        # Verify token
        payload = token_manager.verify_token(token)

        # Check if admin role
        if payload.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )

        return payload

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.post("/create", response_model=CreateBackupResponse, status_code=status.HTTP_201_CREATED)
async def create_backup(
    request: CreateBackupRequest,
    token_data: Dict = Depends(verify_admin_token)
):
    """
    Create a full database backup including all BLOBs.

    This endpoint creates a complete backup of the FunkyGibbon database,
    including all binary data (images, PDFs, etc.) stored in BLOB fields.

    **Authentication:** Requires admin token

    **Returns:**
    - backup_id: Unique identifier for the backup
    - message: Success message
    - size_bytes: Size of the backup file
    """
    try:
        backup_id = await backup_service.create_backup(description=request.description)

        # Get backup info to return size
        backup_info = await backup_service.get_backup_info(backup_id)

        return CreateBackupResponse(
            backup_id=backup_id,
            message="Backup created successfully",
            size_bytes=backup_info["size_bytes"]
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create backup: {str(e)}"
        )


@router.get("/list", response_model=List[BackupInfo])
async def list_backups(
    token_data: Dict = Depends(verify_admin_token)
):
    """
    List all available backups.

    Returns a list of all backups with their metadata, including size,
    creation time, and integrity status.

    **Authentication:** Requires admin token

    **Returns:**
    List of backup metadata objects
    """
    try:
        backups = await backup_service.list_backups()
        return [BackupInfo(**backup) for backup in backups]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list backups: {str(e)}"
        )


@router.get("/{backup_id}", response_model=BackupInfo)
async def get_backup_info(
    backup_id: str,
    token_data: Dict = Depends(verify_admin_token)
):
    """
    Get detailed information about a specific backup.

    Returns metadata for the specified backup including size, checksum,
    and integrity validation status.

    **Authentication:** Requires admin token

    **Parameters:**
    - backup_id: The unique identifier of the backup

    **Returns:**
    Backup metadata object
    """
    try:
        backup_info = await backup_service.get_backup_info(backup_id)

        if backup_info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backup {backup_id} not found"
            )

        return BackupInfo(**backup_info)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get backup info: {str(e)}"
        )


@router.post("/{backup_id}/restore", response_model=RestoreBackupResponse)
async def restore_backup(
    backup_id: str,
    request: RestoreBackupRequest,
    token_data: Dict = Depends(verify_admin_token)
):
    """
    Restore the database from a backup.

    **⚠️ WARNING:** This operation will replace the current database with
    the backup. The server should be restarted after restoration to ensure
    all connections are properly reset.

    **Authentication:** Requires admin token

    **Parameters:**
    - backup_id: The unique identifier of the backup to restore
    - verify_checksum: Whether to verify backup integrity (default: true)

    **Returns:**
    Success message with restoration details
    """
    try:
        await backup_service.restore_backup(
            backup_id=backup_id,
            verify_checksum=request.verify_checksum
        )

        return RestoreBackupResponse(
            message="Database restored successfully from backup",
            backup_id=backup_id,
            warning="Server restart recommended to ensure proper operation"
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore backup: {str(e)}"
        )


@router.delete("/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    backup_id: str,
    token_data: Dict = Depends(verify_admin_token)
):
    """
    Delete a backup and its metadata.

    **Authentication:** Requires admin token

    **Parameters:**
    - backup_id: The unique identifier of the backup to delete
    """
    try:
        await backup_service.delete_backup(backup_id)
        return None  # 204 No Content response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete backup: {str(e)}"
        )
