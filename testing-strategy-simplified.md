# Smart Home Knowledge Graph - Simplified Testing Strategy

## Overview

This testing strategy is designed for the simplified smart home system with:
- 1 house, ~300 entities, few users
- SQLite database with last-write-wins conflict resolution
- Python implementation first, then Swift/WildThing
- Focus on performance and correctness

## Testing Philosophy

1. **Test-Driven Development (TDD)**: Write tests before implementation
2. **Pyramid Testing**: Many unit tests, fewer integration tests, minimal E2E tests
3. **Fast Feedback**: Tests should run quickly (<100ms for unit tests)
4. **Isolation**: Use fixtures and mocks for external dependencies
5. **Coverage Target**: >80% code coverage

## 1. Unit Testing Strategy

### 1.1 Core Models Testing

```python
# tests/unit/test_models.py
import pytest
from datetime import datetime
from models import Entity, EntityType, Relationship, RelationshipType

class TestEntity:
    """Test entity model with SQLite-compatible fields"""
    
    @pytest.fixture
    def sample_entity(self):
        """Provide a sample entity for testing"""
        return Entity(
            id="entity-123",
            type=EntityType.DEVICE,
            content={"name": "Smart Light", "state": "on"},
            version_timestamp=datetime.utcnow(),
            last_modified_by="user-1"
        )
    
    def test_entity_creation(self):
        """Test basic entity creation"""
        entity = Entity(
            type=EntityType.ROOM,
            content={"name": "Living Room"}
        )
        assert entity.id is not None
        assert entity.type == EntityType.ROOM
        assert entity.version_timestamp is not None
    
    def test_entity_update_version(self, sample_entity):
        """Test version update for last-write-wins"""
        old_timestamp = sample_entity.version_timestamp
        sample_entity.update_content({"state": "off"}, "user-2")
        
        assert sample_entity.version_timestamp > old_timestamp
        assert sample_entity.last_modified_by == "user-2"
    
    @pytest.mark.parametrize("entity_type", [
        EntityType.HOME, EntityType.ROOM, EntityType.DEVICE,
        EntityType.USER, EntityType.AUTOMATION, EntityType.SCENE
    ])
    def test_all_entity_types(self, entity_type):
        """Test all supported entity types"""
        entity = Entity(type=entity_type, content={})
        assert entity.type == entity_type
```

### 1.2 SQLite Storage Testing

```python
# tests/unit/test_storage.py
import pytest
import sqlite3
from storage import SQLiteStorage, ConflictResolution

class TestSQLiteStorage:
    """Test SQLite storage operations"""
    
    @pytest.fixture
    def db_connection(self):
        """In-memory SQLite database for testing"""
        conn = sqlite3.connect(":memory:")
        storage = SQLiteStorage(conn)
        storage.initialize_schema()
        yield conn
        conn.close()
    
    @pytest.fixture
    def storage(self, db_connection):
        """Storage instance with test database"""
        return SQLiteStorage(db_connection)
    
    def test_entity_crud_operations(self, storage):
        """Test Create, Read, Update, Delete operations"""
        # Create
        entity = Entity(type=EntityType.DEVICE, content={"name": "Test"})
        storage.create_entity(entity)
        
        # Read
        retrieved = storage.get_entity(entity.id)
        assert retrieved.id == entity.id
        assert retrieved.content == entity.content
        
        # Update
        entity.update_content({"name": "Updated"}, "user-1")
        storage.update_entity(entity)
        retrieved = storage.get_entity(entity.id)
        assert retrieved.content["name"] == "Updated"
        
        # Delete
        storage.delete_entity(entity.id)
        assert storage.get_entity(entity.id) is None
    
    def test_batch_operations(self, storage):
        """Test bulk insert/update for performance"""
        entities = [
            Entity(type=EntityType.DEVICE, content={"index": i})
            for i in range(100)
        ]
        
        # Batch insert
        storage.batch_insert_entities(entities)
        
        # Verify all inserted
        all_entities = storage.get_all_entities()
        assert len(all_entities) == 100
    
    def test_relationship_operations(self, storage):
        """Test relationship CRUD operations"""
        # Create entities
        room = Entity(type=EntityType.ROOM, content={"name": "Kitchen"})
        device = Entity(type=EntityType.DEVICE, content={"name": "Fridge"})
        storage.create_entity(room)
        storage.create_entity(device)
        
        # Create relationship
        rel = Relationship(
            from_id=device.id,
            to_id=room.id,
            type=RelationshipType.LOCATED_IN
        )
        storage.create_relationship(rel)
        
        # Query relationships
        device_rels = storage.get_relationships_from(device.id)
        assert len(device_rels) == 1
        assert device_rels[0].to_id == room.id
```

