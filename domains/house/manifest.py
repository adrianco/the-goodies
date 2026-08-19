"""House vocabulary — declared (ADR-013).

This was *derived* from `EntityType`, `SourceType` and the endpoint table inside
`EntityRelationship.is_valid_for_entities`, so ADR-012's move out of the schema
could be proved byte-identical across all 2016 (relationship_type, from_type,
to_type) triples. That job is done, and ADR-013 changes what the vocabulary
*says* — so deriving it is no longer possible or wanted. This file is now the
source of truth; the enums it came from are legacy.

The two changes worth knowing when reading this:

* `located_in` and `part_of` were conflated. HomeKit used `part_of` for spatial
  containment while the importer used it for composition, so one word carried
  two meanings and the two relationships looked redundant when they were not.
  They are now split: `located_in` is where a thing *is*; `part_of` is what a
  thing is *a component of*.
* Several rules were previously unenforceable — declared with no permitted
  endpoints, so every attempt to create them failed. Where that was an
  oversight it is now `None` (explicitly unconstrained); where the relationship
  was genuinely redundant, it is gone.
"""

from inbetweenies.domain import RelationshipRule, build_manifest

# --- Entity types ---------------------------------------------------------
# Live counts from the 2026-08-03 production backup are in README.md. The
# automation trio (automation / schedule / procedure) has no instances yet: the
# Vantage system at one site and Home Assistant at the other are real but not
# yet described. Undescribed, not absent — see ADR-013.
ENTITY_TYPES = [
    "home",
    "zone",
    "room",
    "device",
    "door",
    "window",
    "note",
    "procedure",
    "schedule",
    "automation",
]

# --- Source types ---------------------------------------------------------
# HOW A RECORD REACHED THE GRAPH — nothing more. Deliberately not the system
# that runs an automation: that is a fact about the world, stays true however
# the record arrived, and belongs on an `app` entity (ADR-013 §4). An
# automation imported from a Home Assistant backup but actually executed by
# Alexa is `imported` and Alexa-run; one field cannot say both.
#
# Left at five on purpose. Extending this per automation vendor — alexa,
# google_home, smartthings, and every IoT app with its own scheduler — is a
# list that never stops growing.
SOURCE_TYPES = [
    "homekit",
    "matter",
    "manual",
    "imported",
    "generated",
]

