# Testing and Validation Strategy for Homegraph Migration

## Overview
This document outlines the comprehensive testing and validation strategy for each phase of the homegraph migration. The goal is to ensure zero regression, maintain data integrity, and validate new functionality at each step.

## Testing Principles

1. **Test-First Development**: Write tests before implementation
2. **Continuous Validation**: Run tests on every commit
3. **Data Integrity**: Validate no data loss during migration
4. **Performance Benchmarking**: Track performance metrics
5. **User Acceptance**: Real-world testing scenarios

## Phase 2: Graph Operations Testing

### Unit Tests

#### Entity Model Tests
```python
# tests/unit/test_entity_model.py
import pytest
from funkygibbon.models import Entity, EntityType

class TestEntityModel:
    def test_entity_creation(self):
        """Test basic entity creation"""
        entity = Entity(
            entity_type=EntityType.DEVICE,
            name="Test Light",
            content={"brightness": 75},
            user_id="test-user"
        )
        assert entity.entity_type == EntityType.DEVICE
        assert entity.name == "Test Light"
        assert entity.version is not None
        
    def test_entity_versioning(self):
        """Test version generation is unique"""
        entity1 = Entity(entity_type=EntityType.ROOM, name="Room 1", user_id="user1")
        entity2 = Entity(entity_type=EntityType.ROOM, name="Room 2", user_id="user1")
        assert entity1.version != entity2.version
        
    def test_parent_version_tracking(self):
        """Test parent version linkage"""
        entity = Entity(
            entity_type=EntityType.DEVICE,
            name="Device",
            user_id="user1",
            parent_versions=["v1", "v2"]
        )
        assert len(entity.parent_versions) == 2
```

#### Relationship Model Tests
```python
# tests/unit/test_relationship_model.py
class TestRelationshipModel:
    def test_relationship_creation(self):
        """Test relationship between entities"""
        rel = EntityRelationship(
            from_entity_id="device1",
            to_entity_id="room1",
            relationship_type=RelationshipType.LOCATED_IN,
            user_id="test-user"
        )
        assert rel.relationship_type == RelationshipType.LOCATED_IN
        
    def test_relationship_properties(self):
        """Test relationship with properties"""
        rel = EntityRelationship(
            from_entity_id="door1",
            to_entity_id="room1",
            relationship_type=RelationshipType.CONNECTS_TO,
            properties={"direction": "north", "locked": False},
            user_id="test-user"
        )
        assert rel.properties["direction"] == "north"
```

### Integration Tests

#### HomeKit to Graph Migration
```python
# tests/integration/test_homekit_migration.py
import pytest
from funkygibbon.migrations import HomeKitToGraphMigrator

@pytest.mark.asyncio
async def test_homekit_migration(test_db):
    """Test migration of existing HomeKit data"""
    # Setup: Create HomeKit data
    await create_sample_homekit_data(test_db)
    
    # Execute migration
    migrator = HomeKitToGraphMigrator(test_db)
    result = await migrator.migrate()
    
    # Verify all data migrated
    assert result.homes_migrated == 1
    assert result.rooms_migrated == 5
    assert result.devices_migrated == 12
    assert result.relationships_created == 17
    
    # Verify data integrity
    entities = await test_db.get_entities(EntityType.DEVICE)
    for entity in entities:
        assert entity.source_type == SourceType.HOMEKIT
        assert "name" in entity.content
```

#### Graph Operations Tests
```python
# tests/integration/test_graph_operations.py
@pytest.mark.asyncio
async def test_path_finding(graph_with_data):
    """Test finding paths between rooms"""
    path = await graph_with_data.find_path("living-room", "bedroom")
    assert len(path) == 3  # living-room -> hallway -> bedroom
    assert path[0] == "living-room"
    assert path[-1] == "bedroom"
    
@pytest.mark.asyncio
async def test_device_discovery(graph_with_data):
    """Test finding devices in rooms"""
    devices = await graph_with_data.get_devices_in_room("living-room")
    assert len(devices) > 0
    assert all(d.entity_type == EntityType.DEVICE for d in devices)
```

### Performance Tests

#### Benchmark Suite
```python
# tests/performance/test_graph_performance.py
import time
import pytest

@pytest.mark.benchmark
async def test_large_graph_query_performance(large_graph):
    """Test query performance with 10k+ entities"""
    start = time.time()
    
    # Test various operations
    await large_graph.get_entities(EntityType.DEVICE)
    await large_graph.find_path("room-1", "room-1000")
    await large_graph.search("light")
    
    duration = time.time() - start
    assert duration < 1.0  # All operations under 1 second
    
@pytest.mark.benchmark
async def test_memory_usage(large_graph):
    """Test memory usage with large datasets"""
    import psutil
    process = psutil.Process()
    
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # Load 10k entities
    await large_graph.load_from_storage()
    
    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = final_memory - initial_memory
    
    assert memory_increase < 100  # Less than 100MB increase
```