### 1.3 Conflict Resolution Testing

```python
# tests/unit/test_conflict_resolution.py
import pytest
from datetime import datetime, timedelta
from conflict_resolution import LastWriteWinsResolver

class TestLastWriteWins:
    """Test last-write-wins conflict resolution"""
    
    @pytest.fixture
    def resolver(self):
        return LastWriteWinsResolver()
    
    def test_newer_timestamp_wins(self, resolver):
        """Test that newer timestamp always wins"""
        old_entity = Entity(
            id="entity-1",
            type=EntityType.DEVICE,
            content={"state": "on"},
            version_timestamp=datetime.utcnow() - timedelta(minutes=5)
        )
        
        new_entity = Entity(
            id="entity-1",
            type=EntityType.DEVICE,
            content={"state": "off"},
            version_timestamp=datetime.utcnow()
        )
        
        winner = resolver.resolve(old_entity, new_entity)
        assert winner.content["state"] == "off"
        assert winner.version_timestamp == new_entity.version_timestamp
    
    def test_concurrent_updates(self, resolver):
        """Test handling of concurrent updates"""
        base_time = datetime.utcnow()
        
        updates = [
            Entity(id="e-1", content={"v": i}, version_timestamp=base_time + timedelta(microseconds=i))
            for i in range(10)
        ]
        
        # Last update should win
        winner = resolver.resolve_multiple(updates)
        assert winner.content["v"] == 9
    
    def test_clock_skew_handling(self, resolver):
        """Test handling of minor clock differences"""
        # Simulate clock skew between devices
        device1_time = datetime.utcnow()
        device2_time = device1_time + timedelta(seconds=2)  # 2 second skew
        
        entity1 = Entity(id="e-1", content={"from": "device1"}, version_timestamp=device1_time)
        entity2 = Entity(id="e-1", content={"from": "device2"}, version_timestamp=device2_time)
        
        winner = resolver.resolve(entity1, entity2)
        assert winner.content["from"] == "device2"
```

## 2. Integration Testing

### 2.1 Database Integration Tests

```python
# tests/integration/test_db_integration.py
import pytest
import sqlite3
from pathlib import Path
from storage import SQLiteStorage
from models import Entity, EntityType

class TestDatabaseIntegration:
    """Test real database operations"""
    
    @pytest.fixture
    def test_db_path(self, tmp_path):
        """Create temporary database file"""
        return tmp_path / "test.db"
    
    @pytest.fixture
    def storage(self, test_db_path):
        """Storage with file-based database"""
        conn = sqlite3.connect(test_db_path)
        storage = SQLiteStorage(conn)
        storage.initialize_schema()
        yield storage
        conn.close()
    
    def test_persistence_across_connections(self, test_db_path):
        """Test data persists across connections"""
        # First connection - write data
        conn1 = sqlite3.connect(test_db_path)
        storage1 = SQLiteStorage(conn1)
        storage1.initialize_schema()
        
        entity = Entity(type=EntityType.HOME, content={"name": "My Home"})
        storage1.create_entity(entity)
        entity_id = entity.id
        conn1.close()
        
        # Second connection - read data
        conn2 = sqlite3.connect(test_db_path)
        storage2 = SQLiteStorage(conn2)
        
        retrieved = storage2.get_entity(entity_id)
        assert retrieved is not None
        assert retrieved.content["name"] == "My Home"
        conn2.close()
    
    def test_concurrent_access(self, test_db_path):
        """Test concurrent database access"""
        # Enable WAL mode for better concurrency
        conn1 = sqlite3.connect(test_db_path)
        conn1.execute("PRAGMA journal_mode=WAL")
        conn2 = sqlite3.connect(test_db_path)
        
        storage1 = SQLiteStorage(conn1)
        storage2 = SQLiteStorage(conn2)
        storage1.initialize_schema()
        
        # Concurrent writes
        entity1 = Entity(type=EntityType.DEVICE, content={"conn": 1})
        entity2 = Entity(type=EntityType.DEVICE, content={"conn": 2})
        
        storage1.create_entity(entity1)
        storage2.create_entity(entity2)
        
        # Both should be visible
        all_entities = storage1.get_all_entities()
        assert len(all_entities) == 2
        
        conn1.close()
        conn2.close()
```

