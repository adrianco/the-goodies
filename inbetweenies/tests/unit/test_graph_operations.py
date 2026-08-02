"""Test GraphOperations (inbetweenies/graph/operations.py).

These are the concrete algorithms every backend inherits: versioned updates,
shortest-path, subgraph extraction and graph statistics. The house fixture's
map is in `memory_graph.build_house`.
"""

import pytest

from inbetweenies.models import EntityType, RelationshipType
from inbetweenies.tests.memory_graph import make_entity


class TestUpdateEntity:
    """update_entity creates a new immutable version rather than mutating."""

    async def test_creates_a_new_version_linked_to_its_parent(self, house):
        original = await house.get_entity("device-light")

        updated = await house.update_entity("device-light", {"name": "Ceiling Light"}, "alice")

        assert updated.id == "device-light"
        assert updated.name == "Ceiling Light"
        assert updated.version != original.version
        assert updated.parent_versions == ["v1"]
        assert updated.user_id == "alice"

    async def test_leaves_the_previous_version_intact(self, house):
        original = await house.get_entity("device-light")

        await house.update_entity("device-light", {"name": "Ceiling Light"}, "alice")

        assert original.name == "Kitchen Light"
        assert await house.get_entity("device-light", version="v1") is original

    async def test_new_version_becomes_the_current_one(self, house):
        updated = await house.update_entity("device-light", {"name": "Ceiling Light"}, "alice")

        assert await house.get_entity("device-light") is updated

    async def test_content_changes_are_merged_not_replaced(self, house):
        updated = await house.update_entity(
            "device-light", {"content": {"manufacturer": "OtherCorp", "watts": 9}}, "alice"
        )

        assert updated.content == {
            "manufacturer": "OtherCorp",  # overwritten
            "watts": 9,  # added
            "capabilities": ["on_off", "brightness"],  # preserved
            "services": ["lightbulb"],  # preserved
        }

    async def test_untouched_fields_carry_over(self, house):
        updated = await house.update_entity("device-light", {"name": "Ceiling Light"}, "alice")

        assert updated.entity_type == EntityType.DEVICE
        assert updated.content["manufacturer"] == "TestCorp"

    async def test_versions_accumulate_across_successive_updates(self, house):
        first = await house.update_entity("device-light", {"name": "Second"}, "alice")
        second = await house.update_entity("device-light", {"name": "Third"}, "bob")

        assert second.parent_versions == ["v1", first.version]

    async def test_unknown_entity_raises_value_error(self, house):
        with pytest.raises(ValueError, match="Entity no-such-entity not found"):
            await house.update_entity("no-such-entity", {"name": "x"}, "alice")

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG (entity.py:170-173, reached via operations.py:67): create_new_version "
            "writes the merged content back into the caller's `changes` dict "
            "(`changes[\"content\"] = merged_content`) instead of into a copy. The "
            "caller's argument is mutated, and MCPTools.update_entity_tool then reports "
            "the whole merged content as `changes_applied` (tools.py:475) rather than "
            "the delta that was requested."
        ),
    )
    async def test_does_not_mutate_the_callers_changes_dict(self, house):
        changes = {"content": {"watts": 9}}

        await house.update_entity("device-light", changes, "alice")

        assert changes == {"content": {"watts": 9}}


