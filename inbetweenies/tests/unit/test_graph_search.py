"""Test GraphSearch scoring, ranking and similarity (inbetweenies/graph/search.py).

The scoring formula is the shared ranking contract: server and client must
agree on it or the same query returns different orders on different clients.
These tests pin the weights (name substring 3.0, per-word 1.5, content 2.0,
per-content-field 1.0, exact-name doubling, fuzzy bonus) and the resulting
order, not just "something came back".
"""

import pytest

from inbetweenies.graph.search import SearchResult
from inbetweenies.models import Entity, EntityType, SourceType
from inbetweenies.tests.memory_graph import (
    InMemoryGraph,
    SearchOnlyGraph,
    make_entity,
)


@pytest.fixture
def scorer():
    """Any GraphSearch instance; calculate_score is a pure method on the base."""
    return InMemoryGraph()


@pytest.fixture
def light():
    """A device with no content, so name scoring can be tested in isolation."""
    return make_entity("light", EntityType.DEVICE, "Kitchen Light", {})


class TestSearchResult:
    """The wire shape a search result is serialized into."""

    def test_to_dict_payload(self, light):
        result = SearchResult(light, 4.25, {"name": ["Kitchen Light"]})

        assert result.to_dict() == {
            "id": "light",
            "version": "v1",
            "entity_type": "device",
            "name": "Kitchen Light",
            "score": 4.25,
            "highlights": {"name": ["Kitchen Light"]},
            "content_preview": None,
        }

    def test_content_preview_shows_first_three_fields_only(self):
        entity = make_entity(
            "e",
            EntityType.DEVICE,
            "Device",
            {"a": 1, "b": 2, "c": 3, "d": 4},
        )

        preview = SearchResult(entity, 1.0, {}).to_dict()["content_preview"]

        assert preview == "a: 1, b: 2, c: 3..."
        assert "d: 4" not in preview

    def test_content_preview_truncates_long_values_at_fifty_chars(self):
        entity = make_entity("e", EntityType.DEVICE, "Device", {"notes": "x" * 200})

        preview = SearchResult(entity, 1.0, {}).to_dict()["content_preview"]

        assert preview == "notes: " + "x" * 50 + "..."

    def test_content_preview_is_none_without_content(self):
        assert SearchResult(
            make_entity("e", EntityType.DEVICE, "Device", None), 1.0, {}
        ).to_dict()["content_preview"] is None

        assert SearchResult(
            make_entity("e", EntityType.DEVICE, "Device", {}), 1.0, {}
        ).to_dict()["content_preview"] is None

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG (search.py:28): SearchResult.to_dict does `self.entity.entity_type.value` "
            "unguarded, so it raises AttributeError when entity_type is a plain string. "
            "Entity.to_dict (entity.py:103) and EntityRelationship.to_dict "
            "(relationship.py:106) both defend against exactly this with hasattr/getattr, "
            "so a string-valued entity serializes everywhere except here. Directly "
            "relevant to the strings-for-enums refactor."
        ),
    )
    def test_to_dict_accepts_a_string_entity_type(self):
        entity = Entity(
            id="e",
            version="v1",
            entity_type="device",  # a plain str, not EntityType.DEVICE
            name="Device",
            content={},
            source_type=SourceType.MANUAL,
            user_id="u",
            parent_versions=[],
        )

        assert SearchResult(entity, 1.0, {}).to_dict()["entity_type"] == "device"


