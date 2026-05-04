"""
Tests for backup and restore functionality.

Covers both the BackupService class and the backup API endpoints,
ensuring that database backups including BLOBs are created and
restored correctly. Also tests the automated backup scheduler.
"""

import pytest
import json
import shutil
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from unittest.mock import patch, MagicMock

from funkygibbon.backup import BackupService
from funkygibbon.backup_scheduler import BackupScheduler
from funkygibbon.database import get_db_context, init_db, engine
from funkygibbon.config import settings


@pytest.fixture
async def test_backup_dir(tmp_path):
    """Create a temporary backup directory for testing."""
    backup_dir = tmp_path / "test_backups"
    backup_dir.mkdir()
    yield backup_dir
    # Cleanup
    if backup_dir.exists():
        shutil.rmtree(backup_dir)


@pytest.fixture
async def backup_service(test_backup_dir):
    """Create a BackupService instance for testing."""
    return BackupService(backup_dir=test_backup_dir)


@pytest.fixture
async def sample_database():
    """Set up a test database with sample data including a BLOB."""
    # Initialize database
    await init_db()

    # Add sample data
    async with get_db_context() as session:
        # Create a simple test table with BLOB data
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS test_data (
                id INTEGER PRIMARY KEY,
                name TEXT,
                data BLOB
            )
        """))

        # Insert test data including binary data
        test_blob = b"This is test binary data for backup testing"
        await session.execute(
            text("INSERT INTO test_data (id, name, data) VALUES (:id, :name, :data)"),
            {"id": 1, "name": "test_record", "data": test_blob}
        )
        await session.commit()

    yield

    # Cleanup
    async with get_db_context() as session:
        await session.execute(text("DROP TABLE IF EXISTS test_data"))
        await session.commit()


class TestBackupService:
    """Tests for the BackupService class."""

    @pytest.mark.asyncio
    async def test_create_backup(self, backup_service, sample_database):
        """Test creating a backup."""
        # Create backup
        backup_id = await backup_service.create_backup(description="Test backup")

        # Verify backup ID format (timestamp-based)
        assert len(backup_id) == 15  # YYYYMMDD_HHMMSS format
        assert "_" in backup_id

        # Verify backup file exists
        backup_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.db"
        assert backup_file.exists()
        assert backup_file.stat().st_size > 0

        # Verify metadata file exists
        metadata_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.json"
        assert metadata_file.exists()

        # Verify metadata content
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        assert metadata["backup_id"] == backup_id
        assert metadata["description"] == "Test backup"
        assert "checksum" in metadata
        assert metadata["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_backup_includes_blob_data(self, backup_service, sample_database):
        """Test that backups include BLOB data."""
        # Create backup
        backup_id = await backup_service.create_backup()

        # Verify backup file exists
        backup_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.db"

        # Query the backup file directly to verify BLOB data is included
        import aiosqlite

        async with aiosqlite.connect(backup_file) as conn:
            cursor = await conn.execute("SELECT data FROM test_data WHERE id = 1")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == b"This is test binary data for backup testing"

    @pytest.mark.asyncio
    async def test_list_backups(self, backup_service, sample_database):
        """Test listing backups."""
        # Create multiple backups
        backup_id1 = await backup_service.create_backup(description="Backup 1")
        backup_id2 = await backup_service.create_backup(description="Backup 2")

        # List backups
        backups = await backup_service.list_backups()

        # Should have at least 2 backups
        assert len(backups) >= 2

        # Verify backup IDs are in list
        backup_ids = [b["backup_id"] for b in backups]
        assert backup_id1 in backup_ids
        assert backup_id2 in backup_ids

        # Verify all backups have integrity_ok flag
        for backup in backups:
            assert "integrity_ok" in backup

    @pytest.mark.asyncio
    async def test_get_backup_info(self, backup_service, sample_database):
        """Test getting backup info."""
        # Create backup
        backup_id = await backup_service.create_backup(description="Info test")

        # Get backup info
        info = await backup_service.get_backup_info(backup_id)

        # Verify info
        assert info is not None
        assert info["backup_id"] == backup_id
        assert info["description"] == "Info test"
        assert info["integrity_ok"] is True
        assert "checksum" in info
        assert "current_checksum" in info
        assert info["checksum"] == info["current_checksum"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_backup_info(self, backup_service):
        """Test getting info for non-existent backup."""
        info = await backup_service.get_backup_info("nonexistent_backup")
        assert info is None

    @pytest.mark.asyncio
    async def test_restore_backup(self, backup_service, sample_database):
        """Test restoring from backup."""
        # Create backup
        backup_id = await backup_service.create_backup()

        # Modify database after backup
        async with get_db_context() as session:
            await session.execute(
                text("INSERT INTO test_data (id, name, data) VALUES (:id, :name, :data)"),
                {"id": 2, "name": "new_record", "data": b"new data"}
            )
            await session.commit()

        # Verify new record exists
        async with get_db_context() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM test_data"))
            count = result.scalar()
            assert count == 2

        # Close all connections before restore
        await engine.dispose()

        # Restore from backup
        await backup_service.restore_backup(backup_id)

        # Re-initialize engine after restore
        from funkygibbon.database import engine as new_engine

        # Verify database is restored (only original record)
        async with get_db_context() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM test_data"))
            count = result.scalar()
            assert count == 1

            result = await session.execute(text("SELECT name FROM test_data WHERE id = 1"))
            name = result.scalar()
            assert name == "test_record"

    @pytest.mark.asyncio
    async def test_restore_with_checksum_verification(self, backup_service, sample_database):
        """Test restore with checksum verification."""
        # Create backup
        backup_id = await backup_service.create_backup()

        # Close connections
        await engine.dispose()

        # Restore with checksum verification
        await backup_service.restore_backup(backup_id, verify_checksum=True)

        # Should succeed without error

    @pytest.mark.asyncio
    async def test_restore_corrupted_backup_fails(self, backup_service, sample_database):
        """Test that restoring a corrupted backup fails."""
        # Create backup
        backup_id = await backup_service.create_backup()

        # Corrupt the backup file
        backup_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.db"
        with open(backup_file, 'ab') as f:
            f.write(b"CORRUPTED DATA")

        # Close connections
        await engine.dispose()

        # Attempt to restore should fail with checksum verification
        with pytest.raises(ValueError, match="integrity check failed"):
            await backup_service.restore_backup(backup_id, verify_checksum=True)

    @pytest.mark.asyncio
    async def test_restore_nonexistent_backup_fails(self, backup_service):
        """Test that restoring non-existent backup fails."""
        with pytest.raises(ValueError, match="not found"):
            await backup_service.restore_backup("nonexistent_backup")

    @pytest.mark.asyncio
    async def test_delete_backup(self, backup_service, sample_database):
        """Test deleting a backup."""
        # Create backup
        backup_id = await backup_service.create_backup()

        # Verify backup exists
        backup_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.db"
        metadata_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.json"
        assert backup_file.exists()
        assert metadata_file.exists()

        # Delete backup
        await backup_service.delete_backup(backup_id)

        # Verify backup files are deleted
        assert not backup_file.exists()
        assert not metadata_file.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_backup_fails(self, backup_service):
        """Test that deleting non-existent backup fails."""
        with pytest.raises(ValueError, match="not found"):
            await backup_service.delete_backup("nonexistent_backup")

    @pytest.mark.asyncio
    async def test_backup_checksum_calculation(self, backup_service, sample_database):
        """Test that checksums are calculated correctly."""
        # Create two identical backups
        backup_id1 = await backup_service.create_backup()

        # Get checksums
        info1 = await backup_service.get_backup_info(backup_id1)

        # Checksums should be consistent
        assert info1["checksum"] == info1["current_checksum"]
        assert len(info1["checksum"]) == 64  # SHA-256 produces 64 hex characters


class TestBackupScheduler:
    """Tests for the BackupScheduler class."""

    @pytest.fixture
    def scheduler_backup_dir(self, tmp_path):
        """Create a temporary backup directory for scheduler testing (non-async)."""
        backup_dir = tmp_path / "scheduler_test_backups"
        backup_dir.mkdir()
        yield backup_dir
        # Cleanup
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

    @pytest.fixture
    def scheduler(self, scheduler_backup_dir):
        """Create a BackupScheduler instance for testing."""
        backup_service = BackupService(backup_dir=scheduler_backup_dir)
        # Create scheduler with short interval for testing
        scheduler = BackupScheduler(
            backup_service=backup_service,
            enabled=True,
            interval_hours=1,
            retention_days=7,
            max_count=5
        )
        yield scheduler
        # Cleanup
        if scheduler.is_running():
            scheduler.stop()

    def test_scheduler_initialization(self, scheduler):
        """Test scheduler is initialized with correct configuration."""
        assert scheduler.enabled is True
        assert scheduler.interval_hours == 1
        assert scheduler.retention_days == 7
        assert scheduler.max_count == 5
        assert scheduler.is_running() is False

    @pytest.mark.asyncio
    async def test_scheduler_start_stop(self, scheduler, sample_database):
        """Test starting and stopping the scheduler."""
        # Start scheduler
        scheduler.start()
        assert scheduler.is_running() is True

        # Stop scheduler
        scheduler.stop()
        assert scheduler.is_running() is False

    def test_scheduler_status(self, scheduler):
        """Test getting scheduler status."""
        status = scheduler.get_status()

        assert "enabled" in status
        assert "running" in status
        assert "interval_hours" in status
        assert "retention_days" in status
        assert "max_count" in status
        assert status["enabled"] is True
        assert status["interval_hours"] == 1

    @pytest.mark.asyncio
    async def test_manual_backup_trigger(self, scheduler, sample_database):
        """Test manually triggering a backup."""
        # Trigger backup
        backup_id = scheduler.trigger_backup_now()

        # Verify backup was created
        assert backup_id is not None
        assert len(backup_id) == 15

        # Verify backup exists
        backup_info = await scheduler.backup_service.get_backup_info(backup_id)
        assert backup_info is not None
        assert backup_info["integrity_ok"] is True

    def test_scheduled_backup_creation(self, scheduler):
        """Test that scheduled backups are created."""
        # Start scheduler
        scheduler.start()

        # Wait a moment for initial backup to complete
        time.sleep(2)

        # Check that at least one backup was created (using sync loop)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        backups = loop.run_until_complete(scheduler.backup_service.list_backups())
        loop.close()

        assert len(backups) >= 1

        # Stop scheduler
        scheduler.stop()

    @pytest.mark.asyncio
    async def test_backup_cleanup_by_age(self, scheduler, sample_database):
        """Test cleanup of old backups based on retention days."""
        # Create multiple backups with different ages
        old_backup_id = await scheduler.backup_service.create_backup(description="Old backup")

        # Modify metadata to make it appear old
        metadata_file = scheduler.backup_service.backup_dir / f"funkygibbon_backup_{old_backup_id}.json"
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        # Set creation date to 8 days ago (beyond 7-day retention)
        old_date = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        metadata["created_at"] = old_date

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Create a recent backup
        recent_backup_id = await scheduler.backup_service.create_backup(description="Recent backup")

        # Run cleanup
        result = scheduler._run_cleanup()

        # Verify old backup was deleted
        old_backup_info = await scheduler.backup_service.get_backup_info(old_backup_id)
        assert old_backup_info is None

        # Verify recent backup still exists
        recent_backup_info = await scheduler.backup_service.get_backup_info(recent_backup_id)
        assert recent_backup_info is not None

        # Verify cleanup stats
        assert result["deleted_count"] >= 1

    @pytest.mark.asyncio
    async def test_backup_cleanup_by_count(self, scheduler, sample_database):
        """Test cleanup when exceeding max backup count."""
        # Create more backups than max_count
        backup_ids = []
        for i in range(7):  # max_count is 5
            backup_id = await scheduler.backup_service.create_backup(
                description=f"Backup {i}"
            )
            backup_ids.append(backup_id)
            time.sleep(0.1)  # Small delay to ensure different timestamps

        # Run cleanup
        result = scheduler._run_cleanup()

        # Should have deleted 2 backups (7 - 5 = 2)
        assert result["deleted_count"] == 2
        assert result["remaining_count"] == 5

        # Verify most recent 5 backups still exist
        remaining_backups = await scheduler.backup_service.list_backups()
        assert len(remaining_backups) == 5

    def test_scheduler_disabled(self, scheduler_backup_dir):
        """Test that disabled scheduler doesn't start."""
        backup_service = BackupService(backup_dir=scheduler_backup_dir)
        scheduler = BackupScheduler(
            backup_service=backup_service,
            enabled=False
        )

        # Try to start
        scheduler.start()

        # Should not be running
        assert scheduler.is_running() is False

    @pytest.mark.asyncio
    async def test_scheduler_idempotent_start(self, scheduler, sample_database):
        """Test that starting an already running scheduler is safe."""
        scheduler.start()
        assert scheduler.is_running() is True

        # Start again
        scheduler.start()
        assert scheduler.is_running() is True

        scheduler.stop()

    def test_scheduler_idempotent_stop(self, scheduler):
        """Test that stopping an already stopped scheduler is safe."""
        # Stop without starting
        scheduler.stop()
        assert scheduler.is_running() is False

        # Stop again
        scheduler.stop()
        assert scheduler.is_running() is False