class TestFindPath:
    """find_path returns the shortest directed route, as entities."""

    async def test_finds_a_direct_edge(self, house):
        path = await house.find_path("room-kitchen", "home-1")

        assert [e.id for e in path] == ["room-kitchen", "home-1"]

    async def test_finds_a_multi_hop_route(self, house):
        path = await house.find_path("device-hub", "home-1")

        assert [e.id for e in path] == ["device-hub", "room-living", "home-1"]

    async def test_returns_entities_not_ids(self, house):
        path = await house.find_path("device-hub", "home-1")

        assert [e.name for e in path] == ["Smart Hub", "Living Room", "Test Home"]

    async def test_prefers_the_shortest_of_several_routes(self, house):
        # room-kitchen reaches home-1 directly and via the hallway; BFS must
        # return the two-node route.
        path = await house.find_path("room-kitchen", "home-1")

        assert len(path) == 2

    async def test_same_start_and_end_returns_that_entity_alone(self, house):
        path = await house.find_path("home-1", "home-1")

        assert [e.id for e in path] == ["home-1"]

    async def test_same_start_and_end_for_unknown_entity_returns_none(self, house):
        assert await house.find_path("no-such-entity", "no-such-entity") is None

    async def test_unreachable_target_returns_none(self, house):
        # home-1 has no outgoing edges.
        assert await house.find_path("home-1", "device-hub") is None

    async def test_edges_are_directed(self, house):
        assert await house.find_path("room-kitchen", "device-light") is None
        assert await house.find_path("device-light", "room-kitchen") is not None

    async def test_unknown_start_returns_none(self, house):
        assert await house.find_path("no-such-entity", "home-1") is None

    async def test_max_depth_bounds_the_number_of_hops(self, house):
        # device-hub -> room-living -> home-1 is two hops.
        assert await house.find_path("device-hub", "home-1", max_depth=1) is None
        assert await house.find_path("device-hub", "home-1", max_depth=2) is not None

    async def test_search_on_empty_graph_returns_none(self, empty_graph):
        assert await empty_graph.find_path("a", "b") is None


class TestGetSubgraph:
    """get_subgraph collects the neighbourhood around an entity."""

    async def test_depth_one_returns_immediate_neighbours(self, house):
        subgraph = await house.get_subgraph("device-light", depth=1)

        assert set(subgraph["entities"]) == {
            "device-light",  # the centre
            "room-kitchen",  # outgoing LOCATED_IN
            "manual-1",  # outgoing DOCUMENTED_BY
            "device-hub",  # incoming CONTROLS
            "automation-1",  # incoming AUTOMATES
            "procedure-1",  # incoming PROCEDURE_FOR
        }
        assert {r.id for r in subgraph["relationships"]} == {
            "rel-light-kitchen",
            "rel-light-manual",
            "rel-hub-light",
            "rel-auto-light",
            "rel-proc-light",
        }

    async def test_entities_are_keyed_by_id(self, house):
        subgraph = await house.get_subgraph("device-light", depth=1)

        assert subgraph["entities"]["device-light"].name == "Kitchen Light"

    async def test_follows_edges_in_both_directions(self, house):
        subgraph = await house.get_subgraph("home-1", depth=1)

        # home-1 has only incoming edges; a purely outgoing walk would return
        # nothing but the centre.
        assert set(subgraph["entities"]) == {
            "home-1",
            "room-kitchen",
            "room-hall",
            "room-living",
        }

    async def test_depth_two_expands_one_hop_further(self, house):
        near = await house.get_subgraph("device-hub", depth=1)
        far = await house.get_subgraph("device-hub", depth=2)

        assert "home-1" not in near["entities"]
        assert "home-1" in far["entities"]

    async def test_relationship_type_filter_narrows_the_edges(self, house):
        subgraph = await house.get_subgraph(
            "device-light", depth=1, rel_types=[RelationshipType.CONTROLS]
        )

        assert {r.id for r in subgraph["relationships"]} == {"rel-hub-light"}
        assert set(subgraph["entities"]) == {"device-light", "device-hub"}

    async def test_isolated_entity_returns_only_itself(self, house):
        subgraph = await house.get_subgraph("note-1", depth=1)

        assert set(subgraph["entities"]) == {"note-1"}
        assert subgraph["relationships"] == []

    async def test_unknown_centre_returns_an_empty_subgraph(self, house):
        assert await house.get_subgraph("no-such-entity") == {
            "entities": {},
            "relationships": [],
        }

    async def test_depth_zero_returns_only_the_centre(self, house):
        subgraph = await house.get_subgraph("device-light", depth=0)

        assert set(subgraph["entities"]) == {"device-light"}
        assert subgraph["relationships"] == []

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG (operations.py:167-168): rel_types is a List but only rel_types[0] is "
            "ever used -- every relationship type after the first is silently ignored, "
            "so a caller asking for two types gets the edges of one."
        ),
    )
    async def test_all_requested_relationship_types_are_included(self, house):
        subgraph = await house.get_subgraph(
            "device-light",
            depth=1,
            rel_types=[RelationshipType.CONTROLS, RelationshipType.AUTOMATES],
        )

        assert {r.id for r in subgraph["relationships"]} == {
            "rel-hub-light",
            "rel-auto-light",
        }

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG (operations.py:170-171): every edge between two entities that are both "
            "expanded is appended twice -- once as the first entity's outgoing edge and "
            "once as the second's incoming edge. The relationships list is not "
            "de-duplicated, so any caller counting edges over-counts at depth >= 2."
        ),
    )
    async def test_relationships_are_not_duplicated(self, house):
        subgraph = await house.get_subgraph("device-light", depth=2)

        ids = [r.id for r in subgraph["relationships"]]
        assert len(ids) == len(set(ids))


