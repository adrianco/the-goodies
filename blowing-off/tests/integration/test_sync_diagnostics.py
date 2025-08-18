"""
Diagnostic tests to verify sync service is working properly.

These tests help diagnose why sync operations timeout on Windows CI.
"""

import pytest
import pytest_asyncio
import asyncio
import httpx
import time
import sys
import os
from pathlib import Path
import tempfile

from blowingoff import BlowingOffClient


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == "win32" and os.environ.get('CI') == 'true',
                    reason="Windows CI has SQLite file locking issues - see issue #7")
class TestSyncDiagnostics:
    """Diagnostic tests for sync service."""

    @pytest.mark.asyncio
    async def test_server_health(self, server_url):
        """Test that server is responding."""
        print(f"\n=== Testing server health ===")
        print(f"Server URL: {server_url}")

        start = time.time()
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{server_url}/health")
            elapsed = time.time() - start

            print(f"Health check took {elapsed:.2f} seconds")
            print(f"Response status: {response.status_code}")
            assert response.status_code == 200
            data = response.json()
            print(f"Response data: {data}")
            assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_simple_sync_request(self, server_url, auth_token):
        """Test a simple sync request without any data."""
        print(f"\n=== Testing simple sync request ===")

        start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = {"Authorization": f"Bearer {auth_token}"}

            # Send proper Inbetweenies v2 sync request
            request_data = {
                "protocol_version": "inbetweenies-v2",
                "device_id": "test-diagnostic",
                "user_id": "test-user",
                "sync_type": "full",
                "vector_clock": {},
                "changes": []
            }

            print(f"Sending sync request: {request_data}")
            response = await client.post(
                f"{server_url}/api/v1/sync/",
                json=request_data,
                headers=headers
            )
            elapsed = time.time() - start

            print(f"Sync request took {elapsed:.2f} seconds")
            print(f"Response status: {response.status_code}")
            assert response.status_code == 200

            data = response.json()
            print(f"Response keys: {data.keys()}")
            assert "changes" in data
            assert "vector_clock" in data

    @pytest.mark.asyncio
    async def test_single_client_operations(self, server_url, auth_token):
        """Test single client can perform basic operations."""
        print(f"\n=== Testing single client operations ===")

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        print(f"Database path: {db_path}")

        try:
            client = BlowingOffClient(db_path)

            # Test connection
            print("Connecting to server...")
            start = time.time()
            await client.connect(server_url, auth_token, "test-single")
            connect_time = time.time() - start
            print(f"Connection took {connect_time:.2f} seconds")

            # Test initial sync
            print("Performing initial sync...")
            start = time.time()
            result = await client.sync()
            sync_time = time.time() - start
            print(f"Initial sync took {sync_time:.2f} seconds")
            print(f"Sync result: success={result.success}, entities={result.synced_entities}")
            assert result.success

            # Test creating an entity locally
            print("Creating local entity...")
            from inbetweenies.models import Entity, EntityType, SourceType
            import uuid

            entity = Entity(
                id=str(uuid.uuid4()),
                version=Entity.create_version("test-user"),
                entity_type=EntityType.DEVICE,
                name="Test Device",
                content={"type": "test"},
                source_type=SourceType.MANUAL,
                user_id="test-user",
                parent_versions=[]
            )

            stored = await client.graph_operations.store_entity(entity)
            print(f"Created entity: {stored.id}")

            # Test syncing the entity
            print("Syncing created entity...")
            start = time.time()
            result = await client.sync()
            sync_time = time.time() - start
            print(f"Entity sync took {sync_time:.2f} seconds")
            print(f"Sync result: success={result.success}, entities={result.synced_entities}")
            assert result.success

            await client.disconnect()
            print("Client disconnected successfully")

        finally:
            Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_concurrent_sync_timing(self, server_url, auth_token):
        """Test how long concurrent sync operations take."""
        print(f"\n=== Testing concurrent sync timing ===")
        print(f"Platform: {sys.platform}")
        print(f"CI environment: {os.environ.get('CI', 'false')}")

        # Create two clients
        clients = []
        db_paths = []

        for i in range(2):
            with tempfile.NamedTemporaryFile(suffix=f"-{i}.db", delete=False) as f:
                db_path = f.name
                db_paths.append(db_path)

            client = BlowingOffClient(db_path)
            await client.connect(server_url, auth_token, f"test-concurrent-{i}")
            clients.append(client)

        try:
            # Test syncing both at the same time
            print("Starting concurrent syncs...")
            start = time.time()

            # Create sync tasks
            tasks = [client.sync() for client in clients]

            # Wait for both with timeout
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=10.0
                )
                elapsed = time.time() - start

                print(f"Concurrent syncs took {elapsed:.2f} seconds")

                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(f"Client {i} failed: {result}")
                    else:
                        print(f"Client {i}: success={result.success}, entities={result.synced_entities}")

            except asyncio.TimeoutError:
                elapsed = time.time() - start
                print(f"ERROR: Concurrent syncs timed out after {elapsed:.2f} seconds!")
                # This is the issue we're trying to diagnose

        finally:
            # Cleanup
            for client in clients:
                try:
                    await client.disconnect()
                except:
                    pass

            for db_path in db_paths:
                Path(db_path).unlink(missing_ok=True)
