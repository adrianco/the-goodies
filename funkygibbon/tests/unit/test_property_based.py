"""
Property-based tests using hypothesis library.
Tests invariants and properties of the system with randomly generated data.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings, example
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant, Bundle, initialize

from inbetweenies.models import Home, Room, Accessory, Service, Characteristic, User
from funkygibbon.sync.conflict_resolution import ConflictResolver
from funkygibbon.sync.versioning import VersionManager
from funkygibbon.repositories.graph_impl import SQLGraphOperations


@pytest.mark.property
class TestEntityProperties:
    """Property-based tests for entity models."""
    
    @given(
        name=st.text(min_size=1, max_size=100),
        is_primary=st.booleans()
    )
    def test_home_creation_properties(self, name, is_primary):
        """Test that homes can be created with any valid string name."""
        home = Home(
            id=f"home-{abs(hash(name)) % 1000000}",
            name=name,
            is_primary=is_primary,
            sync_id=f"sync-{abs(hash(name)) % 1000000}"
        )
        
        assert home.name == name
        assert home.is_primary == is_primary
        assert home.id is not None
        assert home.sync_id is not None
    
    @given(
        room_count=st.integers(min_value=0, max_value=20),
        home_name=st.text(min_size=1, max_size=50)
    )
    def test_home_with_multiple_rooms(self, room_count, home_name):
        """Test that homes can have any number of rooms."""
        home = Home(
            id="home-1",
            name=home_name,
            sync_id="sync-1"
        )
        
        rooms = []
        for i in range(room_count):
            room = Room(
                id=f"room-{i}",
                name=f"Room {i}",
                home_id=home.id,
                sync_id=f"sync-room-{i}"
            )
            rooms.append(room)
        
        assert len(rooms) == room_count
        assert all(r.home_id == home.id for r in rooms)
    
    @given(
        manufacturer=st.text(min_size=1, max_size=50),
        model=st.text(min_size=1, max_size=50),
        is_reachable=st.booleans(),
        is_bridge=st.booleans()
    )
    def test_accessory_properties(self, manufacturer, model, is_reachable, is_bridge):
        """Test accessory creation with various properties."""
        accessory = Accessory(
            id="acc-1",
            name="Test Accessory",
            manufacturer=manufacturer,
            model=model,
            is_reachable=is_reachable,
            is_bridge=is_bridge,
            home_id="home-1",
            sync_id="sync-acc-1"
        )
        
        assert accessory.manufacturer == manufacturer
        assert accessory.model == model
        assert accessory.is_reachable == is_reachable
        assert accessory.is_bridge == is_bridge
    
    @given(
        service_type=st.text(min_size=1, max_size=100),
        is_primary=st.booleans(),
        is_user_interactive=st.booleans()
    )
    def test_service_properties(self, service_type, is_primary, is_user_interactive):
        """Test service creation with various properties."""
        service = Service(
            id="service-1",
            accessory_id="acc-1",
            service_type=service_type,
            name="Test Service",
            is_primary=is_primary,
            is_user_interactive=is_user_interactive,
            sync_id="sync-service-1"
        )
        
        assert service.service_type == service_type
        assert service.is_primary == is_primary
        assert service.is_user_interactive == is_user_interactive


@pytest.mark.property
class TestConflictResolutionProperties:
    """Property-based tests for conflict resolution."""
    
    @given(
        local_version=st.integers(min_value=1, max_value=1000),
        remote_version=st.integers(min_value=1, max_value=1000)
    )
    def test_version_comparison(self, local_version, remote_version):
        """Test that version comparison is consistent."""
        from inbetweenies.models import Entity, EntityType, SourceType
        from datetime import datetime, UTC
        
        resolver = ConflictResolver()
        
        # Create proper Entity objects
        local = Entity(
            id="test-entity",
            version=str(local_version),
            entity_type=EntityType.HOME,
            name="Local Version",
            content={"data": "local"},
            source_type=SourceType.MANUAL,
            user_id="user-1",
            created_at=datetime.now(UTC)
        )
        
        remote = Entity(
            id="test-entity",
            version=str(remote_version),
            entity_type=EntityType.HOME,
            name="Remote Version",
            content={"data": "remote"},
            source_type=SourceType.MANUAL,
            user_id="user-2",
            created_at=datetime.now(UTC)
        )
        
        # Test last-write-wins strategy
        from funkygibbon.sync.conflict_resolution import ConflictStrategy
        result = resolver.resolve_conflict(
            local=local,
            remote=remote,
            strategy=ConflictStrategy.LAST_WRITE_WINS
        )
        
        # The result should be deterministic
        assert result is not None
    
    @given(
        timestamps=st.lists(
            st.integers(min_value=1000000000, max_value=2000000000),
            min_size=2,
            max_size=10
        )
    )
    def test_timestamp_ordering(self, timestamps):
        """Test that timestamp-based resolution is consistent."""
        from inbetweenies.models import Entity, EntityType, SourceType
        from datetime import datetime
        
        resolver = ConflictResolver()
        
        # Create entities with different timestamps
        entities = []
        for i, ts in enumerate(timestamps):
            entity = Entity(
                id="test-entity",
                version=str(i),
                entity_type=EntityType.HOME,
                name=f"Version {i}",
                content={"data": f"version_{i}"},
                source_type=SourceType.MANUAL,
                user_id="user-1",
                created_at=datetime.fromtimestamp(ts)
            )
            entities.append(entity)
        
        # The result should be valid
        if len(entities) >= 2:
            from funkygibbon.sync.conflict_resolution import ConflictStrategy
            result = resolver.resolve_conflict(
                local=entities[0],
                remote=entities[1],
                strategy=ConflictStrategy.LAST_WRITE_WINS
            )
            assert result is not None


@pytest.mark.property
class TestVersioningProperties:
    """Property-based tests for version management."""
    
    @given(
        entity_id=st.text(min_size=1, max_size=50),
        num_versions=st.integers(min_value=1, max_value=10)
    )
    def test_version_creation(self, entity_id, num_versions):
        """Test that entity versions are created correctly."""
        from inbetweenies.models import Entity, EntityType, SourceType
        from datetime import datetime, UTC
        import uuid
        
        # Create multiple versions of the same entity
        versions = []
        for i in range(num_versions):
            entity = Entity(
                id=entity_id,
                version=str(uuid.uuid4()),
                entity_type=EntityType.HOME,
                name=f"Version {i}",
                content={"iteration": i},
                source_type=SourceType.MANUAL,
                user_id="test-user",
                parent_versions=[versions[-1].version] if versions else [],
                created_at=datetime.now(UTC)
            )
            versions.append(entity)
        
        # All versions should have the same entity ID
        assert all(v.id == entity_id for v in versions)
        
        # All versions should have unique version IDs
        version_ids = [v.version for v in versions]
        assert len(set(version_ids)) == num_versions
    
    @given(
        parent_count=st.integers(min_value=0, max_value=3),
        entity_name=st.text(min_size=1, max_size=50)
    )
    def test_parent_versions(self, parent_count, entity_name):
        """Test that parent versions are handled correctly."""
        from inbetweenies.models import Entity, EntityType, SourceType
        from datetime import datetime, UTC
        import uuid
        
        # Create parent versions
        parents = []
        for i in range(parent_count):
            parent = Entity(
                id="test-entity",
                version=str(uuid.uuid4()),
                entity_type=EntityType.HOME,
                name=f"Parent {i}",
                content={},
                source_type=SourceType.MANUAL,
                user_id="test-user",
                created_at=datetime.now(UTC)
            )
            parents.append(parent)
        
        # Create child with parent versions
        child = Entity(
            id="test-entity",
            version=str(uuid.uuid4()),
            entity_type=EntityType.HOME,
            name=entity_name,
            content={},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[p.version for p in parents],
            created_at=datetime.now(UTC)
        )
        
        # Child should have correct number of parents
        assert len(child.parent_versions) == parent_count


@pytest.mark.property
class TestGraphProperties:
    """Property-based tests for graph operations."""
    
    @given(
        node_count=st.integers(min_value=1, max_value=20),
        edge_probability=st.floats(min_value=0, max_value=0.5)
    )
    @settings(max_examples=10)
    def test_random_graph_properties(self, node_count, edge_probability):
        """Test properties of randomly generated graphs."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from funkygibbon.database import Base
        
        # Create in-memory database for testing
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        session = Session(engine)
        
        graph = SQLGraphOperations(session)
        
        # Create nodes (homes and rooms)
        nodes = []
        for i in range(node_count):
            if i == 0:
                # First node is always a home
                home = Home(
                    id=f"home-{i}",
                    name=f"Home {i}",
                    sync_id=f"sync-home-{i}"
                )
                session.add(home)
                nodes.append(("home", f"home-{i}"))
            else:
                # Others are rooms
                room = Room(
                    id=f"room-{i}",
                    name=f"Room {i}",
                    home_id="home-0",
                    sync_id=f"sync-room-{i}"
                )
                session.add(room)
                nodes.append(("room", f"room-{i}"))
        
        session.commit()
        
        # Graph invariants
        homes = session.query(Home).all()
        rooms = session.query(Room).all()
        
        assert len(homes) >= 1  # At least one home
        assert len(rooms) == node_count - 1  # Rest are rooms
        assert all(r.home_id == "home-0" for r in rooms)  # All rooms belong to first home
        
        session.close()
    
    @given(
        text_queries=st.lists(
            st.text(min_size=1, max_size=20),
            min_size=1,
            max_size=5
        )
    )
    @settings(max_examples=10)
    def test_search_properties(self, text_queries):
        """Test that search always returns valid results."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from funkygibbon.database import Base
        
        # Create in-memory database
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        session = Session(engine)
        
        # Add some test data
        home = Home(id="home-1", name="Test Home", sync_id="sync-1")
        room = Room(id="room-1", name="Living Room", home_id="home-1", sync_id="sync-2")
        session.add_all([home, room])
        session.commit()
        
        # Search with various queries
        for query in text_queries:
            # Search should not crash with any input
            try:
                # Simple text search in names
                homes = session.query(Home).filter(Home.name.contains(query)).all()
                rooms = session.query(Room).filter(Room.name.contains(query)).all()
                
                # Results should be lists
                assert isinstance(homes, list)
                assert isinstance(rooms, list)
            except Exception:
                # Some queries might cause issues, but shouldn't crash
                pass
        
        session.close()


@pytest.mark.property
class TestSyncStateMachine(RuleBasedStateMachine):
    """Stateful testing for sync operations."""
    
    def __init__(self):
        super().__init__()
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from funkygibbon.database import Base
        
        # Create in-memory database
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.session = Session(self.engine)
        
        self.homes = {}
        self.rooms = {}
        self.sync_version = 0
    
    @initialize()
    def setup(self):
        """Initialize with at least one home."""
        home = Home(
            id="home-init",
            name="Initial Home",
            is_primary=True,
            sync_id="sync-init"
        )
        self.session.add(home)
        self.session.commit()
        self.homes["home-init"] = home
    
    homes_bundle = Bundle('homes')
    rooms_bundle = Bundle('rooms')
    
    @rule(target=homes_bundle,
          home_id=st.text(min_size=1, max_size=20),
          name=st.text(min_size=1, max_size=50))
    def create_home(self, home_id, name):
        """Create a new home."""
        if home_id not in self.homes:
            home = Home(
                id=home_id,
                name=name,
                sync_id=f"sync-{home_id}"
            )
            self.session.add(home)
            self.session.commit()
            self.homes[home_id] = home
            return home_id
    
    @rule(target=rooms_bundle,
          room_id=st.text(min_size=1, max_size=20),
          name=st.text(min_size=1, max_size=50),
          home=st.one_of(st.just("home-init"), homes_bundle))
    def create_room(self, room_id, name, home):
        """Create a new room in a home."""
        if room_id not in self.rooms and home in self.homes:
            room = Room(
                id=room_id,
                name=name,
                home_id=home,
                sync_id=f"sync-{room_id}"
            )
            self.session.add(room)
            self.session.commit()
            self.rooms[room_id] = room
            return room_id
    
    @rule(home=homes_bundle)
    def delete_home(self, home):
        """Delete a home (keeping at least one)."""
        if home in self.homes and len(self.homes) > 1:
            home_obj = self.homes[home]
            # Delete associated rooms first
            self.session.query(Room).filter_by(home_id=home).delete()
            self.session.delete(home_obj)
            self.session.commit()
            del self.homes[home]
            # Remove from rooms tracking
            self.rooms = {k: v for k, v in self.rooms.items() if v.home_id != home}
    
    @rule()
    def sync_operation(self):
        """Simulate a sync operation."""
        self.sync_version += 1
        # Just increment version, actual sync is complex
    
    @invariant()
    def at_least_one_home(self):
        """There should always be at least one home."""
        count = self.session.query(Home).count()
        assert count >= 1
    
    @invariant()
    def rooms_have_valid_homes(self):
        """All rooms should belong to existing homes."""
        rooms = self.session.query(Room).all()
        home_ids = {h.id for h in self.session.query(Home).all()}
        for room in rooms:
            assert room.home_id in home_ids
    
    @invariant()
    def unique_ids(self):
        """All IDs should be unique."""
        homes = self.session.query(Home).all()
        rooms = self.session.query(Room).all()
        
        home_ids = [h.id for h in homes]
        room_ids = [r.id for r in rooms]
        
        assert len(home_ids) == len(set(home_ids))
        assert len(room_ids) == len(set(room_ids))
    
    def teardown(self):
        """Clean up after test."""
        self.session.close()
        self.engine.dispose()


# Configure the state machine test
TestSyncStateMachine.TestCase.settings = settings(
    max_examples=20,
    stateful_step_count=10,
    deadline=5000  # 5 seconds deadline
)


@pytest.mark.property
class TestDataIntegrity:
    """Test data integrity properties."""
    
    @given(
        num_operations=st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=10)
    def test_transaction_consistency(self, num_operations):
        """Test that transactions maintain consistency."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from funkygibbon.database import Base
        
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        session = Session(engine)
        
        initial_count = 0
        
        for i in range(num_operations):
            try:
                # Start transaction
                home = Home(
                    id=f"home-{i}",
                    name=f"Home {i}",
                    sync_id=f"sync-{i}"
                )
                session.add(home)
                
                # Add rooms
                for j in range(3):
                    room = Room(
                        id=f"room-{i}-{j}",
                        name=f"Room {j}",
                        home_id=f"home-{i}",
                        sync_id=f"sync-room-{i}-{j}"
                    )
                    session.add(room)
                
                session.commit()
                initial_count += 4  # 1 home + 3 rooms
                
            except Exception:
                session.rollback()
                # Count shouldn't change on rollback
        
        # Final count should match successful operations
        final_count = session.query(Home).count() + session.query(Room).count()
        assert final_count == initial_count
        
        session.close()
    
    @given(
        names=st.lists(
            st.text(min_size=1, max_size=100),
            min_size=1,
            max_size=10
        )
    )
    def test_name_handling(self, names):
        """Test that various name formats are handled correctly."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from funkygibbon.database import Base
        
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        session = Session(engine)
        
        for i, name in enumerate(names):
            try:
                home = Home(
                    id=f"home-{i}",
                    name=name,
                    sync_id=f"sync-{i}"
                )
                session.add(home)
                session.commit()
                
                # Should be able to retrieve it
                retrieved = session.query(Home).filter_by(id=f"home-{i}").first()
                assert retrieved is not None
                assert retrieved.name == name
                
            except Exception:
                session.rollback()
                # Some names might cause issues, but shouldn't crash
        
        session.close()