class TestGetStatistics:
    """Whole-graph summary counts."""

    async def test_counts_entities_by_type(self, house):
        stats = await house.get_statistics()

        assert stats["entity_types"] == {
            "home": 1,
            "room": 3,
            "device": 2,
            "procedure": 1,
            "manual": 1,
            "note": 1,
            "automation": 1,
        }
        assert stats["total_entities"] == 10

    async def test_counts_relationships_by_type(self, house):
        stats = await house.get_statistics()

        assert stats["relationship_types"] == {
            "located_in": 5,
            "controls": 1,
            "connects_to": 2,
            "automates": 1,
            "procedure_for": 1,
            "documented_by": 1,
        }
        assert stats["total_relationships"] == 11

    async def test_average_degree_is_two_edges_per_entity_rounded(self, house):
        stats = await house.get_statistics()

        # 2 * 11 edges / 10 entities.
        assert stats["average_degree"] == 2.2

    async def test_counts_entities_with_no_relationships(self, house):
        stats = await house.get_statistics()

        # note-1 is the only unconnected entity.
        assert stats["isolated_entities"] == 1

    async def test_only_the_latest_version_of_an_entity_is_counted(self, house):
        await house.update_entity("device-light", {"name": "Ceiling Light"}, "alice")

        stats = await house.get_statistics()

        assert stats["entity_types"]["device"] == 2
        assert stats["total_entities"] == 10

    async def test_empty_graph_reports_zeroes_without_dividing_by_zero(self, empty_graph):
        assert await empty_graph.get_statistics() == {
            "total_entities": 0,
            "total_relationships": 0,
            "entity_types": {},
            "relationship_types": {},
            "average_degree": 0,
            "isolated_entities": 0,
        }

    async def test_entity_types_with_no_entities_are_omitted(self, empty_graph):
        empty_graph.add_entity(make_entity("d", EntityType.DEVICE, "Only Device"))

        stats = await empty_graph.get_statistics()

        assert list(stats["entity_types"]) == ["device"]


class TestStoreAndFetch:
    """The primitives themselves, as exercised through the shared algorithms."""

    async def test_store_entity_makes_it_findable(self, empty_graph):
        entity = make_entity("new", EntityType.DEVICE, "New Device")

        await empty_graph.store_entity(entity)

        assert await empty_graph.get_entity("new") is entity

    async def test_get_entity_by_explicit_version(self, house):
        updated = await house.update_entity("device-light", {"name": "Ceiling Light"}, "alice")

        assert (await house.get_entity("device-light", version="v1")).name == "Kitchen Light"
        assert (await house.get_entity("device-light", version=updated.version)) is updated
        assert await house.get_entity("device-light", version="no-such-version") is None

    async def test_get_relationships_filters_combine(self, house):
        both = await house.get_relationships(
            from_id="device-light", rel_type=RelationshipType.DOCUMENTED_BY
        )
        wrong_type = await house.get_relationships(
            from_id="device-light", rel_type=RelationshipType.CONTROLS
        )

        assert [r.id for r in both] == ["rel-light-manual"]
        assert wrong_type == []

    async def test_get_entities_by_type_returns_only_that_type(self, house):
        rooms = await house.get_entities_by_type(EntityType.ROOM)

        assert {e.id for e in rooms} == {"room-kitchen", "room-hall", "room-living"}

    async def test_get_entities_by_type_with_no_matches(self, house):
        assert await house.get_entities_by_type(EntityType.SCHEDULE) == []