# --- Relationship types ---------------------------------------------------
# `allowed_endpoints=None` means explicitly unconstrained. An empty tuple means
# "nothing is permitted", which is what made contained_in and depends_on
# uncreatable — see inbetweenies/domain.py::RelationshipRule.
RELATIONSHIP_RULES = [
    # -- Structure --------------------------------------------------------
    RelationshipRule(
        name="located_in",
        # Spatial containment: where a thing IS. The single containment
        # relationship since ADR-013; HomeKit's room->home edges moved here
        # from part_of.
        allowed_endpoints=(
            ("device", "room"),
            ("device", "zone"),
            ("room", "zone"),
            ("room", "home"),
            ("zone", "home"),
            ("door", "room"),
            ("window", "room"),
        ),
    ),
    RelationshipRule(
        name="part_of",
        # Composition: a thing is a COMPONENT of another. 104 live edges, all
        # device->device from the importer. Not containment — a component is
        # not "located in" its parent.
        allowed_endpoints=(("device", "device"),),
    ),
    RelationshipRule(
        name="connects_to",
        allowed_endpoints=(
            ("room", "room"),
            ("door", "room"),
            ("window", "room"),
        ),
    ),
    # -- Documentation and attachments ------------------------------------
    RelationshipRule(
        name="documented_by",
        # How a `manual` (a PDF) attaches -- the counterpart to the base
        # `has_photo`. The room-> and procedure->manual pairs come from the
        # Corfe install, which unlike Roland actually has PDFs: a pool guide
        # attached to the Swimming Pool room, and an instruction sheet for a
        # procedure. Both read correctly in this direction and only in this
        # direction; the reverse is what the migration flips.
        allowed_endpoints=(
            ("device", "manual"),
            ("room", "manual"),
            ("procedure", "manual"),
            ("device", "procedure"),
            ("device", "note"),
            ("room", "note"),
            ("home", "note"),
            ("door", "note"),
        ),
    ),
    RelationshipRule(
        name="procedure_for",
        allowed_endpoints=(("procedure", "device"), ("procedure", "room")),
    ),
    # NOTE: `has_photo` is NOT declared here. It is base vocabulary
    # (inbetweenies/domain.py), along with the `photo` entity type: blobs are
    # engine machinery and every domain has photos. Restating it here would make
    # engine mechanism look like house knowledge.
    # -- Control and automation -------------------------------------------
    # Undescribed at both sites so far. Retained and shaped to serve Vantage
    # (Roland) and Home Assistant (Corfe) alike — neither introduces a concept
    # these cannot express.
    RelationshipRule(
        name="controls",
        allowed_endpoints=(
            ("device", "device"),
            ("automation", "device"),
            ("schedule", "device"),
            ("schedule", "automation"),
        ),
    ),
    RelationshipRule(
        name="automates",
        allowed_endpoints=(
            ("automation", "device"),
            ("automation", "room"),
            ("schedule", "device"),
        ),
    ),
    RelationshipRule(
        name="triggered_by",
        allowed_endpoints=(
            ("automation", "device"),
            ("automation", "schedule"),
            ("schedule", "automation"),
        ),
    ),
    RelationshipRule(
        name="monitors",
        allowed_endpoints=(
            ("device", "device"),
            ("device", "room"),
            ("automation", "device"),
        ),
    ),
    RelationshipRule(
        name="depends_on",
        # Previously uncreatable (no endpoints declared). Unconstrained until
        # the automation is described and a real shape is known — ADR-013 §2.
        allowed_endpoints=None,
    ),
    # -- Apps and automation provenance ------------------------------------
    # An `app` entity per system — Alexa, Google Home, HomeKit, Vantage, Home
    # Assistant, a vendor's own scheduler — and `manages` edges to whatever it
    # runs. That is how an automation records which system executes it
    # (ADR-013 §4): unbounded without schema change, and it makes "what breaks
    # if this system goes away" a graph traversal rather than a text search.
    #
    # This is why `app` looked like a half-built feature: one app entity exists
    # and nothing links to it. It is the right mechanism, declared before the
    # automations it was meant to describe.
    RelationshipRule(
        name="manages",
        # Base declares `manages` as app -> anything, because the engine cannot
        # know a domain's entity types. The house *narrows* it to what an app
        # actually manages here. Narrowing a base rule is the intended use of
        # redeclaring one; widening it would defeat the point of a base rule.
        allowed_endpoints=(
            ("app", "device"),
            ("app", "automation"),
            ("app", "schedule"),
            ("app", "room"),
        ),
    ),
    # NOTE: `controlled_by_app` is deliberately absent (ADR-013 §4). It was the
    # exact inverse of `manages` — device->app against app->device — which is
    # the same one-thing-two-ways defect as the located_in/part_of conflation
    # this ADR exists to fix. Both were unused, so there was no cost to
    # choosing. `manages` wins: the app is the actor, so it reads as the
    # subject.
    # NOTE: `has_blob` is deliberately absent (ADR-013 §3), replaced by the
    # base `has_photo`. "Blob" is a storage word, not a domain word, and the
    # edge never pointed at a blob anyway.
    # NOTE: `contained_in` is deliberately absent (ADR-013 §1). It duplicated
    # located_in, declared no endpoints, and so was never creatable. No data
    # uses it and none could.
]

HOUSE = build_manifest(
    name="house",
    entity_types=ENTITY_TYPES,
    source_types=SOURCE_TYPES,
    relationship_rules=RELATIONSHIP_RULES,
    # `photo` is base; `manual` is the house's own attachment type -- an
    # appliance PDF. Both carry a blob via top-level content.blob_id, and
    # listing `manual` here is what tells the engine so.
    attachment_types=("manual",),
)
