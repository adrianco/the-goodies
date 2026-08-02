"""Test GraphTraversal algorithms (inbetweenies/graph/traversal.py).

Traversal follows *outgoing* edges (``from`` -> ``to``) except for
``get_ancestors``, which follows incoming ones. The house fixture's edges are
laid out in `memory_graph.build_house`; the ids below refer to it.
"""

import pytest

from inbetweenies.models import EntityType, RelationshipType
from inbetweenies.tests.memory_graph import InMemoryGraph, make_entity


@pytest.fixture
def cycle_graph():
    """a -> b -> c -> a, all CONTROLS edges, plus an unrelated LOCATED_IN edge."""
    graph = InMemoryGraph()
    for node in ("a", "b", "c"):
        graph.add_entity(make_entity(node, EntityType.DEVICE, f"Device {node.upper()}"))
    graph.add_entity(make_entity("room", EntityType.ROOM, "Room"))
    graph.connect("ab", "a", "b", RelationshipType.CONTROLS)
    graph.connect("bc", "b", "c", RelationshipType.CONTROLS)
    graph.connect("ca", "c", "a", RelationshipType.CONTROLS)
    graph.connect("a-room", "a", "room", RelationshipType.LOCATED_IN)
    return graph


@pytest.fixture
def control_chain():
    """c1 CONTROLS c2 CONTROLS c3 -- a strictly hierarchical parent->child chain."""
    graph = InMemoryGraph()
    for node in ("c1", "c2", "c3"):
        graph.add_entity(make_entity(node, EntityType.DEVICE, f"Device {node}"))
    graph.connect("c1-c2", "c1", "c2", RelationshipType.CONTROLS)
    graph.connect("c2-c3", "c2", "c3", RelationshipType.CONTROLS)
    return graph


class TestBFS:
    """Breadth-first traversal."""

    async def test_bfs_visits_in_breadth_first_order(self, house):
        visited = await house.bfs("device-hub")

        # depth 0: hub; depth 1: living room and the light (edge insertion
        # order); depth 2: home, kitchen, manual; depth 3: hallway.
        assert [e.id for e in visited] == [
            "device-hub",
            "room-living",
            "device-light",
            "home-1",
            "room-kitchen",
            "manual-1",
            "room-hall",
        ]

    async def test_bfs_returns_entity_objects_not_ids(self, house):
        visited = await house.bfs("device-hub")

        assert visited[0].name == "Smart Hub"
        assert visited[0].entity_type == EntityType.DEVICE

    async def test_bfs_max_depth_zero_returns_only_start(self, house):
        visited = await house.bfs("device-hub", max_depth=0)

        assert [e.id for e in visited] == ["device-hub"]

    async def test_bfs_max_depth_one_stops_at_direct_neighbours(self, house):
        visited = await house.bfs("device-hub", max_depth=1)

        assert [e.id for e in visited] == ["device-hub", "room-living", "device-light"]

    async def test_bfs_filters_by_relationship_type(self, house):
        visited = await house.bfs("room-kitchen", rel_types=[RelationshipType.CONNECTS_TO])

        # LOCATED_IN edges to home-1 must not be followed.
        assert [e.id for e in visited] == ["room-kitchen", "room-hall", "room-living"]

    async def test_bfs_visit_fn_receives_entity_and_depth(self, house):
        seen = []

        await house.bfs("device-hub", visit_fn=lambda entity, depth: seen.append((entity.id, depth)) is None)

        assert seen == [
            ("device-hub", 0),
            ("room-living", 1),
            ("device-light", 1),
            ("home-1", 2),
            ("room-kitchen", 2),
            ("manual-1", 2),
            ("room-hall", 3),
        ]

    async def test_bfs_visit_fn_returning_false_stops_traversal(self, house):
        def stop_at_light(entity, depth):
            return entity.id != "device-light"

        visited = await house.bfs("device-hub", visit_fn=stop_at_light)

        # The entity that triggered the stop is included; nothing after it is.
        assert [e.id for e in visited] == ["device-hub", "room-living", "device-light"]
        assert "manual-1" not in [e.id for e in visited]

    async def test_bfs_unknown_start_returns_empty(self, house):
        assert await house.bfs("does-not-exist") == []

    async def test_bfs_on_empty_graph_returns_empty(self, empty_graph):
        assert await empty_graph.bfs("anything") == []

    async def test_bfs_terminates_on_cycle_and_visits_each_node_once(self, cycle_graph):
        visited = await cycle_graph.bfs("a", rel_types=[RelationshipType.CONTROLS])

        ids = [e.id for e in visited]
        assert ids == ["a", "b", "c"]
        assert len(ids) == len(set(ids))

    async def test_bfs_deduplicates_a_node_reachable_by_two_routes(self):
        # a -> b -> d and a -> c -> d: d is queued twice (once from b, once from
        # c, before either pop) and must still be reported exactly once.
        graph = InMemoryGraph()
        for node in ("a", "b", "c", "d"):
            graph.add_entity(make_entity(node, EntityType.DEVICE, node.upper()))
        graph.connect("ab", "a", "b", RelationshipType.CONTROLS)
        graph.connect("ac", "a", "c", RelationshipType.CONTROLS)
        graph.connect("bd", "b", "d", RelationshipType.CONTROLS)
        graph.connect("cd", "c", "d", RelationshipType.CONTROLS)

        visited = await graph.bfs("a")

        assert [e.id for e in visited] == ["a", "b", "c", "d"]

    async def test_bfs_skips_dangling_relationship_targets(self, house):
        # An edge that points at an id with no entity behind it must not crash
        # or appear in the result.
        house.connect("dangling", "device-hub", "ghost-entity", RelationshipType.CONTROLS)

        visited = await house.bfs("device-hub")

        assert "ghost-entity" not in [e.id for e in visited]


