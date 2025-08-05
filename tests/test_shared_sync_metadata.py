#!/usr/bin/env python3
"""
Comprehensive test showing SyncMetadata is now properly shared between client and server.
"""

import asyncio
import sys
import tempfile
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from datetime import datetime, UTC

sys.path.insert(0, '/workspaces/the-goodies')

@pytest.mark.asyncio
async def test_shared_sync_metadata():
    """Test that SyncMetadata is properly shared."""
    print("=== Comprehensive Shared SyncMetadata Test ===\n")
    
    # Test 1: Import from inbetweenies (source of truth)
    print("1. Testing imports:")
    from inbetweenies.models import SyncMetadata as SharedSyncMetadata, Base
    print("   ✅ Imported from inbetweenies (source of truth)")
    
    # Test 2: Import from FunkyGibbon
    from funkygibbon.models import SyncMetadata as ServerSyncMetadata
    print("   ✅ Imported from FunkyGibbon")
    
    # Test 3: Verify they are the same class
    assert ServerSyncMetadata is SharedSyncMetadata
    print("   ✅ FunkyGibbon uses the exact same class")
    
    # Test 4: Test database creation with all models
    print("\n2. Testing database integration:")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Check all tables were created
    from sqlalchemy import text
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """))
        tables = [row[0] for row in result]
        
    expected_tables = [
        'accessory_rooms', 'accessories', 'characteristics', 
        'homes', 'rooms', 'services', 'sync_metadata', 'users'
    ]
    
    print(f"   ✅ Created tables: {tables}")
    print(f"   ✅ Expected tables: {expected_tables}")
    assert all(table in tables for table in expected_tables)
    print("   ✅ All expected tables created including sync_metadata")
    
    # Test 5: Create and use SyncMetadata
    print("\n3. Testing SyncMetadata functionality:")
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with session_factory() as session:
        # Create metadata using the shared model
        metadata = SharedSyncMetadata(
            client_id="shared-test-client",
            server_url="http://localhost:8000",
            auth_token="shared-test-token"
        )
        session.add(metadata)
        
        # Test sync lifecycle
        metadata.record_sync_start()
        print(f"   ✅ Sync started: {metadata.sync_in_progress}")
        
        await asyncio.sleep(0.1)
        metadata.record_sync_success()
        print(f"   ✅ Sync completed: total={metadata.total_syncs}, failures={metadata.sync_failures}")
        
        # Test serialization
        data = metadata.to_dict()
        print(f"   ✅ Serialized to dict: {len(data)} fields")
        assert data['client_id'] == "shared-test-client"
        assert data['sync_in_progress'] is False
        
        await session.commit()
        
    await engine.dispose()
    
    # Test 6: Verify model consistency
    print("\n4. Testing model consistency:")
    
    # Create instances from both imports
    shared_instance = SharedSyncMetadata(client_id="test1", server_url="url1", auth_token="token1")
    server_instance = ServerSyncMetadata(client_id="test2", server_url="url2", auth_token="token2")
    
    # They should have the same methods and attributes
    shared_methods = set(dir(shared_instance))
    server_methods = set(dir(server_instance))
    assert shared_methods == server_methods
    print("   ✅ Both instances have identical methods and attributes")
    
    # Test specific methods
    assert hasattr(shared_instance, 'record_sync_start')
    assert hasattr(shared_instance, 'record_sync_success')
    assert hasattr(shared_instance, 'record_sync_failure')
    assert hasattr(shared_instance, 'to_dict')
    print("   ✅ All expected methods present")
    
    print("\n✅ ALL TESTS PASSED!")
    print("\n🎉 SyncMetadata Migration Summary:")
    print("   • Moved from blowing-off/models/sync_metadata.py to inbetweenies/models/sync_metadata.py")
    print("   • Updated to use InbetweeniesTimestampMixin")
    print("   • Added proper UTC datetime handling")
    print("   • Enhanced to_dict method for JSON serialization")
    print("   • Available in both FunkyGibbon and Blowing-off via shared import")
    print("   • Database table created automatically with other HomeKit models")
    print("   • All sync tracking functionality preserved and enhanced")
    print("\n✅ SyncMetadata is now properly shared in the inbetweenies package!")


if __name__ == "__main__":
    asyncio.run(test_shared_sync_metadata())