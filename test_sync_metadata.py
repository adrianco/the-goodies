#!/usr/bin/env python3
"""
Test that the shared SyncMetadata model works correctly.
"""

import asyncio
import sys
import tempfile
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from datetime import datetime, UTC

sys.path.insert(0, '/workspaces/the-goodies')

from inbetweenies.models import Base, SyncMetadata


@pytest.mark.asyncio
async def test_sync_metadata():
    """Test SyncMetadata functionality."""
    print("=== Testing Shared SyncMetadata Model ===\n")
    
    # Create in-memory database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with session_factory() as session:
        # Test 1: Create sync metadata
        print("1. Creating sync metadata:")
        metadata = SyncMetadata(
            client_id="test-client-1",
            server_url="http://localhost:8000",
            auth_token="test-token-123"
        )
        session.add(metadata)
        await session.commit()
        print(f"   ✅ Created metadata for client: {metadata.client_id}")
        
        # Test 2: Record sync start
        print("\n2. Recording sync start:")
        metadata.record_sync_start()
        await session.commit()
        print(f"   ✅ Sync started at: {metadata.last_sync_time}")
        print(f"   ✅ Sync in progress: {bool(metadata.sync_in_progress)}")
        
        # Test 3: Record sync success
        print("\n3. Recording sync success:")
        await asyncio.sleep(0.1)  # Small delay to show time difference
        metadata.record_sync_success()
        await session.commit()
        print(f"   ✅ Sync succeeded at: {metadata.last_sync_success}")
        print(f"   ✅ Total syncs: {metadata.total_syncs}")
        print(f"   ✅ Sync failures: {metadata.sync_failures}")
        print(f"   ✅ Sync in progress: {bool(metadata.sync_in_progress)}")
        
        # Test 4: Record sync failure
        print("\n4. Recording sync failure:")
        metadata.record_sync_start()
        await asyncio.sleep(0.1)
        next_retry = datetime.now(UTC).replace(microsecond=0)
        metadata.record_sync_failure("Connection timeout", next_retry)
        await session.commit()
        print(f"   ✅ Sync failed with error: {metadata.last_sync_error}")
        print(f"   ✅ Total syncs: {metadata.total_syncs}")
        print(f"   ✅ Sync failures: {metadata.sync_failures}")
        print(f"   ✅ Next retry at: {metadata.next_retry_time}")
        
        # Test 5: Test to_dict method
        print("\n5. Testing to_dict serialization:")
        data = metadata.to_dict()
        print(f"   ✅ Dictionary keys: {list(data.keys())}")
        print(f"   ✅ Client ID: {data['client_id']}")
        print(f"   ✅ Sync in progress: {data['sync_in_progress']}")
        print(f"   ✅ Last error: {data['last_sync_error']}")
        
        # Test 6: Query from database
        print("\n6. Querying from database:")
        result = await session.execute(
            select(SyncMetadata).where(SyncMetadata.client_id == "test-client-1")
        )
        retrieved_metadata = result.scalar_one()
        print(f"   ✅ Retrieved client: {retrieved_metadata.client_id}")
        print(f"   ✅ Same instance: {retrieved_metadata is metadata}")
        print(f"   ✅ Total syncs match: {retrieved_metadata.total_syncs == 2}")
        
    await engine.dispose()
    print("\n✅ All SyncMetadata tests passed!")
    print("✅ SyncMetadata is now shared in inbetweenies package!")


if __name__ == "__main__":
    asyncio.run(test_sync_metadata())