class TestDFS:
    """Depth-first traversal."""

    async def test_dfs_goes_deep_before_wide(self, house):
        visited = await house.dfs("device-hub")

        # Follows the first edge to the bottom (living room -> home) before
        # taking the hub's second edge.
        assert [e.id for e in visited] == [
            "device-hub",
            "room-living",
            "home-1",
            "device-light",
            "room-kitchen",
            "room-hall",
            "manual-1",
        ]

    async def test_dfs_differs_from_bfs_order(self, house):
        depth_first = [e.id for e in await house.dfs("device-hub")]
        breadth_first = [e.id for e in await house.bfs("device-hub")]

        assert depth_first != breadth_first
        assert set(depth_first) == set(breadth_first)

    async def test_dfs_max_depth_limits_descent(self, house):
        visited = await house.dfs("device-hub", max_depth=1)

        assert [e.id for e in visited] == ["device-hub", "room-living", "device-light"]

    async def test_dfs_visit_fn_returning_false_aborts_whole_traversal(self, house):
        def stop_at_living_room(entity, depth):
            return entity.id != "room-living"

        visited = await house.dfs("device-hub", visit_fn=stop_at_living_room)

        # Unlike a per-branch prune, a False return unwinds the entire search:
        # the hub's second branch (device-light) is never taken.
        assert [e.id for e in visited] == ["device-hub", "room-living"]

    async def test_dfs_filters_by_relationship_type(self, house):
        visited = await house.dfs("room-kitchen", rel_types=[RelationshipType.CONNECTS_TO])

        assert [e.id for e in visited] == ["room-kitchen", "room-hall", "room-living"]

    async def test_dfs_unknown_start_returns_empty(self, house):
        assert await house.dfs("does-not-exist") == []

    async def test_dfs_terminates_on_cycle(self, cycle_graph):
        visited = await cycle_graph.dfs("a", rel_types=[RelationshipType.CONTROLS])

        assert [e.id for e in visited] == ["a", "b", "c"]


