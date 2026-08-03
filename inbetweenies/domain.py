"""Domain manifest — the vocabulary contract between engine and domain (ADR-012).

The engine is already domain-blind everywhere that matters: versioning, the
temporal model, sync and resolution, auth, blobs, the graph index and traversal
mention no house. What was *not* blind was the vocabulary, which lived in two
places the engine owned:

* `EntityType` / `RelationshipType` / `SourceType` as `SQLEnum` **database
  columns**, so a new domain was a schema migration.
* `EntityRelationship.is_valid_for_entities`, which hard-codes that a DEVICE may
  be LOCATED_IN a ROOM — house knowledge living in a shared model.

A manifest is data, not schema: adding a domain becomes a new manifest, not an
ALTER TABLE. Validation moves to the API/sync boundary, so the store keeps what
the domain declares and nothing else decides what is sayable.

Deliberately NOT "any string is fine". Typo-tolerant writes fragment a graph
silently — `"DEVICE"`, `"device"` and `"Device"` become three types nothing
joins — and the damage is only visible much later, in query results that are
quietly incomplete. The manifest keeps writes honest while staying data.
"""

from dataclasses import dataclass
from typing import FrozenSet, Iterable, Mapping, Optional, Tuple


@dataclass(frozen=True)
class RelationshipRule:
    """One relationship type and the endpoint pairs it may connect.

    Three states, deliberately distinguished, because conflating the last two
    is how an abstraction silently changes behaviour:

    * `allowed_endpoints=(("device", "room"),)` — only those pairs.
    * `allowed_endpoints=None` — explicitly unconstrained; any pair.
    * `allowed_endpoints=()` — nothing is permitted.

    The empty tuple looks like a mistake and is not. The house vocabulary
    declares `contained_in` and `depends_on` with no endpoint pairs, and the
    predicate this manifest replaces rejects every pair for them. Reading empty
    as "unconstrained" would have quietly made two unusable relationship types
    usable — a behaviour change smuggled in by an abstraction whose whole
    premise is that behaviour does not change. The gap is real and worth
    fixing, but as a deliberate edit to the house vocabulary, not as a side
    effect of moving it.

    Either position may be the wildcard ``"*"``. This exists for the base
    vocabulary, which has to constrain one end of an edge while knowing nothing
    about the other: ``("*", "photo")`` says anything may have a photo without
    the engine enumerating a domain's entity types, and ``("app", "*")`` says an
    app manages things without the engine knowing which. A domain may narrow a
    base rule by redeclaring it under the same name.

    A wildcard is not a fourth state -- it is a pair like any other, and the
    three states above are unaffected.
    """

    name: str
    allowed_endpoints: Optional[Tuple[Tuple[str, str], ...]] = None

    def permits(self, from_type: str, to_type: str) -> bool:
        if self.allowed_endpoints is None:
            return True
        return any(
            (allowed_from in ("*", from_type)) and (allowed_to in ("*", to_type))
            for allowed_from, allowed_to in self.allowed_endpoints
        )


class DomainValidationError(ValueError):
    """A write used vocabulary the domain does not declare."""


# --- Base vocabulary ---------------------------------------------------------
# Two concepts are engine-level, not house knowledge, and every domain inherits
# them. Declaring either inside a domain would force each new domain to
# redeclare it and leave the engine unable to reason about them generically.
#
# **Attachments.** The blobs table, blob sync and BlobType already live in the
# engine; the vocabulary for *reaching* a blob belongs here too. A vehicle
# collection, a boat and a server rack all have photos. The rule, engine-wide: *an entity that
# carries a blob is an attachment entity, and top-level `content.blob_id` is the
# only link to the blobs table.* The entity type says what kind of document it
# is, so no boolean "this has a blob" flag is needed -- the type IS the flag. No
# relationship ever points at a blob; relationships only name the attachment's
# role (ADR-013 §3).
#
# **Apps.** An `app` is an external system that runs or controls things --
# Alexa, Home Assistant, Vantage, a vendor's own scheduler -- and `manages`
# records what it runs. That is how provenance for automation is expressed
# without an ever-growing source_type enum (ADR-013 §4), and it is not specific
# to houses: any domain has systems acting on its entities.
#
# Base provides the mechanism and the universal types. A domain may *extend*
# the attachment set (the house adds `manual` for an appliance PDF; a vehicles
# domain might add `service_record`) and may *narrow* any base rule by redeclaring it
# under the same name.
BASE_ATTACHMENT_TYPES: Tuple[str, ...] = ("photo",)

BASE_ENTITY_TYPES: Tuple[str, ...] = BASE_ATTACHMENT_TYPES + ("app",)

