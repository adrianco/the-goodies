"""The client's graph store belongs to its database file, not to a directory.

The store used to be `<db_path>.parent / ".blowing-off-graph"`, keyed on the
DIRECTORY holding the database. Two clients opened on different databases that
happened to share a directory therefore shared one entity set, one index, and
one set of pending (unpushed) marks — so one client could see another's
entities, and one client's push could clear another's pending flag. The same
shape made the test suite non-reentrant: every client built on a
NamedTemporaryFile landed in $TMPDIR/.blowing-off-graph, across tests and
across runs.

These tests pin the property that was missing: the store is a function of the
database file's identity. They also pin the migration policy for installs that
already have data in the old shared location — see
`blowingoff.client.migrate_legacy_graph_store`.

No server is involved: the store is chosen in __init__, before connect().
"""

import json
from pathlib import Path

import pytest

from blowingoff.client import (
    LEGACY_CLAIM_MARKER,
    LEGACY_GRAPH_DIR_NAME,
    BlowingOffClient,
    graph_storage_path,
    migrate_legacy_graph_store,
)
from inbetweenies.models import Entity, EntityType, SourceType


def _entity(name: str) -> Entity:
    return Entity(
        entity_type=EntityType.DEVICE,
        name=name,
        content={"marker": name},
        source_type=SourceType.MANUAL,
        user_id="test-user",
    )


def _legacy_store(directory: Path, entity_id: str = "legacy-entity") -> Path:
    """Write a plausible pre-fix shared store into `directory`."""
    legacy = directory / LEGACY_GRAPH_DIR_NAME
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "entities.json").write_text(json.dumps({
        entity_id: [{
            "id": entity_id,
            "version": "2026-01-01T00:00:00+00:00Z-000001-legacy",
            "entity_type": "device",
            "name": "Legacy Device",
            "content": {"origin": "legacy"},
            "source_type": "manual",
            "user_id": "legacy-user",
            "parent_versions": [],
            "created_at": None,
            "updated_at": None,
        }]
    }))
    (legacy / "relationships.json").write_text("[]")
    (legacy / "index.json").write_text(json.dumps(
        {"by_type": {"device": [entity_id]}, "by_room": {}}
    ))
    (legacy / "pending.json").write_text(json.dumps(
        {"entities": {entity_id: "create"}, "relationships": {}}
    ))
    return legacy


class TestStorePathIsDerivedFromTheDatabaseFile:
    """The store directory is a function of the db file, not its parent."""

    def test_two_databases_in_one_directory_get_two_stores(self, tmp_path):
        assert graph_storage_path(tmp_path / "a.db") != graph_storage_path(tmp_path / "b.db")

    def test_same_stem_different_suffix_still_differs(self, tmp_path):
        """The whole name is used, not the stem, which is not unique."""
        assert graph_storage_path(tmp_path / "home.db") != graph_storage_path(tmp_path / "home.sqlite")

    def test_store_sits_beside_its_database(self, tmp_path):
        store = graph_storage_path(tmp_path / "client.db")
        assert store.parent == tmp_path
        assert store.name == "client.db.graph"

    def test_the_old_shared_directory_is_never_used(self, tmp_path):
        client = BlowingOffClient(str(tmp_path / "client.db"))
        assert client.graph_storage_dir.name != LEGACY_GRAPH_DIR_NAME
        assert not (tmp_path / LEGACY_GRAPH_DIR_NAME).exists()


