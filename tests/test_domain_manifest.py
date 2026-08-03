"""The base vocabulary every domain inherits (ADR-013 §3, §4).

Attachments and apps are engine mechanism, not house knowledge. These tests pin
that a domain gets them *without declaring them*, because the whole claim of the
domain abstraction is that a second domain needs no engine change — and a domain
forced to re-declare `photo` and `has_photo` would be re-stating engine
mechanism as its own vocabulary.
"""

import pytest

from inbetweenies.domain import (
    BASE_ATTACHMENT_TYPES,
    BASE_ENTITY_TYPES,
    DomainValidationError,
    RelationshipRule,
    build_manifest,
)


@pytest.fixture
def bare():
    """A domain that declares nothing at all beyond one type of its own."""
    return build_manifest(
        name="bare",
        entity_types=["widget"],
        source_types=["imported"],
        relationship_rules=[],
    )


# --- What a domain gets for free ------------------------------------------- #

def test_a_domain_inherits_base_entity_types_without_declaring_them(bare):
    for base_type in BASE_ENTITY_TYPES:
        assert base_type in bare.entity_types
    assert "widget" in bare.entity_types


def test_a_domain_inherits_base_relationships_without_declaring_them(bare):
    assert "has_photo" in bare.relationship_types
    assert "manages" in bare.relationship_types


def test_base_relationships_are_usable_by_a_domain_that_never_heard_of_them(bare):
    # The point of the wildcard: the base constrains one end of the edge while
    # knowing nothing about 'widget'.
    bare.check_relationship("has_photo", "widget", "photo")
    bare.check_relationship("manages", "app", "widget")


def test_has_photo_still_only_points_at_a_photo(bare):
    with pytest.raises(DomainValidationError):
        bare.check_relationship("has_photo", "widget", "widget")


def test_manages_still_only_starts_at_an_app(bare):
    with pytest.raises(DomainValidationError):
        bare.check_relationship("manages", "widget", "widget")


# --- Attachments ------------------------------------------------------------ #

def test_photo_is_an_attachment_everywhere(bare):
    assert bare.carries_blob("photo")
    assert not bare.carries_blob("widget")


def test_a_domain_can_add_its_own_attachment_types():
    """`manual` is a house-flavoured document; `photo` is universal."""
    m = build_manifest(
        name="vehicles", entity_types=["car"], source_types=["manual"],
        relationship_rules=[], attachment_types=("service_record",),
    )
    assert m.carries_blob("service_record")
    assert m.carries_blob("photo")          # base still there
    # Declaring an attachment type also declares it as an entity type: a domain
    # should not have to list the same word twice.
    assert "service_record" in m.entity_types


def test_a_domain_cannot_drop_a_base_attachment_type():
    m = build_manifest(
        name="vehicles", entity_types=["car"], source_types=["manual"],
        relationship_rules=[], attachment_types=(),
    )
    assert frozenset(BASE_ATTACHMENT_TYPES) <= m.attachment_types


# --- Narrowing -------------------------------------------------------------- #

def test_a_domain_rule_overrides_the_base_rule_of_the_same_name():
    """Redeclaring is for *narrowing*: base says app->anything, houses say less."""
    m = build_manifest(
        name="narrow", entity_types=["car", "note"], source_types=["manual"],
        relationship_rules=[RelationshipRule(name="manages",
                                             allowed_endpoints=(("app", "car"),))],
    )
    m.check_relationship("manages", "app", "car")
    with pytest.raises(DomainValidationError):
        m.check_relationship("manages", "app", "note")


def test_the_house_narrows_manages():
    """Regression: the real manifest must not silently inherit app -> anything."""
    from domains.house.manifest import HOUSE

    HOUSE.check_relationship("manages", "app", "device")
    with pytest.raises(DomainValidationError):
        HOUSE.check_relationship("manages", "app", "note")


# --- The wildcard itself ---------------------------------------------------- #

@pytest.mark.parametrize("endpoints,from_t,to_t,expected", [
    ((("*", "photo"),), "anything", "photo", True),
    ((("*", "photo"),), "anything", "note", False),
    ((("app", "*"),), "app", "anything", True),
    ((("app", "*"),), "note", "anything", False),
    ((("*", "*"),), "a", "b", True),
    ((("device", "room"),), "device", "room", True),
    ((("device", "room"),), "device", "zone", False),
])
def test_wildcard_matching(endpoints, from_t, to_t, expected):
    assert RelationshipRule(name="r", allowed_endpoints=endpoints).permits(from_t, to_t) is expected


def test_the_three_states_are_unaffected_by_the_wildcard():
    """None is unconstrained, () is nothing — ADR-012's distinction still holds.

    Conflating them is what would silently make an uncreatable relationship
    creatable, which is the failure the manifest exists to avoid.
    """
    assert RelationshipRule(name="r", allowed_endpoints=None).permits("a", "b")
    assert not RelationshipRule(name="r", allowed_endpoints=()).permits("a", "b")


# --- The house no longer owns what it does not own -------------------------- #

def test_house_does_not_redeclare_base_vocabulary():
    """If the house re-declares these, the base is decorative.

    Reads the source rather than the built manifest, because build_manifest
    merges the base in — so the assembled HOUSE contains `photo` either way and
    could not tell the difference.
    """
    from domains.house import manifest

    assert "photo" not in manifest.ENTITY_TYPES
    assert "app" not in manifest.ENTITY_TYPES
    assert "has_photo" not in {r.name for r in manifest.RELATIONSHIP_RULES}
