"""Synchronous unit tests for the blowing-off client's sync wire handling.

These cover the two correctness fixes that don't need a live server: deriving a
server change's updated_at from its version (not the client clock), and parsing
the response server_time into a UTC-aware watermark.
"""

from datetime import datetime, timezone

from blowingoff.sync.protocol import InbetweeniesProtocol
from blowingoff.sync.engine import SyncEngine
from inbetweenies.models import Entity
from inbetweenies.sync import SyncOperation

VERSION = "2026-06-15T10:00:00.123456+00:00-000001-alice"


def _response(change_type="update", content=None):
    return {
        "protocol_version": "inbetweenies-v2",
        "sync_type": "full",
        "changes": [{
            "change_type": change_type,
            "entity": {
                "id": "e1", "version": VERSION, "entity_type": "device",
                "name": "Lamp", "content": content or {}, "source_type": "manual",
                "user_id": "alice", "parent_versions": [],
            },
            "relationships": [],
        }],
        "conflicts": [],
        "server_time": "2026-06-15T10:00:01+00:00",
    }


def _protocol():
    return InbetweeniesProtocol("http://server", "token", "client-1")


def test_parse_sync_delta_derives_updated_at_from_version():
    changes, conflicts = _protocol().parse_sync_delta(_response())
    assert len(changes) == 1
    # updated_at comes from the version timestamp, NOT datetime.now().
    assert changes[0].updated_at == Entity.version_timestamp(VERSION)
    assert changes[0].updated_at.tzinfo is not None
    assert not conflicts


def test_parse_sync_delta_marks_tombstone_as_delete():
    changes, _ = _protocol().parse_sync_delta(_response("delete", content={"deleted": True}))
    assert changes[0].operation == SyncOperation.DELETE
    assert changes[0].data["content"]["deleted"] is True


def test_parse_server_time_handles_offset_z_naive_and_missing():
    # +00:00 offset
    t1 = SyncEngine._parse_server_time("2026-06-15T10:00:01+00:00")
    assert t1.tzinfo is not None and t1.isoformat() == "2026-06-15T10:00:01+00:00"
    # trailing Z
    t2 = SyncEngine._parse_server_time("2026-06-15T10:00:01Z")
    assert t2 == t1
    # naive -> assumed UTC
    t3 = SyncEngine._parse_server_time("2026-06-15T10:00:01")
    assert t3 == t1
    # missing -> falls back to an aware "now"
    t4 = SyncEngine._parse_server_time(None)
    assert t4.tzinfo is not None
