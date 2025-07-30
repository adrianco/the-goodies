"""
FunkyGibbon - Test Configuration and Fixtures

DEVELOPMENT CONTEXT:
Created during the initial FunkyGibbon development phase when the project
pivoted from a complex multi-house system to a simplified single-house
deployment. This file provides the test infrastructure for all test modules.

FUNCTIONALITY:
- Provides pytest fixtures for in-memory and file-based SQLite databases
- Generates sample test data (entities, relationships, conflict scenarios)
- Configures custom pytest markers for test categorization
- Includes utilities for performance testing and timing
- Creates realistic home graph structures for integration tests

PURPOSE:
Centralizes test configuration to ensure consistent test environments
and provides reusable test data generators. Supports both unit tests
(fast, isolated) and integration tests (realistic scenarios).

KNOWN ISSUES:
- Some fixtures still reference old schema (needs updating)
- Performance fixtures could be more comprehensive
- Missing async fixtures for the new async codebase

REVISION HISTORY:
- 2025-07-28: Initial creation with basic fixtures
- 2025-07-28: Added performance testing fixtures (300 entities)
- 2025-07-28: Added conflict scenario generators
- 2025-07-28: Needs update for async SQLAlchemy models

DEPENDENCIES:
- pytest: Test framework
- sqlite3: Database for testing
- datetime/random: Test data generation

TODO:
- Update for async SQLAlchemy models
- Add fixtures for new entity types (EntityState, Event)
- Add fixtures for sync testing
"""
import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
import random
from typing import Dict, List, Any

# Import models once they're implemented
# from models import Entity, EntityType, Relationship, RelationshipType
# from storage import SQLiteStorage


