"""House vocabulary, derived from the definitions it replaces.

DERIVED, NOT TRANSCRIBED — and that is the point. ADR-012 §6.1 requires house
behaviour to be byte-identical after the abstraction, gated by the conformance
suite. Retyping 12 entity types, 5 source types and 14 relationship rules by
hand would put that guarantee at the mercy of a typo in a table nothing else
reads. Building the manifest from `EntityType`, `SourceType` and the
`valid_combinations` map inside `is_valid_for_entities` makes it identical by
construction: there is no second copy to drift.

The enums stay where they are for now. They are the house domain's vocabulary,
not the engine's, but moving their definition is a separate mechanical change
from removing the engine's *dependence* on them — and doing both at once would
mean a large diff whose behaviour-preservation could not be checked
independently. This step removes the dependence.

When `domains/garage` arrives it will declare its vocabulary directly rather
than deriving it, since it has nothing to be derived from.
"""

from inbetweenies.domain import RelationshipRule, build_manifest
from inbetweenies.models import EntityType, RelationshipType, SourceType
from inbetweenies.models.relationship import EntityRelationship


def _endpoint_rules():
    """Recover the endpoint constraints by ASKING the predicate that owns them.

    `is_valid_for_entities` keeps its `valid_combinations` table as a function
    local, so there is nothing to import. Rather than transcribe it — the one
    thing that could make "byte-identical" false — the manifest probes the
    predicate over every (relationship_type, from_type, to_type) triple and
    records what it accepts. 12 x 12 x 14 is ~2000 calls at import time, which
    is nothing, and it derives from BEHAVIOUR rather than from a data
    structure: if the rule ever stops being a lookup table, the manifest still
    matches whatever it became.

    Note the asymmetry this preserves: a relationship type with NO entry in the
    table accepts nothing, which is not the same as accepting anything. The
    manifest records that faithfully as an explicit empty allow-list rather
    than as "unconstrained".
    """
    class _Endpoint:
        __slots__ = ("entity_type",)

        def __init__(self, entity_type):
            self.entity_type = entity_type

    entity_types = list(EntityType)
    for rel_type in RelationshipType:
        probe = EntityRelationship(relationship_type=rel_type)
        allowed = tuple(
            (str(a.value), str(b.value))
            for a in entity_types
            for b in entity_types
            if probe.is_valid_for_entities(_Endpoint(a), _Endpoint(b))
        )
        yield RelationshipRule(name=str(rel_type.value), allowed_endpoints=allowed)


HOUSE = build_manifest(
    name="house",
    entity_types=[t.value for t in EntityType],
    source_types=[t.value for t in SourceType],
    relationship_rules=_endpoint_rules(),
)