class TestFindAllPaths:
    """find_all_paths returns every acyclic route between two entities."""

    async def test_finds_every_distinct_route(self, house):
        paths = await house.find_all_paths("room-kitchen", "home-1")

        assert paths == [
            ["room-kitchen", "home-1"],
            ["room-kitchen", "room-hall", "home-1"],
            ["room-kitchen", "room-hall", "room-living", "home-1"],
        ]

    async def test_paths_are_lists_of_ids_starting_at_start_and_ending_at_end(self, house):
        paths = await house.find_all_paths("device-hub", "home-1")

        assert paths == [
            ["device-hub", "room-living", "home-1"],
            ["device-hub", "device-light", "room-kitchen", "home-1"],
            ["device-hub", "device-light", "room-kitchen", "room-hall", "home-1"],
        ]
        for path in paths:
            assert path[0] == "device-hub"
            assert path[-1] == "home-1"

    async def test_max_length_bounds_the_number_of_nodes_in_a_path(self, house):
        # max_length is counted in *nodes*, so 2 admits only the direct edge.
        paths = await house.find_all_paths("room-kitchen", "home-1", max_length=2)

        assert paths == [["room-kitchen", "home-1"]]

        paths = await house.find_all_paths("room-kitchen", "home-1", max_length=3)
        assert paths == [
            ["room-kitchen", "home-1"],
            ["room-kitchen", "room-hall", "home-1"],
        ]

    async def test_default_max_length_drops_longer_routes(self, house):
        # hub -> light -> kitchen -> hall -> living -> home is six nodes, one
        # more than the default max_length of 5, so it is not reported...
        default_paths = await house.find_all_paths("device-hub", "home-1")
        assert len(default_paths) == 3

        # ...but raising the bound surfaces it.
        longer = await house.find_all_paths("device-hub", "home-1", max_length=6)
        assert [
            "device-hub",
            "device-light",
            "room-kitchen",
            "room-hall",
            "room-living",
            "home-1",
        ] in longer

    async def test_no_route_returns_empty(self, house):
        # home-1 has no outgoing edges.
        assert await house.find_all_paths("home-1", "device-hub") == []

    async def test_unknown_target_returns_empty(self, house):
        assert await house.find_all_paths("room-kitchen", "no-such-entity") == []

    async def test_start_equal_to_end_returns_the_trivial_path(self, house):
        assert await house.find_all_paths("home-1", "home-1") == [["home-1"]]

    async def test_filters_by_relationship_type(self, house):
        paths = await house.find_all_paths(
            "room-kitchen", "home-1", rel_types=[RelationshipType.LOCATED_IN]
        )

        assert paths == [["room-kitchen", "home-1"]]

    async def test_cycles_do_not_produce_infinite_paths(self, cycle_graph):
        paths = await cycle_graph.find_all_paths(
            "a", "c", rel_types=[RelationshipType.CONTROLS]
        )

        assert paths == [["a", "b", "c"]]


class TestAncestorsAndDescendants:
    """Hierarchy walks over a parent -> child relationship type.

    CONTROLS points from controller to controlled, i.e. parent -> child, which
    is the direction this pair of methods assumes. See
    ``test_get_ancestors_follows_part_of_the_wrong_way`` for the case where the
    schema's own edge direction is the other way round.
    """

    async def test_get_ancestors_walks_incoming_edges_transitively(self, control_chain):
        ancestors = await control_chain.get_ancestors("c3", RelationshipType.CONTROLS)

        assert [e.id for e in ancestors] == ["c2", "c1"]

    async def test_get_ancestors_of_root_is_empty(self, control_chain):
        assert await control_chain.get_ancestors("c1", RelationshipType.CONTROLS) == []

    async def test_get_ancestors_respects_max_depth(self, control_chain):
        ancestors = await control_chain.get_ancestors(
            "c3", RelationshipType.CONTROLS, max_depth=0
        )

        assert [e.id for e in ancestors] == ["c2"]

    async def test_get_ancestors_ignores_other_relationship_types(self, house):
        # device-light's incoming edges include AUTOMATES and PROCEDURE_FOR;
        # only the CONTROLS one may be followed.
        ancestors = await house.get_ancestors("device-light", RelationshipType.CONTROLS)

        assert [e.id for e in ancestors] == ["device-hub"]

    async def test_get_ancestors_terminates_on_cycle_without_duplicates(self, cycle_graph):
        ancestors = await cycle_graph.get_ancestors("a", RelationshipType.CONTROLS)

        ids = [e.id for e in ancestors]
        assert ids == ["c", "b"]
        assert len(ids) == len(set(ids))

    async def test_get_descendants_reaches_the_whole_subtree(self, control_chain):
        descendants = await control_chain.get_descendants("c1", RelationshipType.CONTROLS)

        assert {"c2", "c3"} <= {e.id for e in descendants}

    async def test_get_descendants_respects_max_depth(self, control_chain):
        ids = {
            e.id
            for e in await control_chain.get_descendants(
                "c1", RelationshipType.CONTROLS, max_depth=1
            )
        }

        assert "c2" in ids
        assert "c3" not in ids

    async def test_get_descendants_ignores_other_relationship_types(self, cycle_graph):
        ids = {
            e.id
            for e in await cycle_graph.get_descendants("a", RelationshipType.LOCATED_IN)
        }

        assert "room" in ids
        assert "b" not in ids

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG (traversal.py:190-229 / 231-253): get_ancestors and get_descendants "
            "assume edges point parent->child, but the schema's hierarchy edges point "
            "child->parent (relationship.py:147-151 validates PART_OF only as "
            "ROOM->HOME, ZONE->HOME, DEVICE->ZONE). get_ancestors follows *incoming* "
            "edges and calls rel.from_entity_id the 'parent', so for the PART_OF "
            "example named in its own docstring it walks downwards and returns "
            "nothing for a leaf."
        ),
    )
    async def test_get_ancestors_follows_part_of_the_wrong_way(self):
        graph = InMemoryGraph()
        graph.add_entity(make_entity("home", EntityType.HOME, "Home"))
        graph.add_entity(make_entity("zone", EntityType.ZONE, "Upstairs"))
        graph.add_entity(make_entity("dev", EntityType.DEVICE, "Sensor"))
        graph.connect("z-h", "zone", "home", RelationshipType.PART_OF)
        graph.connect("d-z", "dev", "zone", RelationshipType.PART_OF)

        ancestors = await graph.get_ancestors("dev", RelationshipType.PART_OF)

        assert [e.id for e in ancestors] == ["zone", "home"]

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG (traversal.py:249-253): get_descendants delegates to bfs(), which "
            "includes the starting entity in its result, so an entity is reported as "
            "its own descendant. get_ancestors excludes self, so the two are "
            "asymmetric."
        ),
    )
    async def test_get_descendants_excludes_the_starting_entity(self, control_chain):
        descendants = await control_chain.get_descendants("c1", RelationshipType.CONTROLS)

        assert [e.id for e in descendants] == ["c2", "c3"]