## Phase 3: Inbetweenies Protocol Testing

### Protocol Tests

#### Version Negotiation
```python
# tests/unit/test_protocol_negotiation.py
def test_version_negotiation():
    """Test protocol version negotiation"""
    negotiator = ProtocolNegotiator()
    
    # V2 client with V2 server
    assert negotiator.negotiate_version(["v2", "v1"], ["v2", "v1"]) == "v2"
    
    # V1 client with V2 server
    assert negotiator.negotiate_version(["v1"], ["v2", "v1"]) == "v1"
    
    # Incompatible versions
    with pytest.raises(ProtocolError):
        negotiator.negotiate_version(["v3"], ["v1", "v2"])
```

#### Message Validation
```python
# tests/unit/test_message_validation.py
def test_sync_request_validation():
    """Test sync request message validation"""
    # Valid V2 request
    request = {
        "protocol_version": "inbetweenies-v2",
        "device_id": "device-123",
        "user_id": "user-123",
        "vector_clock": {"device-123": "v1"},
        "changes": []
    }
    assert validate_sync_request(request) is True
    
    # Missing required field
    invalid_request = request.copy()
    del invalid_request["device_id"]
    
    with pytest.raises(ValidationError):
        validate_sync_request(invalid_request)
```

### Sync Integration Tests

#### Multi-Client Sync
```python
# tests/integration/test_multi_client_sync.py
@pytest.mark.asyncio
async def test_multi_client_sync(sync_server, client1, client2):
    """Test sync between multiple clients"""
    # Client 1 creates entity
    entity = await client1.create_entity(
        entity_type=EntityType.DEVICE,
        name="Shared Light"
    )
    
    # Sync both clients
    await client1.sync()
    await client2.sync()
    
    # Verify entity appears on client 2
    client2_entity = await client2.get_entity(entity.id)
    assert client2_entity is not None
    assert client2_entity.name == "Shared Light"
```

#### Conflict Resolution
```python
# tests/integration/test_conflict_resolution.py
@pytest.mark.asyncio
async def test_concurrent_edit_conflict(sync_server, client1, client2):
    """Test conflict resolution for concurrent edits"""
    # Both clients have same entity
    entity_id = "shared-device"
    
    # Both edit offline
    await client1.update_entity(entity_id, {"brightness": 50})
    await client2.update_entity(entity_id, {"brightness": 75})
    
    # Sync both
    result1 = await client1.sync()
    result2 = await client2.sync()
    
    # Verify conflict was resolved
    assert len(result2.conflicts) == 1
    
    # Both should have same final state
    final1 = await client1.get_entity(entity_id)
    final2 = await client2.get_entity(entity_id)
    assert final1.version == final2.version
```

### Network Resilience Tests

```python
# tests/integration/test_network_resilience.py
@pytest.mark.asyncio
async def test_sync_retry_on_failure(flaky_network_client):
    """Test sync retry mechanism"""
    # Configure network to fail first 2 attempts
    flaky_network_client.fail_count = 2
    
    # Should succeed on 3rd attempt
    result = await flaky_network_client.sync()
    assert result.success is True
    assert flaky_network_client.attempt_count == 3
    
@pytest.mark.asyncio
async def test_partial_sync_recovery(client, sync_server):
    """Test recovery from partial sync"""
    # Simulate partial sync
    with sync_server.simulate_disconnect_after(5):
        try:
            await client.sync_full()
        except NetworkError:
            pass
    
    # Resume sync
    result = await client.sync_delta()
    assert result.resumed_from_partial is True
```

## Phase 4: Swift/WildThing Testing

### Swift Unit Tests

```swift
// Tests/WildThingTests/ModelTests.swift
class ModelTests: XCTestCase {
    func testEntityCoding() throws {
        let entity = Entity(
            entityType: .device,
            content: ["name": .string("Test")],
            userId: "test"
        )
        
        let encoder = JSONEncoder()
        let data = try encoder.encode(entity)
        
        let decoder = JSONDecoder()
        let decoded = try decoder.decode(Entity.self, from: data)
        
        XCTAssertEqual(entity.id, decoded.id)
        XCTAssertEqual(entity.entityType, decoded.entityType)
    }
}
```

### HomeKit Integration Tests

```swift
// Tests/WildThingHomeKitTests/ImportTests.swift
class HomeKitImportTests: XCTestCase {
    func testMockHomeKitImport() async throws {
        let storage = MockStorage()
        let importer = HomeKitImporter(storage: storage)
        
        // Use mock HomeKit data
        let mockHome = MockHMHome(name: "Test Home")
        mockHome.addRoom(MockHMRoom(name: "Living Room"))
        
        try await importer.import(homes: [mockHome])
        
        let entities = try await storage.getEntities(ofType: .home)
        XCTAssertEqual(entities.count, 1)
        XCTAssertEqual(entities[0].content["name"], .string("Test Home"))
    }
}
```