@pytest.fixture
def in_memory_db():
    """Provide in-memory SQLite database connection"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def temp_db(tmp_path):
    """Provide temporary file-based SQLite database"""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn, db_path
    conn.close()


@pytest.fixture
def storage(in_memory_db):
    """Provide SQLiteStorage instance with in-memory database"""
    # Uncomment when SQLiteStorage is implemented
    # storage = SQLiteStorage(in_memory_db)
    # storage.initialize_schema()
    # return storage
    pass


@pytest.fixture
def sample_entities():
    """Generate sample entities for testing"""
    return [
        {
            "id": f"entity-{i}",
            "type": "device" if i % 3 == 0 else "room",
            "content": {
                "name": f"Entity {i}",
                "index": i,
                "state": "on" if i % 2 == 0 else "off"
            },
            "version_timestamp": datetime.now(timezone.utc) - timedelta(minutes=i),
            "last_modified_by": f"user-{i % 3}"
        }
        for i in range(10)
    ]


@pytest.fixture
def home_graph_data():
    """Generate a complete home graph structure"""
    home = {
        "id": "home-1",
        "type": "home",
        "content": {"name": "Test Home", "address": "123 Test St"},
        "version_timestamp": datetime.now(timezone.utc),
        "last_modified_by": "user-1"
    }
    
    rooms = [
        {
            "id": f"room-{i}",
            "type": "room",
            "content": {"name": room_name, "floor": 1},
            "version_timestamp": datetime.now(timezone.utc),
            "last_modified_by": "user-1"
        }
        for i, room_name in enumerate(["Living Room", "Kitchen", "Bedroom"])
    ]
    
    devices = []
    device_configs = [
        ("Smart Light", "room-0", "light"),
        ("Thermostat", "room-0", "thermostat"),
        ("Smart Fridge", "room-1", "appliance"),
        ("Smart TV", "room-2", "entertainment")
    ]
    
    for i, (name, room_id, device_type) in enumerate(device_configs):
        devices.append({
            "id": f"device-{i}",
            "type": "device",
            "content": {
                "name": name,
                "device_type": device_type,
                "state": "on",
                "room_id": room_id
            },
            "version_timestamp": datetime.now(timezone.utc),
            "last_modified_by": "user-1"
        })
    
    relationships = []
    
    # Connect rooms to home
    for room in rooms:
        relationships.append({
            "id": f"rel-room-{room['id']}",
            "from_id": room["id"],
            "to_id": home["id"],
            "type": "located_in",
            "created_at": datetime.now(timezone.utc)
        })
    
    # Connect devices to rooms
    for device in devices:
        room_id = device["content"]["room_id"]
        relationships.append({
            "id": f"rel-device-{device['id']}",
            "from_id": device["id"],
            "to_id": room_id,
            "type": "located_in",
            "created_at": datetime.now(timezone.utc)
        })
    
    return {
        "home": home,
        "rooms": rooms,
        "devices": devices,
        "relationships": relationships,
        "all_entities": [home] + rooms + devices
    }


@pytest.fixture
def performance_db(tmp_path):
    """SQLite database optimized for performance testing"""
    db_path = tmp_path / "performance.db"
    conn = sqlite3.connect(str(db_path))
    
    # Performance optimizations
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=30000000000")
    
    yield conn
    conn.close()


@pytest.fixture
def large_dataset():
    """Generate 300 entities for performance testing"""
    entities = []
    
    # Distribution: 1 home, 10 rooms, 289 devices
    # Home
    entities.append({
        "id": "home-main",
        "type": "home",
        "content": {"name": "Performance Test Home"},
        "version_timestamp": datetime.now(timezone.utc),
        "last_modified_by": "perf-user"
    })
    
    # Rooms
    room_names = ["Living Room", "Kitchen", "Bedroom", "Bathroom", "Office",
                  "Garage", "Basement", "Attic", "Garden", "Hallway"]
    
    for i, name in enumerate(room_names):
        entities.append({
            "id": f"room-{i}",
            "type": "room",
            "content": {"name": name, "floor": i // 5},
            "version_timestamp": datetime.now(timezone.utc) - timedelta(seconds=i),
            "last_modified_by": "perf-user"
        })
    
    # Devices (289 to reach 300 total)
    device_types = ["light", "switch", "sensor", "camera", "thermostat", 
                    "lock", "outlet", "appliance"]
    
    for i in range(289):
        room_idx = i % 10  # Distribute across rooms
        entities.append({
            "id": f"device-{i}",
            "type": "device",
            "content": {
                "name": f"{random.choice(device_types).title()} {i}",
                "device_type": random.choice(device_types),
                "room_id": f"room-{room_idx}",
                "state": random.choice(["on", "off", "idle"]),
                "battery": random.randint(0, 100) if i % 5 == 0 else None,
                "temperature": random.uniform(18.0, 25.0) if i % 10 == 0 else None
            },
            "version_timestamp": datetime.now(timezone.utc) - timedelta(seconds=i*10),
            "last_modified_by": f"user-{i % 5}"
        })
    
    return entities


@pytest.fixture
def conflict_scenarios():
    """Generate entities with conflicting updates for testing"""
    base_time = datetime.now(timezone.utc)
    entity_id = "conflict-entity-1"
    
    return [
        {
            "scenario": "simple_conflict",
            "updates": [
                {
                    "id": entity_id,
                    "content": {"state": "on", "updated_by": "device1"},
                    "version_timestamp": base_time,
                    "device": "device1"
                },
                {
                    "id": entity_id,
                    "content": {"state": "off", "updated_by": "device2"},
                    "version_timestamp": base_time + timedelta(seconds=1),
                    "device": "device2"
                }
            ],
            "expected_winner": "device2"
        },
        {
            "scenario": "concurrent_updates",
            "updates": [
                {
                    "id": entity_id,
                    "content": {"value": i},
                    "version_timestamp": base_time + timedelta(microseconds=i*100),
                    "device": f"device{i}"
                }
                for i in range(5)
            ],
            "expected_winner": "device4"
        },
        {
            "scenario": "clock_skew",
            "updates": [
                {
                    "id": entity_id,
                    "content": {"state": "on"},
                    "version_timestamp": base_time + timedelta(seconds=2),  # Future
                    "device": "device_with_fast_clock"
                },
                {
                    "id": entity_id,
                    "content": {"state": "off"},
                    "version_timestamp": base_time,  # Current
                    "device": "device_normal_clock"
                }
            ],
            "expected_winner": "device_with_fast_clock"
        }
    ]


# Pytest markers
def pytest_configure(config):
    """Register custom pytest markers"""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, isolated)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (may use real resources)"
    )
    config.addinivalue_line(
        "markers", "performance: Performance benchmarks"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take > 1s"
    )
    config.addinivalue_line(
        "markers", "conflict: Conflict resolution tests"
    )


# Test utilities
class TestTimer:
    """Context manager for timing test operations"""
    def __init__(self, name="Operation"):
        self.name = name
        self.start_time = None
        self.duration = None
    
    def __enter__(self):
        self.start_time = datetime.now(timezone.utc)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        print(f"\n{self.name} took {self.duration:.3f}s")


def generate_test_entity(entity_type="device", **kwargs):
    """Helper to generate test entities"""
    defaults = {
        "id": f"{entity_type}-{random.randint(1000, 9999)}",
        "type": entity_type,
        "content": {"name": f"Test {entity_type.title()}"},
        "version_timestamp": datetime.now(timezone.utc),
        "last_modified_by": "test-user"
    }
    defaults.update(kwargs)
    return defaults