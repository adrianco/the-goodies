"""
Performance benchmarks for 300 entity operations
"""
import pytest
import sqlite3
import time
from datetime import datetime, timedelta
import json
import random
from contextlib import contextmanager


@contextmanager
def measure_time(description="Operation"):
    """Context manager to measure execution time"""
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    duration = end - start
    print(f"\n{description}: {duration:.3f}s ({duration*1000:.1f}ms)")
    return duration


class TestPerformanceBenchmarks:
    """Performance tests for SQLite operations with 300 entities"""
    
    @pytest.fixture
    def optimized_db(self, tmp_path):
        """Create optimized SQLite database for performance testing"""
        db_path = tmp_path / "benchmark.db"
        conn = sqlite3.connect(str(db_path))
        
        # Performance optimizations
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory map
        
        # Create schema
        conn.executescript("""
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                version_timestamp REAL NOT NULL,
                last_modified_by TEXT NOT NULL,
                created_at REAL DEFAULT (julianday('now'))
            );
            
            CREATE INDEX idx_entities_type ON entities(type);
            CREATE INDEX idx_entities_timestamp ON entities(version_timestamp);
            CREATE INDEX idx_entities_modified_by ON entities(last_modified_by);
            
            CREATE TABLE relationships (
                id TEXT PRIMARY KEY,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                created_at REAL DEFAULT (julianday('now')),
                
                FOREIGN KEY (from_id) REFERENCES entities(id),
                FOREIGN KEY (to_id) REFERENCES entities(id)
            );
            
            CREATE INDEX idx_rel_from ON relationships(from_id);
            CREATE INDEX idx_rel_to ON relationships(to_id);
            CREATE INDEX idx_rel_type ON relationships(type);
        """)
        
        yield conn
        conn.close()
    
    @pytest.mark.performance
    def test_bulk_insert_300_entities(self, optimized_db):
        """Test inserting 300 entities in bulk"""
        entities = []
        base_time = datetime.utcnow()
        
        # Generate 300 entities
        for i in range(300):
            entity_type = "device" if i % 3 == 0 else "room" if i % 10 == 0 else "sensor"
            content = {
                "name": f"{entity_type.title()} {i}",
                "index": i,
                "state": random.choice(["on", "off", "idle"]),
                "metadata": {
                    "manufacturer": random.choice(["Philips", "Nest", "Ring"]),
                    "model": f"Model-{random.randint(100, 999)}",
                    "firmware": f"v{random.randint(1, 5)}.{random.randint(0, 9)}"
                }
            }
            
            entities.append((
                f"entity-{i}",
                entity_type,
                json.dumps(content),
                (base_time - timedelta(seconds=i)).timestamp(),
                f"user-{i % 5}"
            ))
        
        # Measure bulk insert time
        with measure_time("Bulk insert 300 entities"):
            optimized_db.executemany(
                """
                INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                entities
            )
            optimized_db.commit()
        
        # Verify
        cursor = optimized_db.execute("SELECT COUNT(*) FROM entities")
        count = cursor.fetchone()[0]
        assert count == 300
    
    @pytest.mark.performance
    def test_query_all_entities(self, optimized_db, large_dataset):
        """Test querying all 300 entities"""
        # First, populate database
        entities = []
        for entity in large_dataset:
            entities.append((
                entity['id'],
                entity['type'],
                json.dumps(entity['content']),
                entity['version_timestamp'].timestamp(),
                entity['last_modified_by']
            ))
        
        optimized_db.executemany(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            entities
        )
        optimized_db.commit()
        
        # Measure query time
        with measure_time("Query all 300 entities"):
            cursor = optimized_db.execute("SELECT * FROM entities")
            results = cursor.fetchall()
        
        assert len(results) == 300
    
    @pytest.mark.performance
    def test_filtered_queries(self, optimized_db, large_dataset):
        """Test various filtered queries on 300 entities"""
        # Populate database
        entities = []
        for entity in large_dataset:
            entities.append((
                entity['id'],
                entity['type'],
                json.dumps(entity['content']),
                entity['version_timestamp'].timestamp(),
                entity['last_modified_by']
            ))
        
        optimized_db.executemany(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            entities
        )
        optimized_db.commit()
        
        # Test 1: Filter by type
        with measure_time("Query devices (289 entities)"):
            cursor = optimized_db.execute(
                "SELECT * FROM entities WHERE type = ?",
                ("device",)
            )
            devices = cursor.fetchall()
        assert len(devices) == 289
        
        # Test 2: Filter by user
        with measure_time("Query by user (60 entities)"):
            cursor = optimized_db.execute(
                "SELECT * FROM entities WHERE last_modified_by = ?",
                ("user-0",)
            )
            user_entities = cursor.fetchall()
        assert len(user_entities) == 60  # ~1/5 of 300
        
        # Test 3: Time range query
        mid_time = large_dataset[150]['version_timestamp']
        with measure_time("Query by time range (150 entities)"):
            cursor = optimized_db.execute(
                "SELECT * FROM entities WHERE version_timestamp > ?",
                (mid_time.timestamp(),)
            )
            recent = cursor.fetchall()
        assert len(recent) == 150
    
    @pytest.mark.performance
    def test_update_100_entities(self, optimized_db, large_dataset):
        """Test updating 100 entities"""
        # Populate database
        entities = []
        for entity in large_dataset:
            entities.append((
                entity['id'],
                entity['type'],
                json.dumps(entity['content']),
                entity['version_timestamp'].timestamp(),
                entity['last_modified_by']
            ))
        
        optimized_db.executemany(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            entities
        )
        optimized_db.commit()
        
        # Prepare updates for first 100 entities
        update_time = datetime.utcnow()
        updates = []
        for i in range(100):
            entity = large_dataset[i]
            new_content = entity['content'].copy()
            new_content['updated'] = True
            new_content['update_count'] = i
            
            updates.append((
                json.dumps(new_content),
                update_time.timestamp(),
                "updater-user",
                entity['id']
            ))
        
        # Measure update time
        with measure_time("Update 100 entities"):
            optimized_db.executemany(
                """
                UPDATE entities 
                SET content = ?, version_timestamp = ?, last_modified_by = ?
                WHERE id = ?
                """,
                updates
            )
            optimized_db.commit()
        
        # Verify updates
        cursor = optimized_db.execute(
            "SELECT COUNT(*) FROM entities WHERE last_modified_by = ?",
            ("updater-user",)
        )
        count = cursor.fetchone()[0]
        assert count == 100
    
    @pytest.mark.performance
    def test_relationship_operations(self, optimized_db, large_dataset):
        """Test relationship creation and queries"""
        # First populate entities
        entities = []
        for entity in large_dataset:
            entities.append((
                entity['id'],
                entity['type'],
                json.dumps(entity['content']),
                entity['version_timestamp'].timestamp(),
                entity['last_modified_by']
            ))
        
        optimized_db.executemany(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            entities
        )
        
        # Create relationships - devices to rooms
        relationships = []
        devices = [e for e in large_dataset if e['type'] == 'device']
        rooms = [e for e in large_dataset if e['type'] == 'room']
        
        for i, device in enumerate(devices):
            room = rooms[i % len(rooms)]  # Distribute devices across rooms
            relationships.append((
                f"rel-{i}",
                device['id'],
                room['id'],
                "located_in",
                json.dumps({"assigned_at": datetime.utcnow().isoformat()})
            ))
        
        # Measure relationship insertion
        with measure_time(f"Insert {len(relationships)} relationships"):
            optimized_db.executemany(
                """
                INSERT INTO relationships (id, from_id, to_id, type, properties)
                VALUES (?, ?, ?, ?, ?)
                """,
                relationships
            )
            optimized_db.commit()
        
        # Test relationship queries
        with measure_time("Query devices in specific room"):
            cursor = optimized_db.execute(
                """
                SELECT e.* FROM entities e
                JOIN relationships r ON e.id = r.from_id
                WHERE r.to_id = ? AND r.type = ?
                """,
                (rooms[0]['id'], "located_in")
            )
            devices_in_room = cursor.fetchall()
        
        assert len(devices_in_room) > 0
    
    @pytest.mark.performance
    def test_concurrent_read_write(self, optimized_db, large_dataset):
        """Test concurrent read and write operations"""
        import threading
        import queue
        
        # Populate initial data
        entities = []
        for entity in large_dataset[:200]:  # Start with 200 entities
            entities.append((
                entity['id'],
                entity['type'],
                json.dumps(entity['content']),
                entity['version_timestamp'].timestamp(),
                entity['last_modified_by']
            ))
        
        optimized_db.executemany(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            entities
        )
        optimized_db.commit()
        
        results = queue.Queue()
        errors = queue.Queue()
        
        def reader_thread(thread_id):
            """Continuously read entities"""
            try:
                for _ in range(50):
                    cursor = optimized_db.execute("SELECT COUNT(*) FROM entities")
                    count = cursor.fetchone()[0]
                    results.put(('read', thread_id, count))
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.put(('read', thread_id, str(e)))
        
        def writer_thread(thread_id):
            """Add new entities"""
            try:
                for i in range(20):
                    entity_id = f"concurrent-{thread_id}-{i}"
                    optimized_db.execute(
                        """
                        INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            entity_id,
                            "device",
                            json.dumps({"thread": thread_id, "index": i}),
                            datetime.utcnow().timestamp(),
                            f"thread-{thread_id}"
                        )
                    )
                    optimized_db.commit()
                    results.put(('write', thread_id, entity_id))
                    time.sleep(0.002)
            except Exception as e:
                errors.put(('write', thread_id, str(e)))
        
        # Start concurrent threads
        threads = []
        
        with measure_time("Concurrent read/write operations"):
            # Start 3 readers and 2 writers
            for i in range(3):
                t = threading.Thread(target=reader_thread, args=(i,))
                threads.append(t)
                t.start()
            
            for i in range(2):
                t = threading.Thread(target=writer_thread, args=(i,))
                threads.append(t)
                t.start()
            
            # Wait for all threads
            for t in threads:
                t.join()
        
        # Check results
        assert errors.empty(), f"Errors occurred: {list(errors.queue)}"
        
        # Verify final count
        cursor = optimized_db.execute("SELECT COUNT(*) FROM entities")
        final_count = cursor.fetchone()[0]
        assert final_count == 240  # 200 initial + 40 written (2 threads × 20)
    
    @pytest.mark.performance
    def test_text_search_performance(self, optimized_db, large_dataset):
        """Test text search performance on entity content"""
        # Populate database
        entities = []
        for entity in large_dataset:
            entities.append((
                entity['id'],
                entity['type'],
                json.dumps(entity['content']),
                entity['version_timestamp'].timestamp(),
                entity['last_modified_by']
            ))
        
        optimized_db.executemany(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            entities
        )
        optimized_db.commit()
        
        # Test various search patterns
        search_patterns = [
            ("Light", "Simple word search"),
            ("%room_id%room-5%", "JSON field search"),
            ("%on%", "State search"),
            ("%sensor%", "Device type search")
        ]
        
        for pattern, description in search_patterns:
            with measure_time(f"{description} (pattern: {pattern})"):
                cursor = optimized_db.execute(
                    "SELECT * FROM entities WHERE content LIKE ?",
                    (pattern,)
                )
                results = cursor.fetchall()
            
            print(f"  Found {len(results)} matches")
    
    @pytest.mark.performance
    @pytest.mark.parametrize("batch_size", [10, 50, 100])
    def test_batch_size_impact(self, optimized_db, batch_size):
        """Test impact of different batch sizes on performance"""
        total_entities = 300
        batches = total_entities // batch_size
        
        all_entities = []
        for i in range(total_entities):
            all_entities.append((
                f"batch-test-{i}",
                "device",
                json.dumps({"index": i, "batch_size": batch_size}),
                datetime.utcnow().timestamp(),
                "batch-user"
            ))
        
        with measure_time(f"Insert {total_entities} entities in batches of {batch_size}"):
            for i in range(0, total_entities, batch_size):
                batch = all_entities[i:i + batch_size]
                optimized_db.executemany(
                    """
                    INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    batch
                )
                optimized_db.commit()
        
        # Verify
        cursor = optimized_db.execute(
            "SELECT COUNT(*) FROM entities WHERE last_modified_by = ?",
            ("batch-user",)
        )
        count = cursor.fetchone()[0]
        assert count == total_entities