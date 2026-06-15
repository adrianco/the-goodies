"""
Tests for backup and restore functionality.

Covers the BackupService class, the BackupScheduler, and the backup API
endpoints — backups (including BLOBs) are created and restored correctly.

These tests are deliberately synchronous. The backup code is async, so it is
driven via `arun()` (a thin asyncio.run wrapper that disposes the shared engine
around each call). Every test runs chdir'd into its own tmp dir, so the relative
database (`./funkygibbon.db`) and `./backups` land in isolation and never touch
the repo.
"""

import asyncio
import json
import sqlite3
import time
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from fastapi.testclient import TestClient

import funkygibbon.database as dbmod
from funkygibbon.backup import BackupService
from funkygibbon.backup_scheduler import BackupScheduler
from funkygibbon.database import get_db_context, init_db
from funkygibbon.config import settings
from funkygibbon.api.app import create_app

SAMPLE_BLOB = b"This is test binary data for backup testing"


def arun(coro):
    """Run a coroutine to completion. Each test owns an isolated NullPool engine
    (see _isolated_db), so connections close eagerly and never leak across loops."""
    return asyncio.run(coro)


async def _seed_sample_db():
    await init_db()
    async with get_db_context() as session:
        await session.execute(text(
            "CREATE TABLE IF NOT EXISTS test_data "
            "(id INTEGER PRIMARY KEY, name TEXT, data BLOB)"
        ))
        await session.execute(text("DELETE FROM test_data"))
        await session.execute(
            text("INSERT INTO test_data (id, name, data) VALUES (:id, :name, :data)"),
            {"id": 1, "name": "test_record", "data": SAMPLE_BLOB},
        )
        await session.commit()


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Give each test its own database on an absolute path with a NullPool engine.

    The shared module engine uses a *relative* path with connection pooling, so
    a pooled connection from one test bleeds into the next regardless of cwd.
    Patching a per-test NullPool engine (connections close eagerly, WAL is
    checkpointed on close) makes backup/restore deterministic. chdir keeps the
    backup router's default ./backups dir inside the tmp dir too.
    """
    db_file = tmp_path / "funkygibbon.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    test_engine = create_async_engine(url, connect_args={"timeout": 5}, poolclass=NullPool)
    test_sessionmaker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(dbmod, "engine", test_engine)
    monkeypatch.setattr(dbmod, "async_session", test_sessionmaker)
    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.chdir(tmp_path)
    yield db_file
    asyncio.run(test_engine.dispose())


@pytest.fixture
def backup_dir(tmp_path):
    d = tmp_path / "test_backups"
    d.mkdir()
    return d


@pytest.fixture
def backup_service(backup_dir):
    return BackupService(backup_dir=backup_dir)


@pytest.fixture
def sample_database():
    """Seed the (chdir'd, isolated) database with a row including a BLOB."""
    arun(_seed_sample_db())
    yield


class TestBackupService:
    """Tests for the BackupService class."""

    def test_create_backup(self, backup_service, sample_database):
        backup_id = arun(backup_service.create_backup(description="Test backup"))

        assert len(backup_id) == 15  # YYYYMMDD_HHMMSS
        assert "_" in backup_id

        backup_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.db"
        assert backup_file.exists()
        assert backup_file.stat().st_size > 0

        metadata_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.json"
        assert metadata_file.exists()
        metadata = json.loads(metadata_file.read_text())
        assert metadata["backup_id"] == backup_id
        assert metadata["description"] == "Test backup"
        assert "checksum" in metadata
        assert metadata["size_bytes"] > 0

    def test_backup_includes_blob_data(self, backup_service, sample_database):
        backup_id = arun(backup_service.create_backup())
        backup_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.db"

        # Read the backup file directly (stdlib sqlite3, synchronous).
        conn = sqlite3.connect(backup_file)
        try:
            row = conn.execute("SELECT data FROM test_data WHERE id = 1").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == SAMPLE_BLOB

    def test_list_backups(self, backup_service, sample_database):
        async def _flow():
            id1 = await backup_service.create_backup(description="Backup 1")
            await asyncio.sleep(1.1)  # backup ids are second-resolution
            id2 = await backup_service.create_backup(description="Backup 2")
            return id1, id2, await backup_service.list_backups()

        id1, id2, backups = arun(_flow())
        assert len(backups) >= 2
        ids = [b["backup_id"] for b in backups]
        assert id1 in ids and id2 in ids
        for backup in backups:
            assert "integrity_ok" in backup

    def test_get_backup_info(self, backup_service, sample_database):
        async def _flow():
            backup_id = await backup_service.create_backup(description="Info test")
            return backup_id, await backup_service.get_backup_info(backup_id)

        backup_id, info = arun(_flow())
        assert info is not None
        assert info["backup_id"] == backup_id
        assert info["description"] == "Info test"
        assert info["integrity_ok"] is True
        assert info["checksum"] == info["current_checksum"]

    def test_get_nonexistent_backup_info(self, backup_service):
        assert arun(backup_service.get_backup_info("nonexistent_backup")) is None

    def test_restore_backup(self, backup_service, sample_database):
        async def _flow():
            backup_id = await backup_service.create_backup()

            # Add a second record after the backup.
            async with get_db_context() as session:
                await session.execute(
                    text("INSERT INTO test_data (id, name, data) VALUES (:id, :name, :data)"),
                    {"id": 2, "name": "new_record", "data": b"new data"},
                )
                await session.commit()
            async with get_db_context() as session:
                count = (await session.execute(text("SELECT COUNT(*) FROM test_data"))).scalar()
                assert count == 2

            await backup_service.restore_backup(backup_id)

            async with get_db_context() as session:
                count = (await session.execute(text("SELECT COUNT(*) FROM test_data"))).scalar()
                name = (await session.execute(text("SELECT name FROM test_data WHERE id = 1"))).scalar()
            return count, name

        count, name = arun(_flow())
        assert count == 1
        assert name == "test_record"

    def test_restore_with_checksum_verification(self, backup_service, sample_database):
        async def _flow():
            backup_id = await backup_service.create_backup()
            await backup_service.restore_backup(backup_id, verify_checksum=True)

        arun(_flow())  # should not raise

    def test_restore_corrupted_backup_fails(self, backup_service, sample_database):
        backup_id = arun(backup_service.create_backup())

        backup_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.db"
        with open(backup_file, "ab") as f:
            f.write(b"CORRUPTED DATA")

        with pytest.raises(ValueError, match="integrity check failed"):
            arun(backup_service.restore_backup(backup_id, verify_checksum=True))

    def test_restore_nonexistent_backup_fails(self, backup_service):
        with pytest.raises(ValueError, match="not found"):
            arun(backup_service.restore_backup("nonexistent_backup"))

    def test_delete_backup(self, backup_service, sample_database):
        backup_id = arun(backup_service.create_backup())
        backup_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.db"
        metadata_file = backup_service.backup_dir / f"funkygibbon_backup_{backup_id}.json"
        assert backup_file.exists() and metadata_file.exists()

        arun(backup_service.delete_backup(backup_id))
        assert not backup_file.exists()
        assert not metadata_file.exists()

    def test_delete_nonexistent_backup_fails(self, backup_service):
        with pytest.raises(ValueError, match="not found"):
            arun(backup_service.delete_backup("nonexistent_backup"))

    def test_backup_checksum_calculation(self, backup_service, sample_database):
        async def _flow():
            backup_id = await backup_service.create_backup()
            return await backup_service.get_backup_info(backup_id)

        info = arun(_flow())
        assert info["checksum"] == info["current_checksum"]
        assert len(info["checksum"]) == 64  # SHA-256 hex


class TestBackupScheduler:
    """Tests for the BackupScheduler class."""

    @pytest.fixture
    def scheduler_backup_dir(self, tmp_path):
        d = tmp_path / "scheduler_test_backups"
        d.mkdir()
        return d

    @pytest.fixture
    def scheduler(self, scheduler_backup_dir):
        service = BackupService(backup_dir=scheduler_backup_dir)
        sched = BackupScheduler(
            backup_service=service,
            enabled=True,
            interval_hours=1,
            retention_days=7,
            max_count=5,
        )
        yield sched
        if sched.is_running():
            sched.stop()

    def test_scheduler_initialization(self, scheduler):
        assert scheduler.enabled is True
        assert scheduler.interval_hours == 1
        assert scheduler.retention_days == 7
        assert scheduler.max_count == 5
        assert scheduler.is_running() is False

    def test_scheduler_start_stop(self, scheduler):
        scheduler.start()
        assert scheduler.is_running() is True
        scheduler.stop()
        assert scheduler.is_running() is False

    def test_scheduler_status(self, scheduler):
        status = scheduler.get_status()
        for key in ("enabled", "running", "interval_hours", "retention_days", "max_count"):
            assert key in status
        assert status["enabled"] is True
        assert status["interval_hours"] == 1

    def test_manual_backup_trigger(self, scheduler, sample_database):
        backup_id = scheduler.trigger_backup_now()
        assert backup_id is not None
        assert len(backup_id) == 15

        info = arun(scheduler.backup_service.get_backup_info(backup_id))
        assert info is not None
        assert info["integrity_ok"] is True

    def test_backup_cleanup_by_age(self, scheduler, sample_database):
        old_backup_id = scheduler.trigger_backup_now()

        # Backdate its metadata beyond the 7-day retention window.
        metadata_file = scheduler.backup_service.backup_dir / f"funkygibbon_backup_{old_backup_id}.json"
        metadata = json.loads(metadata_file.read_text())
        metadata["created_at"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        metadata_file.write_text(json.dumps(metadata, indent=2))

        time.sleep(1.1)  # distinct second-resolution backup id
        recent_backup_id = scheduler.trigger_backup_now()

        result = scheduler._run_cleanup()

        assert arun(scheduler.backup_service.get_backup_info(old_backup_id)) is None
        assert arun(scheduler.backup_service.get_backup_info(recent_backup_id)) is not None
        assert result["deleted_count"] >= 1

    def test_backup_cleanup_by_count(self, scheduler, sample_database):
        for i in range(7):  # max_count is 5
            scheduler.trigger_backup_now()
            time.sleep(1.0)  # ids are second-resolution; ensure distinct timestamps

        result = scheduler._run_cleanup()
        assert result["deleted_count"] == 2
        assert result["remaining_count"] == 5

        remaining = arun(scheduler.backup_service.list_backups())
        assert len(remaining) == 5

    def test_scheduler_disabled(self, scheduler_backup_dir):
        service = BackupService(backup_dir=scheduler_backup_dir)
        sched = BackupScheduler(backup_service=service, enabled=False)
        sched.start()
        assert sched.is_running() is False

    def test_scheduler_idempotent_start(self, scheduler):
        scheduler.start()
        assert scheduler.is_running() is True
        scheduler.start()  # safe to call again
        assert scheduler.is_running() is True
        scheduler.stop()

    def test_scheduler_idempotent_stop(self, scheduler):
        scheduler.stop()
        assert scheduler.is_running() is False
        scheduler.stop()  # safe to call again
        assert scheduler.is_running() is False


@pytest.fixture
def client(monkeypatch):
    """Sync TestClient with the periodic backup scheduler disabled (manual
    triggers still work). Lifespan creates the (isolated) DB and tables."""
    monkeypatch.setattr(settings, "backup_schedule_enabled", False)
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def auth_token(client):
    resp = client.post("/api/v1/auth/admin/login", json={"password": "admin"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestBackupAPI:
    """Integration tests for the backup API endpoints (sync TestClient)."""

    def test_create_backup_endpoint(self, client, auth_token):
        resp = client.post(
            "/api/v1/backup/create",
            json={"description": "API test backup"},
            headers=_auth(auth_token),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "backup_id" in data
        assert data["message"] == "Backup created successfully"
        assert data["size_bytes"] > 0

    def test_create_backup_without_auth_fails(self, client):
        resp = client.post("/api/v1/backup/create", json={"description": "Test"})
        assert resp.status_code in (401, 403)

    def test_list_backups_endpoint(self, client, auth_token):
        client.post("/api/v1/backup/create", json={"description": "List test"},
                    headers=_auth(auth_token))
        resp = client.get("/api/v1/backup/list", headers=_auth(auth_token))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_backup_info_endpoint(self, client, auth_token):
        created = client.post("/api/v1/backup/create", json={}, headers=_auth(auth_token)).json()
        backup_id = created["backup_id"]
        resp = client.get(f"/api/v1/backup/{backup_id}", headers=_auth(auth_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["backup_id"] == backup_id
        assert data["integrity_ok"] is True

    def test_get_nonexistent_backup_info_endpoint(self, client, auth_token):
        resp = client.get("/api/v1/backup/nonexistent", headers=_auth(auth_token))
        assert resp.status_code == 404

    def test_delete_backup_endpoint(self, client, auth_token):
        backup_id = client.post("/api/v1/backup/create", json={}, headers=_auth(auth_token)).json()["backup_id"]
        resp = client.delete(f"/api/v1/backup/{backup_id}", headers=_auth(auth_token))
        assert resp.status_code == 204
        # Confirm it is gone.
        assert client.get(f"/api/v1/backup/{backup_id}", headers=_auth(auth_token)).status_code == 404

    def test_get_scheduler_status_endpoint(self, client, auth_token):
        resp = client.get("/api/v1/backup/scheduler/status", headers=_auth(auth_token))
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            data = resp.json()
            for key in ("enabled", "running", "interval_hours", "retention_days", "max_count"):
                assert key in data

    def test_trigger_backup_endpoint(self, client, auth_token):
        resp = client.post("/api/v1/backup/scheduler/trigger", headers=_auth(auth_token))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "backup_id" in data and "message" in data
        assert len(data["backup_id"]) == 15

    def test_scheduler_endpoints_without_auth_fail(self, client):
        assert client.get("/api/v1/backup/scheduler/status").status_code in (401, 403)
        assert client.post("/api/v1/backup/scheduler/trigger").status_code in (401, 403)