### 2.2 Mock Swift/WildThing Interface Tests

```python
# tests/integration/test_swift_interface.py
import pytest
from unittest.mock import Mock, patch
from interfaces import SwiftInterface, SyncProtocol

class TestSwiftInterface:
    """Test interface that will connect to Swift/WildThing"""
    
    @pytest.fixture
    def mock_swift_client(self):
        """Mock Swift client for testing"""
        client = Mock()
        client.sync = Mock(return_value={"status": "success", "entities": []})
        client.get_entity = Mock(return_value={"id": "123", "type": "device"})
        return client
    
    def test_sync_protocol_interface(self, mock_swift_client):
        """Test sync protocol with mocked Swift client"""
        interface = SwiftInterface(mock_swift_client)
        
        # Test sync request
        changes = [
            {"id": "e1", "operation": "create", "data": {"name": "Test"}}
        ]
        result = interface.sync(changes)
        
        assert result["status"] == "success"
        mock_swift_client.sync.assert_called_once_with(changes)
    
    def test_entity_operations_interface(self, mock_swift_client):
        """Test entity operations through interface"""
        interface = SwiftInterface(mock_swift_client)
        
        # Test get entity
        entity = interface.get_entity("123")
        assert entity["id"] == "123"
        mock_swift_client.get_entity.assert_called_once_with("123")
    
    @patch('interfaces.websocket')
    def test_realtime_sync_interface(self, mock_websocket):
        """Test WebSocket interface for real-time sync"""
        ws = Mock()
        mock_websocket.create_connection.return_value = ws
        
        interface = SwiftInterface(None)
        interface.connect_realtime("ws://localhost:8080")
        
        # Test sending updates
        interface.send_update({"id": "e1", "change": "update"})
        ws.send.assert_called_once()
```

## 3. Performance Testing

### 3.1 Entity Performance Tests

