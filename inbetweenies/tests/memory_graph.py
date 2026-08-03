"""In-memory implementations of the inbetweenies graph abstractions.

`inbetweenies.graph` and `inbetweenies.mcp` are abstract: they define the
contract every client (FunkyGibbon's SQL backend, blowing-off's local store, a
future Swift port) implements, and then build real algorithms on top of the two
or three primitives each subclass must supply.

This module supplies the smallest honest backend for those primitives -- plain
dicts and lists -- so the *algorithms* (BFS/DFS, path finding, scoring, the MCP
tool payloads) can be tested for real behaviour rather than mocked away. The
primitives here are deliberately dumb: no filtering shortcuts, no caching, and
insertion-ordered results, so traversal order in the tests is deterministic.

Not a test module itself (pytest only collects ``test_*.py``).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from inbetweenies.graph import GraphTraversal
from inbetweenies.graph.search import GraphSearch, SearchResult
from inbetweenies.mcp import MCPTools
from inbetweenies.models import (
    Entity,
    EntityRelationship,
    EntityType,
    RelationshipType,
    SourceType,
)

# Fixed timestamp so serialized payloads are deterministic.
BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# Sentinel so callers can ask for ``content=None`` (entities loaded from a
# backend that never set content) as distinct from "give me the default {}".
_UNSET = object()


def make_entity(
    entity_id: str,
    entity_type: EntityType,
    name: str,
    content: Any = _UNSET,
    version: str = "v1",
    source_type: SourceType = SourceType.MANUAL,
    user_id: str = "test-user",
    parent_versions: Optional[List[str]] = None,
) -> Entity:
    """Build a detached Entity (no session, no flush)."""
    return Entity(
        id=entity_id,
        version=version,
        entity_type=entity_type,
        name=name,
        content={} if content is _UNSET else content,
        source_type=source_type,
        user_id=user_id,
        parent_versions=parent_versions if parent_versions is not None else [],
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def make_relationship(
    rel_id: str,
    from_entity_id: str,
    to_entity_id: str,
    relationship_type: RelationshipType,
    properties: Optional[Dict[str, Any]] = None,
    from_version: str = "v1",
    to_version: str = "v1",
    user_id: str = "test-user",
) -> EntityRelationship:
    """Build a detached EntityRelationship."""
    return EntityRelationship(
        id=rel_id,
        from_entity_id=from_entity_id,
        from_entity_version=from_version,
        to_entity_id=to_entity_id,
        to_entity_version=to_version,
        relationship_type=relationship_type,
        properties=properties if properties is not None else {},
        user_id=user_id,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


class InMemoryGraph(MCPTools, GraphTraversal):
    """Dict-backed implementation of every abstract method in the package.

    Implements the five ``GraphOperations`` primitives, ``GraphSearch``'s
    ``search_entities``, and (via the same primitives) ``GraphTraversal``, so a
    single object exercises operations, search, traversal and the MCP tools.
    """

    def __init__(self) -> None:
        # entity id -> versions, oldest first. The last entry is "current".
        self._versions: Dict[str, List[Entity]] = {}
        self._relationships: List[EntityRelationship] = []

    # ------------------------------------------------------------------
    # Test-authoring helpers (not part of the contract)
    # ------------------------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        self._versions.setdefault(entity.id, []).append(entity)
        return entity

    def add_relationship(self, relationship: EntityRelationship) -> EntityRelationship:
        self._relationships.append(relationship)
        return relationship

    def connect(
        self,
        rel_id: str,
        from_entity_id: str,
        to_entity_id: str,
        relationship_type: RelationshipType,
        properties: Optional[Dict[str, Any]] = None,
    ) -> EntityRelationship:
        return self.add_relationship(
            make_relationship(
                rel_id, from_entity_id, to_entity_id, relationship_type, properties
            )
        )

    # ------------------------------------------------------------------
    # GraphOperations primitives
    # ------------------------------------------------------------------

    async def store_entity(self, entity: Entity) -> Entity:
        return self.add_entity(entity)

    async def get_entity(
        self, entity_id: str, version: Optional[str] = None
    ) -> Optional[Entity]:
        versions = self._versions.get(entity_id)
        if not versions:
            return None
        if version is None:
            return versions[-1]
        for candidate in versions:
            if candidate.version == version:
                return candidate
        return None

    async def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        return [
            versions[-1]
            for versions in self._versions.values()
            if versions and versions[-1].entity_type == entity_type
        ]

    async def store_relationship(
        self, relationship: EntityRelationship
    ) -> EntityRelationship:
        return self.add_relationship(relationship)

    async def get_relationships(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        rel_type: Optional[RelationshipType] = None,
    ) -> List[EntityRelationship]:
        matches = []
        for rel in self._relationships:
            if from_id is not None and rel.from_entity_id != from_id:
                continue
            if to_id is not None and rel.to_entity_id != to_id:
                continue
            if rel_type is not None and rel.relationship_type != rel_type:
                continue
            matches.append(rel)
        return matches

    # ------------------------------------------------------------------
    # GraphSearch primitive
    # ------------------------------------------------------------------

    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 10,
    ) -> List[SearchResult]:
        candidates = [versions[-1] for versions in self._versions.values() if versions]
        if entity_types:
            candidates = [e for e in candidates if e.entity_type in entity_types]
        return self.filter_and_rank_results(candidates, query, limit)


class VersionedInMemoryGraph(InMemoryGraph):
    """Backend that also exposes version history.

    ``MCPTools.get_entity_details_tool`` probes for ``get_entity_versions`` with
    ``hasattr``; this subclass exercises the branch where the backend has it.
    """

    async def get_entity_versions(self, entity_id: str) -> List[Entity]:
        return list(self._versions.get(entity_id, []))


class ExplodingGraph(InMemoryGraph):
    """Backend whose ``get_entity`` always fails.

    Every MCP tool wraps its body in ``try/except Exception`` and converts the
    failure into ``ToolResult(success=False, error=str(e))``; this backend is how
    that contract gets tested without mocks.
    """

    MESSAGE = "backend unavailable"

    async def get_entity(self, entity_id: str, version: Optional[str] = None):
        raise RuntimeError(self.MESSAGE)


class SearchOnlyGraph(GraphSearch):
    """A GraphSearch implementation that is deliberately *not* a GraphOperations.

    ``GraphSearch.find_similar_entities`` guards on ``isinstance(self,
    GraphOperations)``; this class covers the unguarded-fallback branch.
    """

    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 10,
    ) -> List[SearchResult]:
        return []


def build_house() -> InMemoryGraph:
    """A small but complete house graph used across the graph/MCP tests.

    Entities::

        home-1 (HOME "Test Home")
        room-kitchen (ROOM "Kitchen")      room-hall (ROOM "Hallway")
        room-living (ROOM "Living Room")   note-1 (NOTE, isolated)
        device-light (DEVICE "Kitchen Light")
        device-hub (DEVICE "Smart Hub")
        automation-1 (AUTOMATION "Evening Lights")
        procedure-1 (PROCEDURE "Reset Kitchen Light")
        manual-1 (MANUAL "Kitchen Light Manual")

    Edges (direction matters -- see the traversal tests)::

        room-kitchen  LOCATED_IN     home-1
        room-hall     LOCATED_IN     home-1
        room-living   LOCATED_IN     home-1
        device-light  LOCATED_IN     room-kitchen
        device-hub    LOCATED_IN     room-living
        device-hub    CONTROLS       device-light
        room-kitchen  CONNECTS_TO    room-hall     {"via": "doorway"}
        room-hall     CONNECTS_TO    room-living   {"via": "archway"}
        automation-1  AUTOMATES      device-light
        procedure-1   PROCEDURE_FOR  device-light
        device-light  DOCUMENTED_BY  manual-1
    """
    graph = InMemoryGraph()

    graph.add_entity(make_entity("home-1", EntityType.HOME, "Test Home", {"address": "123 Test St"}))
    graph.add_entity(make_entity("room-kitchen", EntityType.ROOM, "Kitchen", {"floor": 1}))
    graph.add_entity(make_entity("room-hall", EntityType.ROOM, "Hallway", {"floor": 1}))
    graph.add_entity(make_entity("room-living", EntityType.ROOM, "Living Room", {"floor": 1}))
    graph.add_entity(
        make_entity(
            "device-light",
            EntityType.DEVICE,
            "Kitchen Light",
            {
                "manufacturer": "TestCorp",
                "capabilities": ["on_off", "brightness"],
                "services": ["lightbulb"],
            },
        )
    )
    graph.add_entity(
        make_entity(
            "device-hub",
            EntityType.DEVICE,
            "Smart Hub",
            {"manufacturer": "TestCorp", "capabilities": ["bridge"]},
        )
    )
    graph.add_entity(
        make_entity("automation-1", EntityType.AUTOMATION, "Evening Lights", {"enabled": True})
    )
    graph.add_entity(
        make_entity(
            "procedure-1",
            EntityType.PROCEDURE,
            "Reset Kitchen Light",
            {"steps": ["hold button", "release"]},
        )
    )
    graph.add_entity(
        make_entity("manual-1", EntityType.MANUAL, "Kitchen Light Manual", {"pages": 12})
    )
    graph.add_entity(make_entity("note-1", EntityType.NOTE, "Orphan Note", {"text": "nothing"}))

    graph.connect("rel-kitchen-home", "room-kitchen", "home-1", RelationshipType.LOCATED_IN)
    graph.connect("rel-hall-home", "room-hall", "home-1", RelationshipType.LOCATED_IN)
    graph.connect("rel-living-home", "room-living", "home-1", RelationshipType.LOCATED_IN)
    graph.connect("rel-light-kitchen", "device-light", "room-kitchen", RelationshipType.LOCATED_IN)
    graph.connect("rel-hub-living", "device-hub", "room-living", RelationshipType.LOCATED_IN)
    graph.connect("rel-hub-light", "device-hub", "device-light", RelationshipType.CONTROLS)
    graph.connect(
        "rel-kitchen-hall",
        "room-kitchen",
        "room-hall",
        RelationshipType.CONNECTS_TO,
        {"via": "doorway"},
    )
    graph.connect(
        "rel-hall-living",
        "room-hall",
        "room-living",
        RelationshipType.CONNECTS_TO,
        {"via": "archway"},
    )
    graph.connect("rel-auto-light", "automation-1", "device-light", RelationshipType.AUTOMATES)
    graph.connect("rel-proc-light", "procedure-1", "device-light", RelationshipType.PROCEDURE_FOR)
    graph.connect("rel-light-manual", "device-light", "manual-1", RelationshipType.DOCUMENTED_BY)

    return graph