BASE_RELATIONSHIP_RULES: Tuple[RelationshipRule, ...] = (
    # Wildcards, because the base genuinely cannot name the other endpoint:
    # anything may be photographed, and an app may manage anything. A domain
    # that wants tighter rules redeclares these by name.
    RelationshipRule(name="has_photo", allowed_endpoints=(("*", "photo"),)),
    RelationshipRule(name="manages", allowed_endpoints=(("app", "*"),)),
)


@dataclass(frozen=True)
class DomainManifest:
    """Everything the engine needs to know about a domain's vocabulary."""

    name: str
    entity_types: FrozenSet[str]
    source_types: FrozenSet[str]
    relationship_rules: Mapping[str, RelationshipRule]
    # Entity types that carry a blob via top-level content.blob_id. Always
    # includes BASE_ATTACHMENT_TYPES; a domain may add its own.
    attachment_types: FrozenSet[str] = frozenset(BASE_ATTACHMENT_TYPES)

    @property
    def relationship_types(self) -> FrozenSet[str]:
        return frozenset(self.relationship_rules)

    def carries_blob(self, entity_type: str) -> bool:
        """True if this entity type is an attachment (ADR-013 §3).

        The single question the engine needs to ask about blobs, and the reason
        the attachment set is base rather than domain: blob handling can be
        written once without knowing what a house is.
        """
        return entity_type in self.attachment_types

    def check_entity_type(self, value: str) -> None:
        if value not in self.entity_types:
            raise DomainValidationError(
                f"unknown entity_type {value!r} for domain {self.name!r}; "
                f"declared types are {sorted(self.entity_types)}"
            )

    def check_source_type(self, value: str) -> None:
        if value not in self.source_types:
            raise DomainValidationError(
                f"unknown source_type {value!r} for domain {self.name!r}; "
                f"declared types are {sorted(self.source_types)}"
            )

    def check_relationship_type(self, value: str) -> None:
        if value not in self.relationship_rules:
            raise DomainValidationError(
                f"unknown relationship_type {value!r} for domain {self.name!r}; "
                f"declared types are {sorted(self.relationship_rules)}"
            )

    def check_relationship(
        self, relationship_type: str, from_type: Optional[str], to_type: Optional[str]
    ) -> None:
        """Validate an edge against its declared endpoint constraint.

        `from_type`/`to_type` may be None when an endpoint is not held locally —
        an edge can legitimately reference an entity that has not synced yet.
        Endpoint checking is skipped in that case rather than failing: the
        alternative is rejecting writes because of arrival order, which is not a
        property of the data.
        """
        self.check_relationship_type(relationship_type)
        if from_type is None or to_type is None:
            return
        rule = self.relationship_rules[relationship_type]
        if not rule.permits(from_type, to_type):
            raise DomainValidationError(
                f"{relationship_type!r} does not permit {from_type!r} -> {to_type!r} "
                f"in domain {self.name!r}; allowed: {sorted(rule.allowed_endpoints)}"
            )


def build_manifest(
    *,
    name: str,
    entity_types: Iterable[str],
    source_types: Iterable[str],
    relationship_rules: Iterable[RelationshipRule],
    attachment_types: Iterable[str] = (),
) -> DomainManifest:
    """Assemble a manifest, merging the base vocabulary into the domain's.

    The domain declares what is specific to it. Attachments and apps come from
    the base and do not need declaring -- a domain that wrote out `photo` and
    `has_photo` itself would be re-stating engine mechanism as house knowledge.

    `attachment_types` *extends* the base set: the house adds `manual` because
    an appliance PDF is a house-flavoured document, while `photo` is universal.
    Anything listed here is also an entity type, so a domain need not repeat it.

    A domain relationship rule *overrides* a base rule of the same name, so a
    domain can narrow `manages` from "an app manages anything" to the specific
    endpoints it actually allows. Narrowing is the only reason to redeclare;
    silently widening a base rule would defeat the point of having one.
    """
    attachments = frozenset(BASE_ATTACHMENT_TYPES) | {str(t) for t in attachment_types}

    rules = {str(rule.name): rule for rule in BASE_RELATIONSHIP_RULES}
    rules.update({str(rule.name): rule for rule in relationship_rules})

    return DomainManifest(
        name=name,
        entity_types=(
            frozenset(str(t) for t in entity_types)
            | frozenset(BASE_ENTITY_TYPES)
            | attachments
        ),
        source_types=frozenset(str(t) for t in source_types),
        relationship_rules=rules,
        attachment_types=attachments,
    )