```python
# tests/performance/test_performance.py
import pytest
import time
from storage import SQLiteStorage
from models import Entity, EntityType

class TestPerformance:
    """Performance benchmarks for 300 entity target"""
    
    @pytest.fixture
    def storage_with_data(self, tmp_path):
        """Storage pre-populated with test data"""
        conn = sqlite3.connect(tmp_path / "perf.db")
        storage = SQLiteStorage(conn)
        storage.initialize_schema()
        
        # Create 300 entities
        entities = []
        for i in range(300):
            entity_type = EntityType.DEVICE if i % 3 == 0 else EntityType.ROOM
            entity = Entity(
                type=entity_type,
                content={
                    "name": f"Entity {i}",
                    "index": i,
                    "metadata": {"tags": ["tag1", "tag2"], "active": True}
                }
            )
            entities.append(entity)
        
        storage.batch_insert_entities(entities)
        yield storage
        conn.close()
    
    def test_bulk_insert_performance(self, storage):
        """Test inserting 300 entities performance"""
        entities = [
            Entity(type=EntityType.DEVICE, content={"index": i})
            for i in range(300)
        ]
        
        start_time = time.time()
        storage.batch_insert_entities(entities)
        duration = time.time() - start_time
        
        assert duration < 1.0  # Should complete in under 1 second
        print(f"Inserted 300 entities in {duration:.3f}s")
    
    def test_query_performance(self, storage_with_data):
        """Test querying performance with 300 entities"""
        # Test 1: Get all entities
        start_time = time.time()
        all_entities = storage_with_data.get_all_entities()
        duration = time.time() - start_time
        
        assert len(all_entities) == 300
        assert duration < 0.1  # Should complete in under 100ms
        print(f"Retrieved 300 entities in {duration:.3f}s")
        
        # Test 2: Filter by type
        start_time = time.time()
        devices = storage_with_data.get_entities_by_type(EntityType.DEVICE)
        duration = time.time() - start_time
        
        assert len(devices) == 100  # 1/3 are devices
        assert duration < 0.05  # Should complete in under 50ms
        print(f"Filtered 100 devices in {duration:.3f}s")
    
    def test_update_performance(self, storage_with_data):
        """Test update performance"""
        all_entities = storage_with_data.get_all_entities()
        
        # Update 100 entities
        entities_to_update = all_entities[:100]
        for entity in entities_to_update:
            entity.update_content({"updated": True}, "user-1")
        
        start_time = time.time()
        for entity in entities_to_update:
            storage_with_data.update_entity(entity)
        duration = time.time() - start_time
        
        assert duration < 0.5  # Should complete in under 500ms
        print(f"Updated 100 entities in {duration:.3f}s")
    
    def test_relationship_query_performance(self, storage_with_data):
        """Test relationship traversal performance"""
        # Create relationships
        entities = storage_with_data.get_all_entities()
        relationships = []
        
        # Create a connected graph
        for i in range(len(entities) - 1):
            rel = Relationship(
                from_id=entities[i].id,
                to_id=entities[i + 1].id,
                type=RelationshipType.CONNECTS_TO
            )
            relationships.append(rel)
        
        storage_with_data.batch_insert_relationships(relationships)
        
        # Test traversal
        start_time = time.time()
        # Find all devices in a specific room
        room = entities[0]  # Assume first is a room
        connected = storage_with_data.get_connected_entities(room.id, max_depth=3)
        duration = time.time() - start_time
        
        assert len(connected) > 0
        assert duration < 0.1  # Should complete in under 100ms
        print(f"Traversed relationships in {duration:.3f}s")
```

### 3.2 Concurrent Operation Tests

```python
# tests/performance/test_concurrency.py
import pytest
import threading
import time
from queue import Queue
from storage import SQLiteStorage

class TestConcurrency:
    """Test concurrent operations and conflict resolution"""
    
    def test_concurrent_writes(self, storage):
        """Test multiple threads writing simultaneously"""
        num_threads = 5
        entities_per_thread = 20
        results = Queue()
        
        def write_entities(thread_id):
            for i in range(entities_per_thread):
                entity = Entity(
                    type=EntityType.DEVICE,
                    content={"thread": thread_id, "index": i}
                )
                storage.create_entity(entity)
                results.put(entity.id)
        
        # Start threads
        threads = []
        start_time = time.time()
        
        for i in range(num_threads):
            t = threading.Thread(target=write_entities, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        duration = time.time() - start_time
        
        # Verify all entities created
        assert results.qsize() == num_threads * entities_per_thread
        all_entities = storage.get_all_entities()
        assert len(all_entities) == num_threads * entities_per_thread
        print(f"Concurrent writes completed in {duration:.3f}s")
    
    def test_read_write_concurrency(self, storage_with_data):
        """Test concurrent reads during writes"""
        read_results = Queue()
        write_results = Queue()
        
        def reader_thread():
            for _ in range(50):
                entities = storage_with_data.get_all_entities()
                read_results.put(len(entities))
                time.sleep(0.01)
        
        def writer_thread():
            for i in range(25):
                entity = Entity(
                    type=EntityType.DEVICE,
                    content={"new": True, "index": i}
                )
                storage_with_data.create_entity(entity)
                write_results.put(entity.id)
                time.sleep(0.02)
        
        # Start concurrent operations
        reader = threading.Thread(target=reader_thread)
        writer = threading.Thread(target=writer_thread)
        
        reader.start()
        writer.start()
        
        reader.join()
        writer.join()
        
        # Verify consistency
        assert write_results.qsize() == 25
        # Read counts should increase monotonically
        read_counts = list(read_results.queue)
        assert read_counts[-1] >= read_counts[0]
```

## 4. Test Fixtures and Utilities

