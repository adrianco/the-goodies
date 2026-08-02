"""End-to-end: a client change that loses conflict resolution is acknowledged.

ADR-011 §2. Server-side unit tests assert the ack and the preserved version
row, but the property that matters is a client one: after pushing a change
that loses, the client must stop retrying it.

Withholding the ack from a loser was correct while every client applied every
pulled change — the retry eventually converged. It stops being correct once a
client guards its pending ids against pull-apply (ADR-011 §1, which KittenKong
implements): the guard blocks the server's version because the id is pending,
the push loses and is not acked, the pending mark survives, and every later
sync repeats identically. The entity never converges on that client.

blowing-off has no pull-guard (it captures its push payload before the pull,
so it never needed one — see tests/unit/test_sync_push.py), which is exactly
why it can observe the server half of this contract cleanly: if the ack is
withheld, the pending mark simply never clears.
"""

import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from blowingoff import BlowingOffClient
from inbetweenies.models import Entity, EntityType, SourceType


def _ancient_version() -> str:
    """A version stamped far enough in the past to lose LWW deterministically."""
    old = datetime.now(UTC) - timedelta(days=3650)
    return f"{old.isoformat()}Z-000001-test-user"


@pytest.mark.integration
@pytest.mark.asyncio
class TestLosingChangeIsAcknowledged:

    @pytest_asyncio.fixture
    async def client(self, server_url, auth_token):
        # A private directory, not NamedTemporaryFile: the client derives its
        # graph store from the DB file's PARENT (`<parent>/.blowing-off-graph`),
        # so every client using the system temp dir shares one graph store --
        # and its pending marks -- across tests and across runs.
        work_dir = tempfile.mkdtemp(prefix="blowingoff-losing-")
        db_path = str(Path(work_dir) / "client.db")

        client = BlowingOffClient(db_path)
        await client.connect(server_url, auth_token, "test-losing-change")
        yield client
        await client.disconnect()
        shutil.rmtree(work_dir, ignore_errors=True)

    async def _server_entity_id(self, server_url, auth_token) -> str:
        """Create an entity server-side and return its id."""
        async with httpx.AsyncClient(base_url=server_url) as http:
            response = await http.post(
                "/api/v1/graph/entities",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={
                    "entity_type": "note",
                    "name": "server-owned",
                    "content": {"origin": "server"},
                    "source_type": "manual",
                    "user_id": "server-user",
                },
            )
            response.raise_for_status()
            return response.json()["entity"]["id"]

    async def test_losing_push_is_acked_and_not_retried_forever(
        self, client, server_url, auth_token
    ):
        """The livelock regression: a losing change must not stay pending."""
        entity_id = await self._server_entity_id(server_url, auth_token)
        await client.sync()

        # A local edit stamped long in the past: it will lose LWW against the
        # server's newer version, deterministically and without racing.
        losing = Entity(
            id=entity_id,
            version=_ancient_version(),
            entity_type=EntityType.NOTE,
            name="client-edit-that-loses",
            content={"origin": "client"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[],
        )
        await client.graph_operations.store_entity(losing)
        assert client.pending_changes_count > 0, "the local edit should be queued"

        result = await client.sync()
        assert result.success, result.errors

        assert client.pending_changes_count == 0, (
            "a change that lost resolution must still be acknowledged, or the "
            "client retries it on every sync forever (ADR-011 §2)"
        )

        # And it stays cleared — the retry does not come back on the next cycle.
        await client.sync()
        assert client.pending_changes_count == 0

    async def test_the_server_version_still_wins(
        self, client, server_url, auth_token
    ):
        """Acked does not mean applied: the loser must not become current."""
        entity_id = await self._server_entity_id(server_url, auth_token)
        await client.sync()

        losing = Entity(
            id=entity_id,
            version=_ancient_version(),
            entity_type=EntityType.NOTE,
            name="client-edit-that-loses",
            content={"origin": "client"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[],
        )
        await client.graph_operations.store_entity(losing)
        await client.sync()

        async with httpx.AsyncClient(base_url=server_url) as http:
            response = await http.get(
                f"/api/v1/graph/entities/{entity_id}",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            response.raise_for_status()
            assert response.json()["entity"]["name"] == "server-owned", (
                "the losing client edit must not have overwritten the server"
            )
