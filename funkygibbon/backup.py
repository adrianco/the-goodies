"""
FunkyGibbon - Backup and Restore Service

DEVELOPMENT CONTEXT:
Created to provide comprehensive backup and restore functionality for the
FunkyGibbon server, ensuring all data including BLOBs (images, PDFs) stored
in SQLite are properly backed up and can be reliably restored.

FUNCTIONALITY:
- Creates full database backups with metadata tracking
- Validates backup integrity using SHA-256 checksums
- Lists available backups with size and timestamp information
- Restores database from backup with validation
- Manages backup lifecycle (creation, deletion, cleanup)
- Includes BLOB data in backups automatically via SQLite export

PURPOSE:
Ensures data safety and disaster recovery capabilities for FunkyGibbon
deployments, with special attention to preserving binary data (BLOBs)
that are stored within the SQLite database.

DESIGN DECISIONS:
- Uses SQLite VACUUM INTO for atomic backup creation
- Stores backups in ./backups/ directory by default
- Backup metadata stored in JSON alongside each backup file
- Checksums validate data integrity before restore
- Restore requires server restart to prevent database corruption

KNOWN LIMITATIONS:
- Backups are local only (no cloud storage integration)
- Restore requires stopping/restarting the server
- No incremental backup support (always full backups)
- No compression (raw SQLite files)

REVISION HISTORY:
- 2026-04-07: Initial implementation with full backup/restore support

DEPENDENCIES:
- pathlib: Path handling for backup files
- hashlib: SHA-256 checksums for integrity validation
- json: Metadata serialization
- shutil: File copy operations for restore
- sqlalchemy: Database connection management

USAGE:
```python
# Create a backup
backup_service = BackupService()
backup_id = await backup_service.create_backup()

# List backups
backups = await backup_service.list_backups()

# Restore from backup
await backup_service.restore_backup(backup_id)
```
"""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .database import engine, get_db_context
from .config import settings