### 4.1 Database Fixtures

```python
# tests/conftest.py
import pytest
import sqlite3
from pathlib import Path
from storage import SQLiteStorage
from models import Entity, EntityType, Relationship, RelationshipType

@pytest.fixture
def in_memory_storage():
    """Provide in-memory storage for fast tests"""
    conn = sqlite3.connect(":memory:")
    storage = SQLiteStorage(conn)
    storage.initialize_schema()
    yield storage
    conn.close()

@pytest.fixture
def sample_home_graph(in_memory_storage):
    """Create a sample home graph for testing"""
    # Create home
    home = Entity(type=EntityType.HOME, content={"name": "Test Home"})
    in_memory_storage.create_entity(home)
    
    # Create rooms
    rooms = []
    for room_name in ["Living Room", "Kitchen", "Bedroom"]:
        room = Entity(type=EntityType.ROOM, content={"name": room_name})
        in_memory_storage.create_entity(room)
        rooms.append(room)
        
        # Connect room to home
        rel = Relationship(
            from_id=room.id,
            to_id=home.id,
            type=RelationshipType.LOCATED_IN
        )
        in_memory_storage.create_relationship(rel)
    
    # Create devices
    devices = []
    device_configs = [
        ("Smart Light", rooms[0]),
        ("Thermostat", rooms[0]),
        ("Smart Fridge", rooms[1]),
        ("Smart TV", rooms[2])
    ]
    
    for device_name, room in device_configs:
        device = Entity(
            type=EntityType.DEVICE,
            content={"name": device_name, "state": "on"}
        )
        in_memory_storage.create_entity(device)
        devices.append(device)
        
        # Connect device to room
        rel = Relationship(
            from_id=device.id,
            to_id=room.id,
            type=RelationshipType.LOCATED_IN
        )
        in_memory_storage.create_relationship(rel)
    
    return {
        "home": home,
        "rooms": rooms,
        "devices": devices,
        "storage": in_memory_storage
    }

@pytest.fixture
def benchmark_storage(tmp_path):
    """Storage configured for benchmarking"""
    db_path = tmp_path / "benchmark.db"
    conn = sqlite3.connect(db_path)
    
    # Optimize for performance
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    
    storage = SQLiteStorage(conn)
    storage.initialize_schema()
    
    yield storage
    conn.close()
```

### 4.2 Test Data Generators

```python
# tests/utils/generators.py
import random
from datetime import datetime, timedelta
from models import Entity, EntityType, Relationship, RelationshipType

class TestDataGenerator:
    """Generate realistic test data"""
    
    @staticmethod
    def generate_entity(entity_type=None):
        """Generate a random entity"""
        if entity_type is None:
            entity_type = random.choice(list(EntityType))
        
        content_generators = {
            EntityType.HOME: lambda: {
                "name": f"Home {random.randint(1, 100)}",
                "address": f"{random.randint(1, 999)} Test St",
                "timezone": "UTC"
            },
            EntityType.ROOM: lambda: {
                "name": random.choice(["Kitchen", "Bedroom", "Living Room", "Bathroom"]),
                "floor": random.randint(1, 3),
                "area_sqft": random.randint(100, 500)
            },
            EntityType.DEVICE: lambda: {
                "name": random.choice(["Light", "Thermostat", "Camera", "Lock"]),
                "manufacturer": random.choice(["Philips", "Nest", "Ring", "August"]),
                "state": random.choice(["on", "off", "idle"]),
                "battery_level": random.randint(0, 100)
            }
        }
        
        content = content_generators.get(
            entity_type,
            lambda: {"name": "Generic Entity"}
        )()
        
        return Entity(
            type=entity_type,
            content=content,
            version_timestamp=datetime.utcnow() - timedelta(
                seconds=random.randint(0, 3600)
            )
        )
    
    @staticmethod
    def generate_home_graph(num_rooms=5, devices_per_room=3):
        """Generate a complete home graph"""
        entities = []
        relationships = []
        
        # Create home
        home = TestDataGenerator.generate_entity(EntityType.HOME)
        entities.append(home)
        
        # Create rooms
        for i in range(num_rooms):
            room = TestDataGenerator.generate_entity(EntityType.ROOM)
            entities.append(room)
            
            # Connect room to home
            rel = Relationship(
                from_id=room.id,
                to_id=home.id,
                type=RelationshipType.LOCATED_IN
            )
            relationships.append(rel)
            
            # Create devices in room
            for j in range(devices_per_room):
                device = TestDataGenerator.generate_entity(EntityType.DEVICE)
                entities.append(device)
                
                # Connect device to room
                rel = Relationship(
                    from_id=device.id,
                    to_id=room.id,
                    type=RelationshipType.LOCATED_IN
                )
                relationships.append(rel)
        
        return entities, relationships
```

