"""
Unit tests for SQLite storage operations
"""
import pytest
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch


class TestSQLiteStorage:
    """Test SQLite storage implementation"""
    
    @pytest.mark.unit
    def test_initialize_schema(self, in_memory_db):
        """Test database schema initialization"""
        # Create tables
        in_memory_db.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                version_timestamp REAL NOT NULL,
                last_modified_by TEXT NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                
                CHECK (type IN ('home', 'room', 'device', 'user', 'automation', 'scene'))
            );
            
            CREATE TABLE IF NOT EXISTS relationships (
                id TEXT PRIMARY KEY,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                created_at REAL DEFAULT (julianday('now')),
                
                FOREIGN KEY (from_id) REFERENCES entities(id),
                FOREIGN KEY (to_id) REFERENCES entities(id),
                CHECK (type IN ('located_in', 'connects_to', 'controls', 'owned_by'))
            );
            
            CREATE INDEX idx_entities_type ON entities(type);
            CREATE INDEX idx_entities_timestamp ON entities(version_timestamp);
            CREATE INDEX idx_relationships_from ON relationships(from_id);
            CREATE INDEX idx_relationships_to ON relationships(to_id);
        """)
        
        # Verify tables exist
        cursor = in_memory_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        
        assert 'entities' in tables
        assert 'relationships' in tables
        
        # Verify indices exist
        cursor = in_memory_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indices = {row[0] for row in cursor.fetchall()}
        
        assert 'idx_entities_type' in indices
        assert 'idx_entities_timestamp' in indices
    
    @pytest.mark.unit
    def test_create_entity(self, in_memory_db, sample_entities):
        """Test entity creation"""
        # Initialize schema first
        in_memory_db.executescript("""
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                version_timestamp REAL NOT NULL,
                last_modified_by TEXT NOT NULL
            );
        """)
        
        # Insert entity
        entity = sample_entities[0]
        in_memory_db.execute(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entity['id'],
                entity['type'],
                str(entity['content']),
                entity['version_timestamp'].timestamp(),
                entity['last_modified_by']
            )
        )
        in_memory_db.commit()
        
        # Verify insertion
        cursor = in_memory_db.execute(
            "SELECT * FROM entities WHERE id = ?",
            (entity['id'],)
        )
        row = cursor.fetchone()
        
        assert row is not None
        assert row['id'] == entity['id']
        assert row['type'] == entity['type']
    
    @pytest.mark.unit
    def test_update_entity_version(self, in_memory_db):
        """Test entity update with version timestamp"""
        # Setup
        in_memory_db.executescript("""
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                version_timestamp REAL NOT NULL,
                last_modified_by TEXT NOT NULL
            );
        """)
        
        # Insert initial entity
        entity_id = "test-entity-1"
        old_timestamp = datetime.now(timezone.utc) - timedelta(minutes=5)
        
        in_memory_db.execute(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_id, "device", '{"state": "on"}', old_timestamp.timestamp(), "user1")
        )
        
        # Update entity
        new_timestamp = datetime.now(timezone.utc)
        in_memory_db.execute(
            """
            UPDATE entities 
            SET content = ?, version_timestamp = ?, last_modified_by = ?
            WHERE id = ? AND version_timestamp < ?
            """,
            ('{"state": "off"}', new_timestamp.timestamp(), "user2", 
             entity_id, new_timestamp.timestamp())
        )
        in_memory_db.commit()
        
        # Verify update
        cursor = in_memory_db.execute(
            "SELECT * FROM entities WHERE id = ?",
            (entity_id,)
        )
        row = cursor.fetchone()
        
        assert row['content'] == '{"state": "off"}'
        assert row['last_modified_by'] == "user2"
        assert row['version_timestamp'] > old_timestamp.timestamp()
    
    @pytest.mark.unit
    def test_batch_insert_entities(self, in_memory_db, sample_entities):
        """Test bulk entity insertion"""
        # Setup
        in_memory_db.executescript("""
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                version_timestamp REAL NOT NULL,
                last_modified_by TEXT NOT NULL
            );
        """)
        
        # Prepare batch data
        batch_data = [
            (
                e['id'], e['type'], str(e['content']),
                e['version_timestamp'].timestamp(), e['last_modified_by']
            )
            for e in sample_entities
        ]
        
        # Batch insert
        in_memory_db.executemany(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            batch_data
        )
        in_memory_db.commit()
        
        # Verify all inserted
        cursor = in_memory_db.execute("SELECT COUNT(*) as count FROM entities")
        count = cursor.fetchone()['count']
        
        assert count == len(sample_entities)
    
    @pytest.mark.unit
    def test_query_by_type(self, in_memory_db, home_graph_data):
        """Test querying entities by type"""
        # Setup and insert data
        in_memory_db.executescript("""
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                version_timestamp REAL NOT NULL,
                last_modified_by TEXT NOT NULL
            );
            CREATE INDEX idx_entities_type ON entities(type);
        """)
        
        # Insert all entities
        for entity in home_graph_data['all_entities']:
            in_memory_db.execute(
                """
                INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entity['id'], entity['type'], str(entity['content']),
                    entity['version_timestamp'].timestamp(), entity['last_modified_by']
                )
            )
        in_memory_db.commit()
        
        # Query devices
        cursor = in_memory_db.execute(
            "SELECT * FROM entities WHERE type = ?",
            ("device",)
        )
        devices = cursor.fetchall()
        
        assert len(devices) == len(home_graph_data['devices'])
        
        # Query rooms
        cursor = in_memory_db.execute(
            "SELECT * FROM entities WHERE type = ?",
            ("room",)
        )
        rooms = cursor.fetchall()
        
        assert len(rooms) == len(home_graph_data['rooms'])
    
    @pytest.mark.unit
    def test_delete_entity(self, in_memory_db):
        """Test entity deletion"""
        # Setup
        in_memory_db.executescript("""
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                version_timestamp REAL NOT NULL,
                last_modified_by TEXT NOT NULL
            );
        """)
        
        # Insert entity
        entity_id = "to-delete"
        in_memory_db.execute(
            """
            INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_id, "device", "{}", datetime.now(timezone.utc).timestamp(), "user")
        )
        in_memory_db.commit()
        
        # Delete entity
        in_memory_db.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        in_memory_db.commit()
        
        # Verify deletion
        cursor = in_memory_db.execute(
            "SELECT * FROM entities WHERE id = ?",
            (entity_id,)
        )
        
        assert cursor.fetchone() is None
    
    @pytest.mark.unit
    def test_relationship_operations(self, in_memory_db):
        """Test relationship CRUD operations"""
        # Setup
        in_memory_db.executescript("""
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                version_timestamp REAL NOT NULL,
                last_modified_by TEXT NOT NULL
            );
            
            CREATE TABLE relationships (
                id TEXT PRIMARY KEY,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                created_at REAL DEFAULT (julianday('now'))
            );
        """)
        
        # Create entities
        entities = [
            ("room-1", "room", '{"name": "Living Room"}'),
            ("device-1", "device", '{"name": "Light"}')
        ]
        
        for entity_id, entity_type, content in entities:
            in_memory_db.execute(
                """
                INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entity_id, entity_type, content, datetime.now(timezone.utc).timestamp(), "user")
            )
        
        # Create relationship
        in_memory_db.execute(
            """
            INSERT INTO relationships (id, from_id, to_id, type, properties)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("rel-1", "device-1", "room-1", "located_in", '{"floor": 1}')
        )
        in_memory_db.commit()
        
        # Query relationships
        cursor = in_memory_db.execute(
            "SELECT * FROM relationships WHERE from_id = ?",
            ("device-1",)
        )
        rel = cursor.fetchone()
        
        assert rel is not None
        assert rel['to_id'] == "room-1"
        assert rel['type'] == "located_in"
    
    @pytest.mark.unit
    def test_transaction_rollback(self, in_memory_db):
        """Test transaction rollback on error"""
        # Setup
        in_memory_db.executescript("""
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                version_timestamp REAL NOT NULL,
                last_modified_by TEXT NOT NULL
            );
        """)
        
        try:
            # Start transaction
            in_memory_db.execute("BEGIN")
            
            # Insert entity
            in_memory_db.execute(
                """
                INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("test-1", "device", "{}", datetime.now(timezone.utc).timestamp(), "user")
            )
            
            # Simulate error - duplicate primary key
            in_memory_db.execute(
                """
                INSERT INTO entities (id, type, content, version_timestamp, last_modified_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("test-1", "device", "{}", datetime.now(timezone.utc).timestamp(), "user")
            )
            
            in_memory_db.execute("COMMIT")
        except sqlite3.IntegrityError:
            in_memory_db.execute("ROLLBACK")
        
        # Verify no data was inserted
        cursor = in_memory_db.execute("SELECT COUNT(*) as count FROM entities")
        count = cursor.fetchone()['count']
        
        assert count == 0