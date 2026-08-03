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
    """

    name: str
    allowed_endpoints: Optional[Tuple[Tuple[str, str], ...]] = None

    def permits(self, from_type: str, to_type: str) -> bool:
        if self.allowed_endpoints is None:
            return True
        return (from_type, to_type) in self.allowed_endpoints


class DomainValidationError(ValueError):
    """A write used vocabulary the domain does not declare."""


@dataclass(frozen=True)
class DomainManifest:
    """Everything the engine needs to know about a domain's vocabulary."""

    name: str
    entity_types: FrozenSet[str]
    source_types: FrozenSet[str]
    relationship_rules: Mapping[str, RelationshipRule]

    @property
    def relationship_types(self) -> FrozenSet[str]:
        return frozenset(self.relationship_rules)

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
) -> DomainManifest:
    """Assemble a manifest, normalising the vocabulary to plain strings."""
    return DomainManifest(
        name=name,
        entity_types=frozenset(str(t) for t in entity_types),
        source_types=frozenset(str(t) for t in source_types),
        relationship_rules={str(rule.name): rule for rule in relationship_rules},
    )
