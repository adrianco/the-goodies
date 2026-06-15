"""Test conflict resolution functionality."""

import pytest
from datetime import datetime, timezone, timedelta

from inbetweenies.sync.conflict import ConflictResolver, ConflictResolution


class TestConflictResolver:
    """Test ConflictResolver functionality."""

    def test_resolve_with_newer_remote(self):
        """Test resolution when remote has newer timestamp."""
        base_time = datetime.now(timezone.utc)

        local = {
            "id": "test-entity",
            "updated_at": base_time - timedelta(hours=1),
            "sync_id": "local-sync",
            "content": {"value": 100}
        }

        remote = {
            "id": "test-entity",
            "updated_at": base_time,
            "sync_id": "remote-sync",
            "content": {"value": 200}
        }

        resolution = ConflictResolver.resolve(local, remote)

        assert resolution.winner == remote
        assert resolution.loser == local
        assert "remote has newer timestamp" in resolution.reason
        assert resolution.timestamp_diff_ms > 0

    def test_resolve_with_newer_local(self):
        """Test resolution when local has newer timestamp."""
        base_time = datetime.now(timezone.utc)

        local = {
            "id": "test-entity",
            "updated_at": base_time,
            "sync_id": "local-sync",
            "content": {"value": 100}
        }

        remote = {
            "id": "test-entity",
            "updated_at": base_time - timedelta(hours=1),
            "sync_id": "remote-sync",
            "content": {"value": 200}
        }

        resolution = ConflictResolver.resolve(local, remote)

        assert resolution.winner == local
        assert resolution.loser == remote
        assert "local has newer timestamp" in resolution.reason
        assert resolution.timestamp_diff_ms < 0

    def test_resolve_with_same_timestamp_version_tiebreaker(self):
        """Within 1s the greater version string wins (canonical, PROTOCOL.md §7)."""
        base_time = datetime.now(timezone.utc)

        local = {
            "id": "test-entity",
            "updated_at": base_time,
            "version": "2026-06-15T10:00:00+00:00-000001-alice",
            "content": {"value": 100}
        }

        remote = {
            "id": "test-entity",
            "updated_at": base_time,
            "version": "2026-06-15T10:00:00+00:00-000002-alice",  # greater
            "content": {"value": 200}
        }

        resolution = ConflictResolver.resolve(local, remote)

        assert resolution.winner == remote
        assert resolution.loser == local
        assert "version" in resolution.reason
        assert abs(resolution.timestamp_diff_ms) < 1000

    def test_resolve_with_string_timestamps(self):
        """Test resolution with ISO format string timestamps."""
        local = {
            "id": "test-entity",
            "updated_at": "2025-01-01T10:00:00+00:00",
            "sync_id": "local-sync",
            "content": {"value": 100}
        }

        remote = {
            "id": "test-entity",
            "updated_at": "2025-01-01T11:00:00+00:00",  # 1 hour later
            "sync_id": "remote-sync",
            "content": {"value": 200}
        }

        resolution = ConflictResolver.resolve(local, remote)

        assert resolution.winner == remote
        assert resolution.loser == local
        assert "remote has newer timestamp" in resolution.reason
        assert resolution.timestamp_diff_ms == 3600000  # 1 hour in milliseconds

    def test_resolve_with_z_suffix_timestamps(self):
        """Test resolution with timestamps ending in 'Z'."""
        local = {
            "id": "test-entity",
            "updated_at": "2025-01-01T10:00:00Z",
            "sync_id": "local-sync",
            "content": {"value": 100}
        }

        remote = {
            "id": "test-entity",
            "updated_at": "2025-01-01T09:00:00Z",  # 1 hour earlier
            "sync_id": "remote-sync",
            "content": {"value": 200}
        }

        resolution = ConflictResolver.resolve(local, remote)

        assert resolution.winner == local
        assert resolution.loser == remote
        assert "local has newer timestamp" in resolution.reason
        assert resolution.timestamp_diff_ms == -3600000  # -1 hour in milliseconds

    def test_resolve_with_naive_timestamps(self):
        """Test resolution with timezone-naive timestamps (assumes UTC)."""
        base_time = datetime.now()  # Naive datetime

        local = {
            "id": "test-entity",
            "updated_at": base_time - timedelta(minutes=30),
            "sync_id": "local-sync",
            "content": {"value": 100}
        }

        remote = {
            "id": "test-entity",
            "updated_at": base_time,
            "sync_id": "remote-sync",
            "content": {"value": 200}
        }

        resolution = ConflictResolver.resolve(local, remote)

        assert resolution.winner == remote
        assert resolution.loser == local
        assert "remote has newer timestamp" in resolution.reason
        assert resolution.timestamp_diff_ms == 1800000  # 30 minutes in milliseconds

    def test_resolve_with_missing_version(self):
        """Within 1s and both versions absent/empty, local wins deterministically."""
        base_time = datetime.now(timezone.utc)

        local = {
            "id": "test-entity",
            "updated_at": base_time,
            "version": None,
            "content": {"value": 100}
        }

        remote = {
            "id": "test-entity",
            "updated_at": base_time,
            # Missing version
            "content": {"value": 200}
        }

        resolution = ConflictResolver.resolve(local, remote)

        # With both None/missing, local wins (empty string comparison)
        assert resolution.winner == local
        assert resolution.loser == remote
        assert "version" in resolution.reason

    def test_resolve_with_mixed_timestamp_types(self):
        """Test resolution with mixed datetime and string timestamps."""
        base_time = datetime.now(timezone.utc)

        local = {
            "id": "test-entity",
            "updated_at": base_time,  # datetime object
            "sync_id": "local-sync",
            "content": {"value": 100}
        }

        remote = {
            "id": "test-entity",
            "updated_at": (base_time + timedelta(hours=1)).isoformat(),  # string
            "sync_id": "remote-sync",
            "content": {"value": 200}
        }

        resolution = ConflictResolver.resolve(local, remote)

        assert resolution.winner == remote
        assert resolution.loser == local
        assert "remote has newer timestamp" in resolution.reason
        assert resolution.timestamp_diff_ms == 3600000  # 1 hour in milliseconds

    def test_resolution_attributes(self):
        """Test ConflictResolution attributes."""
        base_time = datetime.now(timezone.utc)

        local = {
            "id": "test-entity",
            "updated_at": base_time - timedelta(seconds=30),
            "sync_id": "local-sync",
            "content": {"value": 100},
            "name": "Local Entity"
        }

        remote = {
            "id": "test-entity",
            "updated_at": base_time,
            "sync_id": "remote-sync",
            "content": {"value": 200},
            "name": "Remote Entity"
        }

        resolution = ConflictResolver.resolve(local, remote)

        # Check all attributes are preserved
        assert resolution.winner["id"] == "test-entity"
        assert resolution.winner["name"] == "Remote Entity"
        assert resolution.winner["content"]["value"] == 200

        assert resolution.loser["id"] == "test-entity"
        assert resolution.loser["name"] == "Local Entity"
        assert resolution.loser["content"]["value"] == 100

        assert resolution.timestamp_diff_ms == 30000  # 30 seconds
