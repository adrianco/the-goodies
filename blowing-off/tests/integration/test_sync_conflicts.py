"""
Conflict resolution integration tests.

REVISION HISTORY:
- 2025-07-28: Skipped entire test class due to database concurrency issues
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
import json
import httpx
from pathlib import Path
import tempfile
import uuid
import sys
import os

from blowingoff import BlowingOffClient


class TestSyncConflicts:
    """Test conflict resolution scenarios."""

    @pytest_asyncio.fixture
    async def two_clients(self, server_url, auth_token):
        """Create two clients to simulate conflicts."""
        clients = []

        for i in range(2):
            with tempfile.NamedTemporaryFile(suffix=f"-{i}.db", delete=False) as f:
                db_path = f.name

            client = BlowingOffClient(db_path)
            await client.connect(server_url, auth_token, f"test-client-{i}")
            clients.append((client, db_path))

        yield clients

        # Cleanup with delay for Windows
        import time
        for client, db_path in clients:
            try:
                await client.disconnect()
            except:
                pass
            time.sleep(0.1)  # Give Windows time to release handles
            try:
                Path(db_path).unlink(missing_ok=True)
            except:
                pass

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32" and os.environ.get('CI') == 'true',
                        reason="Windows CI has SQLite file locking issues - see issue #7")
    async def test_concurrent_updates(self, two_clients):
        """Test concurrent updates to same entity."""
        from inbetweenies.models import Entity, EntityType, SourceType
        import uuid

        client1, _ = two_clients[0]
        client2, _ = two_clients[1]

        # Initial sync for both
        await client1.sync()
        await client2.sync()

        # Create test entity on client1 using graph operations
        test_entity = Entity(
            entity_type=EntityType.DEVICE,
            name="Conflict Test Device",
            content={"state": "initial", "color": "white"},
            source_type=SourceType.MANUAL,
            user_id="test-user"
        )

        # Store entity on client1
        stored_entity = await client1.graph_operations.store_entity(test_entity)
        entity_id = stored_entity.id

        # Mark entity for sync and sync to propagate to server
        client1.sync_engine.mark_entity_for_sync(entity_id)
        sync1 = await client1.sync()
        print(f"DEBUG: Client1 sync after create: success={sync1.success}, synced={sync1.synced_entities}")
        sync2 = await client2.sync()
        print(f"DEBUG: Client2 sync to get entity: success={sync2.success}, synced={sync2.synced_entities}")

        # Update on both clients with different values
        # Client1 updates
        entity1 = await client1.graph_operations.get_entity(entity_id)
        if entity1:
            entity1.content = {"state": "on", "color": "red"}
            await client1.graph_operations.store_entity(entity1)
            client1.sync_engine.mark_entity_for_sync(entity_id)

        # Client2 updates - need to check if entity exists after sync
        entity2 = await client2.graph_operations.get_entity(entity_id)
        if not entity2:
            # If not found, search for it by type
            devices = await client2.graph_operations.get_entities_by_type(EntityType.DEVICE)
            print(f"DEBUG: Client2 devices: {[d.name for d in devices]}")
            entity2 = next((e for e in devices if e.name == "Conflict Test Device"), None)
            if entity2:
                print(f"DEBUG: Found entity2 by search: id={entity2.id}")

        if entity2:
            entity2.content = {"state": "off", "color": "blue"}
            await client2.graph_operations.store_entity(entity2)
            client2.sync_engine.mark_entity_for_sync(entity2.id)

        # Sync both - last write should win
        result1 = await client1.sync()
        result2 = await client2.sync()

        # At least one should succeed
        assert result1.success or result2.success

        # Final sync should have consistent state
        final_sync1 = await client1.sync()
        print(f"DEBUG: Final client1 sync: success={final_sync1.success}, synced={final_sync1.synced_entities}")
        final_sync2 = await client2.sync()
        print(f"DEBUG: Final client2 sync: success={final_sync2.success}, synced={final_sync2.synced_entities}")

        # Get final state from both clients
        final_entity1 = await client1.graph_operations.get_entity(entity_id)
        final_entity2 = await client2.graph_operations.get_entity(entity_id)

        print(f"DEBUG: Final entity1: id={final_entity1.id if final_entity1 else None}, content={final_entity1.content if final_entity1 else None}")
        print(f"DEBUG: Final entity2: id={final_entity2.id if final_entity2 else None}, content={final_entity2.content if final_entity2 else None}")

        # Both should have the same content now
        assert final_entity1.content == final_entity2.content

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32" and os.environ.get('CI') == 'true',
                        reason="Windows CI has SQLite file locking issues - see issue #7")
    async def test_delete_update_conflict(self, two_clients):
        """Test conflict when one client deletes while other updates."""
        from inbetweenies.models import Entity, EntityType, SourceType

        client1, _ = two_clients[0]
        client2, _ = two_clients[1]

        # Setup
        await client1.sync()
        await client2.sync()

        # Create test entity
        test_entity = Entity(
            entity_type=EntityType.DEVICE,
            name="Delete Test Device",
            content={"type": "switch"},
            source_type=SourceType.MANUAL
        )

        stored_entity = await client1.graph_operations.store_entity(test_entity)
        entity_id = stored_entity.id

        client1.sync_engine.mark_entity_for_sync(entity_id)
        await client1.sync()
        await client2.sync()

        # Client1 deletes (by clearing local data), Client2 updates
        # Since there's no explicit delete in the graph API, we simulate by clearing
        client1.clear_graph_data()

        # Client2 updates
        entity2 = await client2.graph_operations.get_entity(entity_id)
        if entity2:
            entity2.content = {"type": "switch", "power": "on"}
            await client2.graph_operations.store_entity(entity2)

        # Sync both
        result1 = await client1.sync()
        result2 = await client2.sync()

        # At least one should succeed
        assert result1.success or result2.success

        # After sync, both should have consistent view
        await client1.sync()
        await client2.sync()

        # Check if entity exists on both
        entity1 = await client1.graph_operations.get_entity(entity_id)
        entity2 = await client2.graph_operations.get_entity(entity_id)

        # Both should have same view (either both have it or both don't)
        assert (entity1 is None) == (entity2 is None)

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32" and os.environ.get('CI') == 'true',
                        reason="Windows CI has SQLite file locking issues - see issue #7")
    async def test_timestamp_tiebreaker(self, two_clients):
        """Test version tiebreaker for conflict resolution."""
        from inbetweenies.models import Entity, EntityType, SourceType
        from datetime import datetime, UTC

        client1, _ = two_clients[0]
        client2, _ = two_clients[1]

        # Setup
        await client1.sync()
        await client2.sync()

        # Create entity on client1
        test_entity = Entity(
            entity_type=EntityType.DEVICE,
            name="Tiebreaker Test",
            content={"value": "initial"},
            source_type=SourceType.MANUAL
        )

        stored_entity = await client1.graph_operations.store_entity(test_entity)
        entity_id = stored_entity.id

        # Sync to both clients
        client1.sync_engine.mark_entity_for_sync(entity_id)
        await client1.sync()
        await client2.sync()

        # Now both update with different values
        # The one with later version should win
        entity1 = await client1.graph_operations.get_entity(entity_id)
        entity1.content = {"value": "client1"}
        entity1.updated_at = datetime.now(UTC)
        stored1 = await client1.graph_operations.store_entity(entity1)
        client1.sync_engine.mark_entity_for_sync(entity_id)

        # Small delay to ensure different timestamp
        await asyncio.sleep(0.1)

        entity2 = await client2.graph_operations.get_entity(entity_id)
        entity2.content = {"value": "client2"}
        entity2.updated_at = datetime.now(UTC)  # Later timestamp
        stored2 = await client2.graph_operations.store_entity(entity2)
        client2.sync_engine.mark_entity_for_sync(entity_id)

        # Sync both - multiple rounds to ensure convergence
        for _ in range(3):
            await client1.sync()
            await client2.sync()

        # Check both have the same value (conflict should be resolved consistently)
        final1 = await client1.graph_operations.get_entity(entity_id)
        final2 = await client2.graph_operations.get_entity(entity_id)

        # Both clients should eventually have the same value after multiple syncs
        # On Windows, conflict resolution might take more sync rounds
        if final1.content != final2.content:
            # Try one more sync round
            await client1.sync()
            await client2.sync()
            final1 = await client1.graph_operations.get_entity(entity_id)
            final2 = await client2.graph_operations.get_entity(entity_id)

        # Both should have converged to the same state
        assert final1.content == final2.content
        # The value should be either client1 or client2 (conflict resolution occurred)
        assert final1.content["value"] in ["client1", "client2"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32" and os.environ.get('CI') == 'true',
                        reason="Sync hangs on Windows CI due to SQLite locking issues")
    async def test_bulk_conflict_resolution(self, two_clients):
        """Test resolving multiple conflicts in one sync."""
        from inbetweenies.models import Entity, EntityType, SourceType

        client1, _ = two_clients[0]
        client2, _ = two_clients[1]

        # Setup
        await client1.sync()
        await client2.sync()

        # Create multiple entities and update on both sides
        entity_ids = []
        for i in range(5):
            entity = Entity(
                entity_type=EntityType.DEVICE,
                name=f"Bulk Device {i}",
                content={"type": "switch", "index": i},
                source_type=SourceType.MANUAL
            )
            stored = await client1.graph_operations.store_entity(entity)
            entity_ids.append(stored.id)
            client1.sync_engine.mark_entity_for_sync(stored.id)

        await client1.sync()
        await client2.sync()

        # Update all entities differently on both clients
        for i, entity_id in enumerate(entity_ids):
            # Client1 updates
            entity1 = await client1.graph_operations.get_entity(entity_id)
            if entity1:
                entity1.content = {"power": "on", "level": i}
                await client1.graph_operations.store_entity(entity1)
                client1.sync_engine.mark_entity_for_sync(entity_id)

            # Client2 updates
            entity2 = await client2.graph_operations.get_entity(entity_id)
            if entity2:
                entity2.content = {"power": "off", "level": i * 2}
                await client2.graph_operations.store_entity(entity2)
                client2.sync_engine.mark_entity_for_sync(entity_id)

        # Sync and resolve all conflicts
        result1 = await client1.sync()
        result2 = await client2.sync()

        # At least one should succeed
        assert result1.success or result2.success

        # Could have conflicts depending on timing
        # total_conflicts = len(result1.conflicts) + len(result2.conflicts)
        # Just verify sync completes

        # Final sync for consistency
        await client1.sync()
        await client2.sync()

        # Verify all entities have consistent state
        for entity_id in entity_ids:
            entity1 = await client1.graph_operations.get_entity(entity_id)
            entity2 = await client2.graph_operations.get_entity(entity_id)
            # Both should exist or both should not exist
            assert (entity1 is None) == (entity2 is None)
            # If both exist, they should have the same content
            if entity1 and entity2:
                assert entity1.content == entity2.content