@pytest.mark.integration
class TestBackupAPI:
    """Integration tests for backup API endpoints."""

    @pytest.fixture
    async def auth_token(self, client):
        """Get an admin auth token for API calls."""
        response = client.post(
            "/api/v1/auth/admin/login",
            json={"password": "admin"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    @pytest.mark.asyncio
    async def test_create_backup_endpoint(self, client, auth_token, sample_database):
        """Test POST /api/v1/backup/create endpoint."""
        response = client.post(
            "/api/v1/backup/create",
            json={"description": "API test backup"},
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 201
        data = response.json()
        assert "backup_id" in data
        assert data["message"] == "Backup created successfully"
        assert data["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_create_backup_without_auth_fails(self, client):
        """Test that creating backup without auth fails."""
        response = client.post(
            "/api/v1/backup/create",
            json={"description": "Test"}
        )

        assert response.status_code == 403  # Forbidden

    @pytest.mark.asyncio
    async def test_list_backups_endpoint(self, client, auth_token, backup_service, sample_database):
        """Test GET /api/v1/backup/list endpoint."""
        # Create a backup first
        await backup_service.create_backup(description="List test")

        response = client.get(
            "/api/v1/backup/list",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_backup_info_endpoint(self, client, auth_token, backup_service, sample_database):
        """Test GET /api/v1/backup/{backup_id} endpoint."""
        # Create a backup
        backup_id = await backup_service.create_backup()

        response = client.get(
            f"/api/v1/backup/{backup_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["backup_id"] == backup_id
        assert data["integrity_ok"] is True

    @pytest.mark.asyncio
    async def test_get_nonexistent_backup_info_endpoint(self, client, auth_token):
        """Test getting info for non-existent backup via API."""
        response = client.get(
            "/api/v1/backup/nonexistent",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_backup_endpoint(self, client, auth_token, backup_service, sample_database):
        """Test DELETE /api/v1/backup/{backup_id} endpoint."""
        # Create a backup
        backup_id = await backup_service.create_backup()

        response = client.delete(
            f"/api/v1/backup/{backup_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 204

        # Verify backup is deleted
        info = await backup_service.get_backup_info(backup_id)
        assert info is None

    @pytest.mark.asyncio
    async def test_get_scheduler_status_endpoint(self, client, auth_token):
        """Test GET /api/v1/backup/scheduler/status endpoint."""
        response = client.get(
            "/api/v1/backup/scheduler/status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        # Should return scheduler status (may be running or not)
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "enabled" in data
            assert "running" in data
            assert "interval_hours" in data
            assert "retention_days" in data
            assert "max_count" in data

    @pytest.mark.asyncio
    async def test_trigger_backup_endpoint(self, client, auth_token, sample_database):
        """Test POST /api/v1/backup/scheduler/trigger endpoint."""
        response = client.post(
            "/api/v1/backup/scheduler/trigger",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 201
        data = response.json()
        assert "backup_id" in data
        assert "message" in data
        assert len(data["backup_id"]) == 15

    @pytest.mark.asyncio
    async def test_scheduler_endpoints_without_auth_fail(self, client):
        """Test that scheduler endpoints require authentication."""
        # Test status endpoint
        response = client.get("/api/v1/backup/scheduler/status")
        assert response.status_code == 403

        # Test trigger endpoint
        response = client.post("/api/v1/backup/scheduler/trigger")
        assert response.status_code == 403