class BackupService:
    """
    Service for creating and managing database backups.

    This service handles full SQLite database backups including all BLOBs
    stored in the database. Backups are stored locally with metadata and
    integrity checksums.
    """

    def __init__(self, backup_dir: Optional[Path] = None, db_path: Optional[Path] = None):
        """
        Initialize backup service.

        Args:
            backup_dir: Directory to store backups (defaults to ./backups)
            db_path: Path to database file (defaults to parsing from settings.database_url)
        """
        self.backup_dir = backup_dir or Path("./backups")
        self.backup_dir.mkdir(exist_ok=True, parents=True)

        # Extract database file path from connection string or use provided path
        if db_path:
            self.db_path = db_path
        else:
            # Format: sqlite+aiosqlite:///./funkygibbon.db
            db_url = settings.database_url
            if ":///" in db_url:
                db_file = db_url.split("///")[1]
                self.db_path = Path(db_file) if db_file else Path("./funkygibbon.db")
            else:
                # Default fallback
                self.db_path = Path("./funkygibbon.db")

    async def create_backup(self, description: Optional[str] = None) -> str:
        """
        Create a full database backup including all BLOBs.

        Uses SQLite VACUUM INTO for atomic backup creation. This ensures
        all data including BLOBs stored in LargeBinary columns are included.

        Args:
            description: Optional description for the backup

        Returns:
            Backup ID (timestamp-based identifier)

        Raises:
            RuntimeError: If backup creation fails
        """
        # Generate backup ID from timestamp
        backup_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"funkygibbon_backup_{backup_id}.db"

        try:
            # Use VACUUM INTO for atomic backup (SQLite 3.27.0+)
            # This creates a complete copy including all BLOBs
            async with get_db_context() as session:
                await session.execute(text(f"VACUUM INTO '{backup_file}'"))
                await session.commit()

            # Calculate checksum for integrity validation
            checksum = self._calculate_file_checksum(backup_file)

            # Create metadata file
            metadata = {
                "backup_id": backup_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "description": description or "Full database backup",
                "database_path": str(self.db_path),
                "backup_file": str(backup_file.name),
                "size_bytes": backup_file.stat().st_size,
                "checksum": checksum,
                "version": "1.0"
            }

            metadata_file = self.backup_dir / f"funkygibbon_backup_{backup_id}.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            return backup_id

        except Exception as e:
            # Clean up partial backup if it exists
            if backup_file.exists():
                backup_file.unlink()
            raise RuntimeError(f"Backup creation failed: {str(e)}")

    async def list_backups(self) -> List[Dict[str, Any]]:
        """
        List all available backups with metadata.

        Returns:
            List of backup metadata dictionaries
        """
        backups = []

        for metadata_file in sorted(self.backup_dir.glob("*.json"), reverse=True):
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                # Verify backup file still exists
                backup_file = self.backup_dir / metadata["backup_file"]
                if backup_file.exists():
                    # Add current file size (may differ if corruption occurred)
                    metadata["current_size_bytes"] = backup_file.stat().st_size
                    metadata["integrity_ok"] = (
                        metadata["current_size_bytes"] == metadata["size_bytes"]
                    )
                    backups.append(metadata)
                else:
                    metadata["integrity_ok"] = False
                    metadata["error"] = "Backup file missing"
                    backups.append(metadata)

            except Exception as e:
                # Include corrupted metadata in listing with error
                backups.append({
                    "backup_id": metadata_file.stem.replace("funkygibbon_backup_", ""),
                    "error": f"Failed to read metadata: {str(e)}",
                    "integrity_ok": False
                })

        return backups

    async def get_backup_info(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific backup.

        Args:
            backup_id: Backup identifier

        Returns:
            Backup metadata dictionary or None if not found
        """
        metadata_file = self.backup_dir / f"funkygibbon_backup_{backup_id}.json"

        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            # Verify backup file exists and validate checksum
            backup_file = self.backup_dir / metadata["backup_file"]
            if backup_file.exists():
                current_checksum = self._calculate_file_checksum(backup_file)
                metadata["current_checksum"] = current_checksum
                metadata["integrity_ok"] = (current_checksum == metadata["checksum"])
            else:
                metadata["integrity_ok"] = False
                metadata["error"] = "Backup file missing"

            return metadata

        except Exception as e:
            return {
                "backup_id": backup_id,
                "error": f"Failed to read metadata: {str(e)}",
                "integrity_ok": False
            }

    async def restore_backup(self, backup_id: str, verify_checksum: bool = True) -> None:
        """
        Restore database from backup.

        WARNING: This operation requires the server to be stopped before
        restoration and restarted after. The database file will be replaced.

        Args:
            backup_id: Backup identifier to restore from
            verify_checksum: Whether to verify backup integrity before restore

        Raises:
            ValueError: If backup not found or integrity check fails
            RuntimeError: If restore operation fails
        """
        metadata = await self.get_backup_info(backup_id)

        if metadata is None:
            raise ValueError(f"Backup {backup_id} not found")

        if "error" in metadata:
            raise ValueError(f"Cannot restore: {metadata['error']}")

        backup_file = self.backup_dir / metadata["backup_file"]

        # Verify integrity if requested
        if verify_checksum:
            if not metadata.get("integrity_ok", False):
                raise ValueError("Backup integrity check failed - checksum mismatch")

        try:
            # Create a safety backup of current database before restore
            safety_backup = self.db_path.parent / f"{self.db_path.name}.pre_restore"
            if self.db_path.exists():
                shutil.copy2(self.db_path, safety_backup)

            # Restore by copying backup over current database
            # NOTE: This requires no active connections to the database
            shutil.copy2(backup_file, self.db_path)

            # Clean up safety backup on success
            if safety_backup.exists():
                safety_backup.unlink()

        except Exception as e:
            # Attempt to restore from safety backup if restore failed
            if safety_backup.exists():
                try:
                    shutil.copy2(safety_backup, self.db_path)
                except:
                    pass  # Can't do much if safety restore fails

            raise RuntimeError(f"Restore failed: {str(e)}")

    async def delete_backup(self, backup_id: str) -> None:
        """
        Delete a backup and its metadata.

        Args:
            backup_id: Backup identifier to delete

        Raises:
            ValueError: If backup not found
        """
        metadata_file = self.backup_dir / f"funkygibbon_backup_{backup_id}.json"
        backup_file = self.backup_dir / f"funkygibbon_backup_{backup_id}.db"

        if not metadata_file.exists():
            raise ValueError(f"Backup {backup_id} not found")

        # Read metadata to get exact backup filename
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            backup_file = self.backup_dir / metadata["backup_file"]
        except:
            pass  # Use default filename if metadata can't be read

        # Delete files
        if backup_file.exists():
            backup_file.unlink()
        if metadata_file.exists():
            metadata_file.unlink()

    def _calculate_file_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA-256 checksum of a file.

        Args:
            file_path: Path to file

        Returns:
            Hexadecimal checksum string
        """
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()
