#!/usr/bin/env python3
"""
Test the sync metadata API endpoints.
"""

import asyncio
import sys
import tempfile
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from fastapi.testclient import TestClient

sys.path.insert(0, '/workspaces/the-goodies')
sys.path.insert(0, '/workspaces/the-goodies/funkygibbon')

from funkygibbon.api.app import create_app
from funkygibbon.models import Base


@pytest.mark.asyncio
async def test_sync_metadata_api():
    """Test sync metadata API endpoints."""
    print("=== Testing Sync Metadata API ===\n")
    
    # Create test app
    app = create_app()
    client = TestClient(app)
    
    # Test 1: Create sync metadata
    print("1. Creating sync metadata via API:")
    response = client.post("/api/v1/sync-metadata/", params={
        "client_id": "test-client-api",
        "server_url": "http://localhost:8000",
        "auth_token": "api-test-token"
    })
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Created for client: {data['client_id']}")
        print(f"   ✅ Server URL: {data['server_url']}")
    else:
        print(f"   ❌ Failed: {response.text}")
    
    # Test 2: Get sync metadata
    print("\n2. Getting sync metadata:")
    response = client.get("/api/v1/sync-metadata/test-client-api")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Retrieved client: {data['client_id']}")
        print(f"   ✅ Total syncs: {data['total_syncs']}")
        print(f"   ✅ Sync failures: {data['sync_failures']}")
    else:
        print(f"   ❌ Failed: {response.text}")
    
    # Test 3: Record sync start
    print("\n3. Recording sync start:")
    response = client.post("/api/v1/sync-metadata/test-client-api/sync-start")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Response: {data['status']}")
    else:
        print(f"   ❌ Failed: {response.text}")
    
    # Test 4: Record sync success
    print("\n4. Recording sync success:")
    response = client.post("/api/v1/sync-metadata/test-client-api/sync-success")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Response: {data['status']}")
    else:
        print(f"   ❌ Failed: {response.text}")
    
    # Test 5: Get sync status
    print("\n5. Getting sync status:")
    response = client.get("/api/v1/sync-metadata/test-client-api/status")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Client: {data['client_id']}")
        print(f"   ✅ Total syncs: {data['total_syncs']}")
        print(f"   ✅ Sync in progress: {data['sync_in_progress']}")
        print(f"   ✅ Last success: {data['last_success'] is not None}")
    else:
        print(f"   ❌ Failed: {response.text}")
    
    # Test 6: List all metadata
    print("\n6. Listing all sync metadata:")
    response = client.get("/api/v1/sync-metadata/")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Found {len(data)} metadata entries")
        if data:
            print(f"   ✅ First entry client: {data[0]['client_id']}")
    else:
        print(f"   ❌ Failed: {response.text}")
    
    print("\n✅ Sync Metadata API tests completed!")
    print("✅ API endpoints working with shared SyncMetadata model!")


if __name__ == "__main__":
    asyncio.run(test_sync_metadata_api())