## 5. Test Execution and CI/CD

### 5.1 pytest Configuration

```ini
# pytest.ini
[tool:pytest]
minversion = 6.0
addopts = 
    -ra
    --strict-markers
    --cov=src
    --cov-branch
    --cov-report=term-missing:skip-covered
    --cov-report=html
    --cov-report=xml
    --cov-fail-under=80
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (may use real resources)
    performance: Performance benchmarks
    slow: Tests that take > 1s

[coverage:run]
source = src
omit = 
    */tests/*
    */conftest.py
    */__init__.py

[coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
```

### 5.2 Test Execution Commands

```bash
# Run all tests
pytest

# Run only unit tests
pytest -m unit

# Run with coverage
pytest --cov=src --cov-report=html

# Run performance tests
pytest -m performance --benchmark-only

# Run specific test file
pytest tests/unit/test_models.py

# Run with verbose output
pytest -v

# Run in parallel (requires pytest-xdist)
pytest -n auto

# Run and stop on first failure
pytest -x

# Run only failed tests from last run
pytest --lf

# Generate HTML report
pytest --html=report.html --self-contained-html
```

### 5.3 GitHub Actions CI

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.9, 3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run linting
      run: |
        flake8 src tests
        black --check src tests
        mypy src
    
    - name: Run tests with coverage
      run: |
        pytest --cov=src --cov-report=xml --cov-report=term
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: true
    
    - name: Run performance benchmarks
      run: |
        pytest -m performance --benchmark-json=benchmark.json
    
    - name: Store benchmark results
      uses: benchmark-action/github-action-benchmark@v1
      with:
        tool: 'pytest'
        output-file-path: benchmark.json
        github-token: ${{ secrets.GITHUB_TOKEN }}
        auto-push: true
```

## 6. Test Best Practices

### 6.1 Test Structure
- **Arrange**: Set up test data and dependencies
- **Act**: Execute the code under test  
- **Assert**: Verify expected outcomes
- **Cleanup**: Handled by fixtures

### 6.2 Test Naming
- Use descriptive names: `test_entity_update_increments_version_timestamp`
- Include scenario: `test_concurrent_writes_with_conflict_resolution`
- Be specific: `test_bulk_insert_300_entities_under_1_second`

### 6.3 Test Data
- Use fixtures for reusable test data
- Keep test data minimal but realistic
- Use factories/generators for bulk data
- Clean up after tests (automatic with fixtures)

### 6.4 Assertions
- One logical assertion per test
- Use specific assertions (not just `assert True`)
- Include helpful error messages
- Test both positive and negative cases

## 7. Monitoring and Reporting

### 7.1 Coverage Goals
- Overall: >80% coverage
- Critical modules: >90% coverage
- New code: 100% coverage
- Branch coverage: >75%

### 7.2 Performance Targets
- Unit tests: <100ms each
- Integration tests: <1s each
- Full test suite: <30s
- 300 entity operations: <1s

### 7.3 Test Reports
- HTML coverage reports
- Performance benchmark trends
- Flaky test detection
- Test execution time tracking

## Conclusion

This testing strategy ensures the simplified smart home knowledge graph system is:
- **Correct**: Comprehensive unit and integration tests
- **Performant**: Meets 300 entity target with headroom
- **Reliable**: Last-write-wins conflict resolution tested
- **Maintainable**: >80% coverage with fast feedback

The focus on SQLite operations, conflict resolution, and performance testing provides confidence that the system will work reliably in production with the expected load.