@pytest.mark.asyncio
class TestTwoClientsInOneDirectoryAreIndependent:
    """The regression: different databases, same directory, one graph."""

    @staticmethod
    def _pair(tmp_path):
        return (
            BlowingOffClient(str(tmp_path / "alice.db")),
            BlowingOffClient(str(tmp_path / "bob.db")),
        )

    async def test_stores_are_distinct_directories(self, tmp_path):
        alice, bob = self._pair(tmp_path)
        assert alice.graph_storage_dir != bob.graph_storage_dir

    async def test_neither_sees_the_others_entities(self, tmp_path):
        alice, bob = self._pair(tmp_path)

        stored = await alice.graph_operations.store_entity(_entity("alice-device"))

        assert await alice.graph_operations.get_entity(stored.id) is not None
        assert await bob.graph_operations.get_entity(stored.id) is None, (
            "bob's database is a different file; alice's entity must not be visible"
        )
        assert bob.graph_storage.get_entities_by_type(EntityType.DEVICE) == []

    async def test_pending_marks_are_independent(self, tmp_path):
        alice, bob = self._pair(tmp_path)

        await alice.graph_operations.store_entity(_entity("alice-device"))
        assert alice.pending_changes_count == 1
        assert bob.pending_changes_count == 0, (
            "bob has written nothing; he must have nothing pending"
        )

        # And a push acknowledged for bob must not clear alice's queue, which
        # is the production consequence: a client silently loses a change it
        # never pushed.
        await bob.graph_operations.store_entity(_entity("bob-device"))
        bob.graph_storage.clear_pending()

        assert bob.pending_changes_count == 0
        assert alice.pending_changes_count == 1, (
            "bob's sync must not clear alice's unpushed change"
        )

    async def test_clear_graph_data_only_clears_its_own_client(self, tmp_path):
        alice, bob = self._pair(tmp_path)

        alice_entity = await alice.graph_operations.store_entity(_entity("alice-device"))
        bob_entity = await bob.graph_operations.store_entity(_entity("bob-device"))

        alice.clear_graph_data()

        assert await alice.graph_operations.get_entity(alice_entity.id) is None
        assert await bob.graph_operations.get_entity(bob_entity.id) is not None
        assert bob.pending_changes_count == 1


@pytest.mark.asyncio
class TestStoreSurvivesRestart:
    """The existing persistence guarantee must not regress."""

    async def test_entities_and_pending_marks_survive_a_restart(self, tmp_path):
        db_path = str(tmp_path / "client.db")

        first = BlowingOffClient(db_path)
        stored = await first.graph_operations.store_entity(_entity("persisted"))
        assert first.pending_changes_count == 1

        reopened = BlowingOffClient(db_path)

        assert reopened.graph_storage_dir == first.graph_storage_dir
        found = await reopened.graph_operations.get_entity(stored.id)
        assert found is not None and found.name == "persisted"
        assert reopened.pending_changes_count == 1, (
            "an offline write must still be pushed after a restart"
        )

    async def test_a_neighbour_appearing_later_does_not_disturb_the_store(self, tmp_path):
        """A second database in the directory must not affect the first."""
        db_path = str(tmp_path / "client.db")
        first = BlowingOffClient(db_path)
        stored = await first.graph_operations.store_entity(_entity("persisted"))

        BlowingOffClient(str(tmp_path / "neighbour.db"))

        reopened = BlowingOffClient(db_path)
        assert await reopened.graph_operations.get_entity(stored.id) is not None
        assert reopened.pending_changes_count == 1


