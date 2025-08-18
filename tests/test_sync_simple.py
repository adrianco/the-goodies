#!/usr/bin/env python3
"""
Simple sync test to verify multi-client propagation.
"""

import sqlite3
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, UTC


def create_test_db(db_path: str, client_id: str):
    """Create a test database with initial data."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create basic tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            type TEXT,
            name TEXT,
            data TEXT,
            created_by TEXT,
            created_at TEXT,
            updated_at TEXT,
            sync_id TEXT,
            version INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Insert client metadata
    cursor.execute(
        "INSERT INTO sync_metadata (key, value) VALUES (?, ?)",
        ("client_id", client_id)
    )

    conn.commit()
    conn.close()
    return db_path


def add_entity(db_path: str, entity_id: str, name: str, client_id: str):
    """Add an entity to the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO entities
        (id, type, name, created_by, created_at, sync_id, version)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        entity_id,
        "test_entity",
        name,
        client_id,
        datetime.now(UTC).isoformat(),
        f"sync_{entity_id}",
        1
    ))

    conn.commit()
    conn.close()


def get_entities(db_path: str):
    """Get all entities from database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, created_by FROM entities")
    entities = cursor.fetchall()

    conn.close()
    return entities


def sync_databases(source_db: str, target_db: str):
    """Simple sync from source to target."""
    source_conn = sqlite3.connect(source_db)
    target_conn = sqlite3.connect(target_db)

    # Get entities from source
    source_cursor = source_conn.cursor()
    source_cursor.execute("SELECT * FROM entities")
    source_entities = source_cursor.fetchall()

    # Insert into target (simple merge)
    target_cursor = target_conn.cursor()
    for entity in source_entities:
        target_cursor.execute("""
            INSERT OR REPLACE INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, entity)

    target_conn.commit()
    source_conn.close()
    target_conn.close()


def run_multi_client_sync_test():
    """Run a simple multi-client sync test."""
    print("\n" + "="*60)
    print("SIMPLE MULTI-CLIENT SYNC TEST")
    print("="*60)

    # Create temp directories
    temp_dir = tempfile.mkdtemp(prefix="sync_test_")
    client_dbs = []

    try:
        # Create 3 client databases
        for i in range(3):
            db_path = Path(temp_dir) / f"client_{i}.db"
            create_test_db(str(db_path), f"client_{i}")
            client_dbs.append(str(db_path))
            print(f"Created database for client_{i}")

        print("\n--- Phase 1: Initial Data Creation ---")

        # Client 0 creates entities
        add_entity(client_dbs[0], "entity_1", "First Entity", "client_0")
        add_entity(client_dbs[0], "entity_2", "Second Entity", "client_0")
        print("Client 0 created 2 entities")

        # Client 1 creates different entities
        add_entity(client_dbs[1], "entity_3", "Third Entity", "client_1")
        print("Client 1 created 1 entity")

        # Client 2 creates entities
        add_entity(client_dbs[2], "entity_4", "Fourth Entity", "client_2")
        print("Client 2 created 1 entity")

        print("\n--- Phase 2: Initial State ---")
        for i, db in enumerate(client_dbs):
            entities = get_entities(db)
            print(f"Client {i} has {len(entities)} entities: {[e[1] for e in entities]}")

        print("\n--- Phase 3: Sync Propagation ---")

        # Sync Client 0 -> Client 1
        sync_databases(client_dbs[0], client_dbs[1])
        print("Synced: Client 0 -> Client 1")

        # Sync Client 1 -> Client 2
        sync_databases(client_dbs[1], client_dbs[2])
        print("Synced: Client 1 -> Client 2")

        # Sync Client 2 -> Client 0 (complete the circle)
        sync_databases(client_dbs[2], client_dbs[0])
        print("Synced: Client 2 -> Client 0")

        # Sync Client 0 -> Client 1 again (propagate all)
        sync_databases(client_dbs[0], client_dbs[1])
        print("Synced: Client 0 -> Client 1 (second pass)")

        print("\n--- Phase 4: Final State ---")
        all_entity_counts = []
        for i, db in enumerate(client_dbs):
            entities = get_entities(db)
            all_entity_counts.append(len(entities))
            print(f"Client {i} has {len(entities)} entities: {[e[1] for e in entities]}")

        print("\n--- Phase 5: Verification ---")

        # Check if all clients have the same number of entities
        if len(set(all_entity_counts)) == 1:
            print(f"✓ SUCCESS: All clients converged to {all_entity_counts[0]} entities")

            # Verify all clients have all entities
            expected_entities = {"entity_1", "entity_2", "entity_3", "entity_4"}
            all_have_all = True

            for i, db in enumerate(client_dbs):
                entities = get_entities(db)
                entity_ids = {e[0] for e in entities}

                if entity_ids == expected_entities:
                    print(f"✓ Client {i} has all expected entities")
                else:
                    missing = expected_entities - entity_ids
                    extra = entity_ids - expected_entities
                    print(f"✗ Client {i} missing: {missing}, extra: {extra}")
                    all_have_all = False

            return all_have_all
        else:
            print(f"✗ FAILURE: Clients have different entity counts: {all_entity_counts}")
            return False

    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print("\nTest cleanup completed")


def run_conflict_resolution_test():
    """Test conflict resolution during sync."""
    print("\n" + "="*60)
    print("CONFLICT RESOLUTION TEST")
    print("="*60)

    temp_dir = tempfile.mkdtemp(prefix="conflict_test_")

    try:
        # Create 2 client databases
        db1 = Path(temp_dir) / "client_1.db"
        db2 = Path(temp_dir) / "client_2.db"

        create_test_db(str(db1), "client_1")
        create_test_db(str(db2), "client_2")

        # Both clients create the same entity with different data
        add_entity(str(db1), "shared_entity", "Client 1 Version", "client_1")
        add_entity(str(db2), "shared_entity", "Client 2 Version", "client_2")

        print("Both clients created 'shared_entity' with different values")

        # Show initial state
        print("\nBefore sync:")
        print(f"Client 1: {get_entities(str(db1))}")
        print(f"Client 2: {get_entities(str(db2))}")

        # Sync (last write wins)
        sync_databases(str(db2), str(db1))  # Client 2 -> Client 1

        print("\nAfter sync (Client 2 -> Client 1):")
        entities_1 = get_entities(str(db1))
        print(f"Client 1: {entities_1}")

        # Both should have the same value now
        if entities_1[0][1] == "Client 2 Version":
            print("✓ Conflict resolved: Client 2 version won (last write)")
            return True
        else:
            print("✗ Unexpected conflict resolution")
            return False

    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    print("Running Sync Propagation Tests")
    print("="*60)

    # Run tests
    test1_passed = run_multi_client_sync_test()
    test2_passed = run_conflict_resolution_test()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Multi-Client Sync Test: {'PASSED' if test1_passed else 'FAILED'}")
    print(f"Conflict Resolution Test: {'PASSED' if test2_passed else 'FAILED'}")

    if test1_passed and test2_passed:
        print("\n✓ All sync tests passed!")
    else:
        print("\n✗ Some tests failed")
