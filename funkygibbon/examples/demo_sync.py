#!/usr/bin/env python3
"""
Test script for demonstrating sync functionality.

Shows how to:
1. Send sync requests
2. Handle conflicts
3. Monitor sync progress
"""

import asyncio
import httpx
import json
from datetime import datetime, timezone
from typing import Dict


async def test_sync_api():
    """Test the sync API endpoints"""
    base_url = "http://localhost:8000/api/v1"
    
    print("🔄 Testing Enhanced Inbetweenies Sync Protocol")
    print("=" * 50)
    
    # 1. Check sync status
    print("\n1️⃣ Checking sync status for device 'test-device'...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/sync/status", params={"device_id": "test-device"})
        status = response.json()
        print(f"   Status: {json.dumps(status, indent=2)}")
    
    # 2. Send a full sync request
    print("\n2️⃣ Sending full sync request...")
    sync_request = {
        "protocol_version": "inbetweenies-v2",
        "device_id": "test-device",
        "user_id": "test-user",
        "sync_type": "full",
        "vector_clock": {"clocks": {}},
        "changes": []
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base_url}/sync/", json=sync_request)
        sync_response = response.json()
        print(f"   Response: {json.dumps(sync_response, indent=2)}")
    
    # 3. Create some local changes to sync
    print("\n3️⃣ Creating local changes to sync...")
    changes = [
        {
            "change_type": "create",
            "entity": {
                "id": "device-001",
                "version": f"{datetime.now(timezone.utc).isoformat()}Z-test-user",
                "entity_type": "device",
                "name": "Smart Light",
                "content": {"power": "on", "brightness": 75},
                "source_type": "manual",
                "user_id": "test-user",
                "parent_versions": []
            }
        },
        {
            "change_type": "create",
            "entity": {
                "id": "room-001",
                "version": f"{datetime.now(timezone.utc).isoformat()}Z-test-user",
                "entity_type": "room",
                "name": "Test Room",
                "content": {"area": 25},
                "source_type": "manual",
                "user_id": "test-user",
                "parent_versions": []
            },
            "relationships": [
                {
                    "id": "rel-001",
                    "from_entity_id": "device-001",
                    "from_entity_version": f"{datetime.now(timezone.utc).isoformat()}Z-test-user",
                    "to_entity_id": "room-001",
                    "to_entity_version": f"{datetime.now(timezone.utc).isoformat()}Z-test-user",
                    "relationship_type": "located_in",
                    "properties": {"position": "ceiling"}
                }
            ]
        }
    ]
    
    # 4. Send delta sync with changes
    print("\n4️⃣ Sending delta sync with local changes...")
    delta_request = {
        "protocol_version": "inbetweenies-v2",
        "device_id": "test-device",
        "user_id": "test-user",
        "sync_type": "delta",
        "vector_clock": {"clocks": {"test-device": "v1"}},
        "changes": changes
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base_url}/sync/", json=delta_request)
        if response.status_code == 200:
            delta_response = response.json()
            print(f"   Sync stats: {json.dumps(delta_response['sync_stats'], indent=2)}")
        else:
            print(f"   ❌ Error: {response.status_code} - {response.text}")
    
    # 5. Create a conflict scenario
    print("\n5️⃣ Creating conflict scenario...")
    
    # First update from device 1
    update1 = {
        "protocol_version": "inbetweenies-v2",
        "device_id": "device-1",
        "user_id": "user-1",
        "sync_type": "delta",
        "vector_clock": {"clocks": {}},
        "changes": [{
            "change_type": "update",
            "entity": {
                "id": "device-001",
                "version": f"{datetime.now(timezone.utc).isoformat()}Z-user-1",
                "entity_type": "device",
                "name": "Smart Light Updated",
                "content": {"power": "off", "color": "blue"},
                "source_type": "manual",
                "user_id": "user-1",
                "parent_versions": [changes[0]["entity"]["version"]]
            }
        }]
    }
    
    # Conflicting update from device 2
    update2 = {
        "protocol_version": "inbetweenies-v2",
        "device_id": "device-2",
        "user_id": "user-2",
        "sync_type": "delta",
        "vector_clock": {"clocks": {}},
        "changes": [{
            "change_type": "update",
            "entity": {
                "id": "device-001",
                "version": f"{datetime.now(timezone.utc).isoformat()}Z-user-2",
                "entity_type": "device",
                "name": "Smart Light Modified",
                "content": {"power": "on", "brightness": 50, "color": "red"},
                "source_type": "manual",
                "user_id": "user-2",
                "parent_versions": [changes[0]["entity"]["version"]]
            }
        }]
    }
    
    async with httpx.AsyncClient() as client:
        # Send first update
        print("   Sending update from device-1...")
        response1 = await client.post(f"{base_url}/sync/", json=update1)
        print(f"   Result: {response1.status_code}")
        
        # Send conflicting update
        print("   Sending conflicting update from device-2...")
        response2 = await client.post(f"{base_url}/sync/", json=update2)
        if response2.status_code == 200:
            result2 = response2.json()
            if result2.get("conflicts"):
                print(f"   ⚠️  Conflicts detected: {json.dumps(result2['conflicts'], indent=2)}")
        else:
            print(f"   ❌ Error: {response2.status_code}")
    
    # 6. Check pending conflicts
    print("\n6️⃣ Checking pending conflicts...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/sync/conflicts")
        conflicts = response.json()
        print(f"   Pending conflicts: {len(conflicts.get('conflicts', []))}")
    
    # 7. Test entity search after sync
    print("\n7️⃣ Searching for synced entities...")
    search_request = {
        "query": "smart",
        "entity_types": ["device"]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base_url}/graph/search", json=search_request)
        if response.status_code == 200:
            results = response.json()
            print(f"   Found {len(results.get('results', []))} entities")
            for result in results.get("results", [])[:3]:
                print(f"   - {result['name']} ({result['entity_type']})")
    
    print("\n✅ Sync API test completed!")


if __name__ == "__main__":
    asyncio.run(test_sync_api())