@pytest.mark.asyncio
class TestLegacyStoreMigration:
    """Existing installs keep their data — but never a stranger's."""

    async def test_lone_database_adopts_its_legacy_store(self, tmp_path):
        """Unambiguous ownership: the only database in the directory."""
        legacy = _legacy_store(tmp_path)
        (tmp_path / "client.db").write_bytes(b"")

        client = BlowingOffClient(str(tmp_path / "client.db"))

        assert client.graph_store_migration == "adopted"
        entity = await client.graph_operations.get_entity("legacy-entity")
        assert entity is not None and entity.name == "Legacy Device"
        assert client.pending_changes_count == 1, (
            "an unpushed change in the old store must still be pushed, not stranded"
        )
        # The original is copied, not moved: nothing is destroyed.
        assert (legacy / "entities.json").is_file()
        assert (legacy / LEGACY_CLAIM_MARKER).is_file()

    async def test_adoption_survives_the_next_start(self, tmp_path):
        (tmp_path / "client.db").write_bytes(b"")
        _legacy_store(tmp_path)

        BlowingOffClient(str(tmp_path / "client.db"))
        again = BlowingOffClient(str(tmp_path / "client.db"))

        assert again.graph_store_migration == "own-store-exists"
        assert await again.graph_operations.get_entity("legacy-entity") is not None

    async def test_shared_legacy_store_is_not_adopted_by_anyone(self, tmp_path, caplog):
        """The stranger case: the old directory may hold another client's graph."""
        legacy = _legacy_store(tmp_path)
        (tmp_path / "alice.db").write_bytes(b"")
        (tmp_path / "bob.db").write_bytes(b"")

        with caplog.at_level("WARNING"):
            alice = BlowingOffClient(str(tmp_path / "alice.db"))
            bob = BlowingOffClient(str(tmp_path / "bob.db"))

        assert alice.graph_store_migration == "declined-ambiguous"
        assert bob.graph_store_migration == "declined-ambiguous"
        assert await alice.graph_operations.get_entity("legacy-entity") is None
        assert await bob.graph_operations.get_entity("legacy-entity") is None
        assert alice.pending_changes_count == 0
        assert bob.pending_changes_count == 0

        # Declining is not deleting: the data is still there for a human.
        assert json.loads((legacy / "entities.json").read_text())
        assert not (legacy / LEGACY_CLAIM_MARKER).exists()
        assert "cannot be attributed" in caplog.text

    async def test_a_second_database_cannot_adopt_an_already_adopted_store(self, tmp_path, caplog):
        """Adoption is once-only, even if the neighbour arrives afterwards."""
        (tmp_path / "first.db").write_bytes(b"")
        _legacy_store(tmp_path)

        first = BlowingOffClient(str(tmp_path / "first.db"))
        assert first.graph_store_migration == "adopted"

        (tmp_path / "second.db").write_bytes(b"")
        with caplog.at_level("WARNING"):
            second = BlowingOffClient(str(tmp_path / "second.db"))

        assert second.graph_store_migration == "declined-already-claimed"
        assert await second.graph_operations.get_entity("legacy-entity") is None
        assert "already adopted" in caplog.text

    async def test_an_existing_store_wins_over_the_legacy_one(self, tmp_path):
        """A store of this database's own is authoritative; legacy is history."""
        db_path = str(tmp_path / "client.db")
        client = BlowingOffClient(db_path)
        own = await client.graph_operations.store_entity(_entity("mine"))

        _legacy_store(tmp_path)
        reopened = BlowingOffClient(db_path)

        assert reopened.graph_store_migration == "own-store-exists"
        assert await reopened.graph_operations.get_entity(own.id) is not None
        assert await reopened.graph_operations.get_entity("legacy-entity") is None

    async def test_a_deliberate_clear_is_not_undone_by_legacy_data(self, tmp_path):
        db_path = str(tmp_path / "client.db")
        client = BlowingOffClient(db_path)
        await client.graph_operations.store_entity(_entity("mine"))
        _legacy_store(tmp_path)
        client.clear_graph_data()

        reopened = BlowingOffClient(db_path)

        assert reopened.graph_store_migration == "own-store-exists"
        assert await reopened.graph_operations.get_entity("legacy-entity") is None

    def test_no_legacy_store_is_a_no_op(self, tmp_path):
        client = BlowingOffClient(str(tmp_path / "client.db"))
        assert client.graph_store_migration == "no-legacy-store"

    def test_an_empty_legacy_directory_is_not_adopted(self, tmp_path):
        (tmp_path / LEGACY_GRAPH_DIR_NAME).mkdir()
        client = BlowingOffClient(str(tmp_path / "client.db"))
        assert client.graph_store_migration == "legacy-store-empty"

    def test_migration_never_writes_to_the_legacy_directory_it_declines(self, tmp_path):
        legacy = _legacy_store(tmp_path)
        (tmp_path / "a.db").write_bytes(b"")
        (tmp_path / "b.db").write_bytes(b"")
        before = sorted(p.name for p in legacy.iterdir())

        migrate_legacy_graph_store(tmp_path / "a.db")

        assert sorted(p.name for p in legacy.iterdir()) == before