class TestCalculateScore:
    """Relevance scoring for a single entity."""

    def test_exact_name_match_is_doubled_and_gets_the_fuzzy_bonus(self, scorer, light):
        score, highlights = scorer.calculate_score(light, "kitchen light")

        # 3.0 (name contains query) doubled to 6.0 for the exact match, plus a
        # 1.0 fuzzy-similarity bonus for the perfect ratio.
        assert score == 7.0
        assert highlights == {"name": ["Kitchen Light"]}

    def test_name_match_is_case_insensitive(self, scorer, light):
        assert scorer.calculate_score(light, "KITCHEN LIGHT")[0] == 7.0

    def test_substring_of_name_scores_three(self, scorer, light):
        score, highlights = scorer.calculate_score(light, "kitchen")

        assert score == 3.0
        assert highlights["name"] == ["Kitchen Light"]

    def test_individual_word_matches_score_one_and_a_half_each(self, scorer, light):
        # "light kitchen" is not a substring of "Kitchen Light", but both words
        # appear: 2 x 1.5.
        assert scorer.calculate_score(light, "light kitchen")[0] == 3.0

        # Only one of the two words appears: 1 x 1.5.
        assert scorer.calculate_score(light, "kitchen bedroom")[0] == 1.5

    def test_fuzzy_match_rescues_a_typo(self, scorer):
        kitchen = make_entity("k", EntityType.ROOM, "Kitchen", {})

        score, highlights = scorer.calculate_score(kitchen, "Kitcen")

        # No substring or word match at all; the whole score is the >0.8
        # SequenceMatcher ratio.
        assert score == pytest.approx(0.923, abs=0.001)
        assert highlights == {}

    def test_typo_below_the_fuzzy_threshold_scores_nothing(self, scorer):
        kitchen = make_entity("k", EntityType.ROOM, "Kitchen", {})

        assert scorer.calculate_score(kitchen, "bathroom") == (0.0, {})

    def test_content_substring_scores_two_plus_one_per_matching_field(self, scorer):
        entity = make_entity(
            "e", EntityType.DEVICE, "Anonymous", {"manufacturer": "TestCorp"}
        )

        score, highlights = scorer.calculate_score(entity, "testcorp")

        # 2.0 for the serialized content containing the query + 1.0 for the
        # individual string field that contains it.
        assert score == 3.0
        assert highlights["content"] == [
            "Content contains 'testcorp'",
            "manufacturer: TestCorp...",
        ]
        assert "name" not in highlights

    def test_content_word_matches_score_a_half_each(self, scorer):
        entity = make_entity("e", EntityType.DEVICE, "Anonymous", {"room": "attic"})

        score, highlights = scorer.calculate_score(entity, "attic zzzz")

        assert score == 0.5
        assert highlights["content"] == ["Content matches 1 word(s)"]

    def test_content_keys_are_searchable_too(self, scorer):
        entity = make_entity("e", EntityType.DEVICE, "Anonymous", {"brightness": 75})

        score, _ = scorer.calculate_score(entity, "brightness")

        # The whole content dict is serialized to JSON before matching, so keys
        # match as well as values (2.0, with no per-field bonus: 75 is not a str).
        assert score == 2.0

    def test_no_match_anywhere_scores_zero(self, scorer, light):
        assert scorer.calculate_score(light, "helicopter") == (0.0, {})

    def test_entity_without_content_is_scored_on_name_alone(self, scorer):
        entity = make_entity("e", EntityType.DEVICE, "Kitchen Light", None)

        assert scorer.calculate_score(entity, "kitchen")[0] == 3.0


class TestFilterAndRank:
    """Turning scored entities into an ordered result list."""

    @pytest.fixture
    def entities(self):
        """Four entities that land in four distinct tiers for "kitchen light"."""
        return [
            make_entity("word", EntityType.DEVICE, "Front Light", {}),  # 1.5
            make_entity("miss", EntityType.DEVICE, "Front Door", {}),  # 0.0
            make_entity("exact", EntityType.DEVICE, "Kitchen Light", {}),  # 7.0
            make_entity("substring", EntityType.DEVICE, "My Kitchen Light Switch", {}),  # 3.0
        ]

    def test_ranks_by_descending_score(self, scorer, entities):
        results = scorer.filter_and_rank_results(entities, "kitchen light", limit=10)

        assert [r.entity.id for r in results] == ["exact", "substring", "word"]
        assert [r.score for r in results] == sorted(
            (r.score for r in results), reverse=True
        )

    def test_zero_scoring_entities_are_dropped(self, scorer, entities):
        results = scorer.filter_and_rank_results(entities, "kitchen light", limit=10)

        assert "miss" not in [r.entity.id for r in results]
        assert len(results) == 3

    def test_limit_truncates_the_ranked_list(self, scorer, entities):
        results = scorer.filter_and_rank_results(entities, "kitchen light", limit=2)

        assert [r.entity.id for r in results] == ["exact", "substring"]

    def test_limit_zero_returns_nothing(self, scorer, entities):
        assert scorer.filter_and_rank_results(entities, "kitchen light", limit=0) == []

    def test_no_candidates_returns_empty(self, scorer):
        assert scorer.filter_and_rank_results([], "kitchen", limit=10) == []

    def test_ties_keep_input_order(self, scorer):
        tied = [
            make_entity("second", EntityType.DEVICE, "Kitchen Light", {}),
            make_entity("first", EntityType.DEVICE, "Kitchen Fan", {}),
        ]

        results = scorer.filter_and_rank_results(tied, "kitchen", limit=10)

        assert [r.score for r in results] == [3.0, 3.0]
        assert [r.entity.id for r in results] == ["second", "first"]


class TestSearchEntitiesOverAGraph:
    """End-to-end search through a populated graph."""

    async def test_ranks_the_exact_name_match_first(self, house):
        results = await house.search_entities("kitchen", limit=10)

        assert [r.entity.id for r in results] == [
            "room-kitchen",  # exact name -> 7.0
            "device-light",  # "Kitchen Light" -> 3.0
            "procedure-1",  # "Reset Kitchen Light" -> 3.0
            "manual-1",  # "Kitchen Light Manual" -> 3.0
        ]
        assert results[0].score > results[1].score

    async def test_entity_type_filter_restricts_candidates(self, house):
        results = await house.search_entities(
            "kitchen", entity_types=[EntityType.DEVICE], limit=10
        )

        assert [r.entity.id for r in results] == ["device-light"]

    async def test_limit_is_applied_after_ranking(self, house):
        results = await house.search_entities("kitchen", limit=2)

        assert [r.entity.id for r in results] == ["room-kitchen", "device-light"]

    async def test_query_matching_nothing_returns_empty(self, house):
        assert await house.search_entities("helicopter") == []

    async def test_search_on_empty_graph_returns_empty(self, empty_graph):
        assert await empty_graph.search_entities("kitchen") == []


