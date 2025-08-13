#!/usr/bin/env python
"""Test graph operations work correctly"""

import asyncio
import sys
import pytest
import tempfile
sys.path.insert(0, '/workspaces/the-goodies')

from blowingoff.graph import LocalGraphStorage, LocalGraphOperations
from inbetweenies.models import Entity, EntityType, SourceType

@pytest.mark.asyncio
async def test_graph_ops():
    # Create a temporary directory for storage
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LocalGraphStorage(tmpdir)
        ops = LocalGraphOperations(storage)
        
        # Create a test entity
        entity = Entity(
            entity_type=EntityType.HOME,
            name="Test Home",
            content={"test": True},
            source_type=SourceType.MANUAL
        )
        
        # Store it
        stored = await ops.store_entity(entity)
        print(f"Stored entity: {stored.id}")
        
        # Get all entities by type
        print("\nTesting get_entities_by_type...")
        for et in EntityType:
            print(f"  EntityType.{et.name} = {et.value}")
            try:
                entities = await ops.get_entities_by_type(et)
                print(f"    Found {len(entities)} entities")
            except Exception as e:
                print(f"    Error: {e}")
        
        print("\nDone!")

if __name__ == "__main__":
    asyncio.run(test_graph_ops())