class TestDetectCycles:
    """Cycle detection."""

    async def test_detects_a_simple_cycle(self, cycle_graph):
        cycles = await cycle_graph.detect_cycles(
            start_id="a", rel_types=[RelationshipType.CONTROLS]
        )

        # The cycle is reported as a closed walk: back to where it started.
        assert cycles == [["a", "b", "c", "a"]]

    async def test_detects_a_self_loop(self):
        graph = InMemoryGraph()
        graph.add_entity(make_entity("a", EntityType.DEVICE, "A"))
        graph.connect("aa", "a", "a", RelationshipType.CONTROLS)

        assert await graph.detect_cycles(start_id="a") == [["a", "a"]]

    async def test_acyclic_graph_reports_no_cycles(self, house):
        assert await house.detect_cycles(start_id="device-hub") == []

    async def test_relationship_type_filter_can_hide_a_cycle(self, cycle_graph):
        cycles = await cycle_graph.detect_cycles(
            start_id="a", rel_types=[RelationshipType.LOCATED_IN]
        )

        assert cycles == []

    async def test_unknown_start_reports_no_cycles(self, house):
        assert await house.detect_cycles(start_id="no-such-entity") == []

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG (traversal.py:299-304): detect_cycles(start_id=None) is documented as "
            "'if None, check entire graph' but the else branch is a bare `pass`, so it "
            "silently reports no cycles for a graph that has one. Either the docstring "
            "or the implementation is wrong; a caller cannot tell a clean graph from an "
            "unimplemented scan."
        ),
    )
    async def test_whole_graph_scan_finds_cycles(self, cycle_graph):
        assert await cycle_graph.detect_cycles() == [["a", "b", "c", "a"]]


class TestCentrality:
    """Degree centrality."""

    async def test_degree_centrality_counts_incoming_and_outgoing(self, house):
        # device-light: 2 outgoing (LOCATED_IN, DOCUMENTED_BY) + 3 incoming
        # (CONTROLS, AUTOMATES, PROCEDURE_FOR).
        assert await house.calculate_centrality("device-light") == 5

    async def test_degree_centrality_of_a_sink(self, house):
        # home-1 has three incoming LOCATED_IN edges and no outgoing ones.
        assert await house.calculate_centrality("home-1", metric="degree") == 3

    async def test_isolated_entity_has_zero_centrality(self, house):
        assert await house.calculate_centrality("note-1") == 0

    async def test_unknown_entity_has_zero_centrality(self, house):
        assert await house.calculate_centrality("no-such-entity") == 0

    async def test_unimplemented_metrics_return_zero(self, house):
        # "closeness" and "betweenness" are named in the docstring but not
        # implemented; they fall through to 0.0, which a caller cannot tell
        # apart from a genuinely uncentral entity.
        assert await house.calculate_centrality("device-light", metric="closeness") == 0.0
        assert await house.calculate_centrality("device-light", metric="betweenness") == 0.0