class TestFindSimilarEntities:
    """Similarity search: same-type entities scored by name and content overlap."""

    @pytest.fixture
    def graph(self):
        graph = InMemoryGraph()
        graph.add_entity(
            make_entity(
                "ref",
                EntityType.DEVICE,
                "Kitchen Light",
                {"manufacturer": "TestCorp", "watts": 9},
            )
        )
        graph.add_entity(
            make_entity(
                "twin",
                EntityType.DEVICE,
                "Kitchen Light",
                {"manufacturer": "TestCorp", "watts": 9},
            )
        )
        graph.add_entity(
            make_entity(
                "cousin",
                EntityType.DEVICE,
                "Hallway Light",
                {"manufacturer": "TestCorp", "watts": 5},
            )
        )
        graph.add_entity(
            make_entity("stranger", EntityType.DEVICE, "Boiler", {"pressure": 2})
        )
        graph.add_entity(
            make_entity("other-type", EntityType.ROOM, "Kitchen Light", {"watts": 9})
        )
        return graph

    async def test_ranks_the_most_similar_first(self, graph):
        results = await graph.find_similar_entities("ref")

        assert [r.entity.id for r in results] == ["twin", "cousin", "stranger"]
        assert results[0].score > results[1].score > results[2].score

    async def test_excludes_the_reference_entity(self, graph):
        assert "ref" not in [r.entity.id for r in await graph.find_similar_entities("ref")]

    async def test_only_considers_entities_of_the_same_type(self, graph):
        assert "other-type" not in [
            r.entity.id for r in await graph.find_similar_entities("ref")
        ]

    async def test_limit_is_respected(self, graph):
        results = await graph.find_similar_entities("ref", limit=1)

        assert [r.entity.id for r in results] == ["twin"]

    async def test_highlights_name_the_reference(self, graph):
        results = await graph.find_similar_entities("ref", limit=1)

        assert results[0].highlights == {"similarity": ["Similar to Kitchen Light"]}

    async def test_unknown_entity_returns_empty(self, graph):
        assert await graph.find_similar_entities("no-such-entity") == []

    async def test_only_entity_of_its_type_has_no_similars(self, house):
        assert await house.find_similar_entities("home-1") == []

    async def test_search_backend_without_graph_operations_returns_empty(self):
        # find_similar_entities needs get_entity/get_entities_by_type, so a
        # GraphSearch that is not also a GraphOperations bails out.
        assert await SearchOnlyGraph().find_similar_entities("anything") == []


class TestCalculateSimilarity:
    """The pairwise similarity metric behind find_similar_entities."""

    def test_identical_entities_score_one(self, scorer):
        entity = make_entity("a", EntityType.DEVICE, "Kitchen Light", {"watts": 9})

        # 0.2 same type + 0.3 name + 0.3 key overlap + 0.2 equal values.
        assert scorer._calculate_similarity(entity, entity) == pytest.approx(1.0)

    def test_same_type_contributes_two_tenths(self, scorer):
        a = make_entity("a", EntityType.DEVICE, "aaaa", None)
        b_same = make_entity("b", EntityType.DEVICE, "aaaa", None)
        b_other = make_entity("b", EntityType.ROOM, "aaaa", None)

        assert scorer._calculate_similarity(a, b_same) - scorer._calculate_similarity(
            a, b_other
        ) == pytest.approx(0.2)

    def test_matching_content_values_beat_matching_keys_alone(self, scorer):
        ref = make_entity("ref", EntityType.DEVICE, "Light", {"watts": 9})
        same_value = make_entity("a", EntityType.DEVICE, "Light", {"watts": 9})
        same_key = make_entity("b", EntityType.DEVICE, "Light", {"watts": 60})

        assert scorer._calculate_similarity(ref, same_value) == pytest.approx(
            scorer._calculate_similarity(ref, same_key) + 0.2
        )

    def test_disjoint_content_keys_add_nothing(self, scorer):
        ref = make_entity("ref", EntityType.DEVICE, "Light", {"watts": 9})
        other = make_entity("o", EntityType.DEVICE, "Light", {"pressure": 2})

        # 0.2 same type + 0.3 identical name, no content contribution.
        assert scorer._calculate_similarity(ref, other) == pytest.approx(0.5)

    def test_missing_content_skips_the_content_terms(self, scorer):
        ref = make_entity("ref", EntityType.DEVICE, "Light", {"watts": 9})
        empty = make_entity("o", EntityType.DEVICE, "Light", None)

        assert scorer._calculate_similarity(ref, empty) == pytest.approx(0.5)

    def test_dissimilar_names_lower_the_score(self, scorer):
        ref = make_entity("ref", EntityType.DEVICE, "Kitchen Light", None)
        close = make_entity("a", EntityType.DEVICE, "Kitchen Lights", None)
        far = make_entity("b", EntityType.DEVICE, "Boiler", None)

        assert scorer._calculate_similarity(ref, close) > scorer._calculate_similarity(
            ref, far
        )