## MCP Server Testing

### Tool Testing Framework

```python
# tests/mcp/test_mcp_tools.py
class TestMCPTools:
    @pytest.fixture
    def mcp_client(self, mcp_server):
        """Create MCP client for testing"""
        return MCPTestClient(mcp_server)
    
    async def test_get_devices_in_room_tool(self, mcp_client, sample_data):
        """Test device query tool"""
        response = await mcp_client.call_tool(
            "get_devices_in_room",
            {"room_name": "Living Room"}
        )
        
        assert response.error is None
        assert "devices" in response.result
        assert len(response.result["devices"]) == 3
        
    async def test_invalid_tool_call(self, mcp_client):
        """Test error handling for invalid tool"""
        response = await mcp_client.call_tool(
            "non_existent_tool",
            {}
        )
        
        assert response.error is not None
        assert response.error.code == -32602
```

## End-to-End Testing

### Test Scenarios

1. **Fresh Installation Flow**
   - Install FunkyGibbon server
   - Set up Blowing-off client
   - Import HomeKit data
   - Verify all entities imported
   - Test basic queries

2. **Migration Flow**
   - Start with existing HomeKit data
   - Run migration scripts
   - Verify data integrity
   - Test new graph operations
   - Ensure backward compatibility

3. **Multi-Device Sync Flow**
   - Set up server with initial data
   - Connect iOS device (future)
   - Connect Python client
   - Make changes on each
   - Verify sync consistency

### Automated E2E Suite

```python
# tests/e2e/test_complete_flow.py
@pytest.mark.e2e
async def test_complete_setup_flow():
    """Test complete setup from scratch"""
    # 1. Start fresh server
    server = await start_funkygibbon_server(port=8000)
    
    # 2. Initialize client
    client = BlowingOffClient("http://localhost:8000")
    
    # 3. Create initial data
    home = await client.create_home("My Home")
    room = await client.create_room("Living Room", home.id)
    device = await client.create_device("Smart Light", room.id)
    
    # 4. Test graph operations
    devices = await client.get_devices_in_room("Living Room")
    assert len(devices) == 1
    assert devices[0].name == "Smart Light"
    
    # 5. Test MCP interface
    mcp_response = await client.mcp_call(
        "search_entities",
        {"query": "light"}
    )
    assert len(mcp_response["results"]) == 1
```

## Validation Criteria

### Data Integrity Validation

1. **No Data Loss**
   - Count entities before/after migration
   - Verify all fields preserved
   - Check relationship integrity

2. **Version Consistency**
   - All versions properly linked
   - No orphaned versions
   - Correct parent tracking

3. **Sync Integrity**
   - No duplicate entities
   - Consistent state across clients
   - Proper conflict resolution

### Performance Validation

1. **Response Times**
   - Graph queries < 10ms
   - Sync operations < 1s
   - MCP tools < 50ms

2. **Resource Usage**
   - Memory < 100MB for typical home
   - CPU usage reasonable
   - Efficient network usage

3. **Scalability**
   - Handle 10k+ entities
   - Support 100+ concurrent clients
   - Graceful degradation

## Test Automation

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - run: |
          pip install -r requirements-test.txt
          pytest tests/ --cov=funkygibbon --cov-report=xml
          
  test-swift:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3
      - run: |
          swift test --enable-test-discovery
          
  test-integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:14
    steps:
      - run: |
          docker-compose up -d
          pytest tests/integration/ -m integration
```

### Test Reports

1. **Coverage Reports**
   - Maintain >90% code coverage
   - Track coverage trends
   - Identify untested paths

2. **Performance Reports**
   - Track query times over commits
   - Memory usage trends
   - Identify regressions

3. **Compatibility Matrix**
   - Test across Python versions
   - Test across Swift versions
   - Test protocol compatibility

## User Acceptance Testing

### Beta Testing Program

1. **Phase 1: Internal Testing**
   - Development team usage
   - Dogfooding the system
   - Rapid iteration

2. **Phase 2: Alpha Users**
   - 5-10 technical users
   - Detailed feedback collection
   - Bug tracking

3. **Phase 3: Beta Release**
   - 50-100 users
   - Real-world scenarios
   - Performance monitoring

### Feedback Collection

```python
# funkygibbon/telemetry/feedback.py
class FeedbackCollector:
    """Collect anonymized usage feedback"""
    
    async def track_tool_usage(self, tool_name: str, duration: float):
        """Track which MCP tools are used"""
        
    async def track_query_patterns(self, query_type: str, result_count: int):
        """Track common query patterns"""
        
    async def report_error(self, error_type: str, context: dict):
        """Report errors for analysis"""
```

## Success Metrics

1. **Test Coverage**: >90% across all components
2. **Test Execution Time**: <5 minutes for full suite
3. **Defect Rate**: <0.1% in production
4. **Performance**: All benchmarks passing
5. **User Satisfaction**: >4.5/5 rating from beta users