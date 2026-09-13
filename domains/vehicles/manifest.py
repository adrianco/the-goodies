"""Vehicles vocabulary — the second domain, and the proof (ADR-012).

What a garage full of bikes and cars needs the graph to say: which vehicles
exist, what is fitted to them, which tools and spares are on the shelf, where
each thing is kept, what was bought when and from whom, and what was done to
each machine over its life. A car's history is *exactly* the temporal model:
a part's ``fitted_to`` edge is an interval, a service is an event dated when
it happened, and ``at`` answers "what was on the bike last spring".

First pass. The vocabulary is deliberately small and will be iterated; what
matters now is that it is a manifest and nothing else -- no engine code, no
schema, no client change beyond pointing at it.

Base vocabulary (``photo`` / ``has_photo``, ``app`` / ``manages``) is inherited
and NOT restated here; see ``inbetweenies/domain.py``.
"""

from inbetweenies.domain import DomainTool, RelationshipRule, Walk, build_manifest

from pathlib import Path

from . import tools as vehicle_tools

# --- Entity types ---------------------------------------------------------
ENTITY_TYPES = [
    # The machines. `content.kind` says which: car, motorcycle, bicycle,
    # ebike, trailer... one type, because everything below applies to all
    # of them alike (parts, tools, purchases, service).
    "vehicle",
    # A component fitted to a vehicle now or once: tyres, chain, battery,
    # brake pads. Fitting is an interval edge (`fitted_to`), so a part's life
    # across vehicles -- and a vehicle's parts at any instant -- is history.
    "part",
    # Workshop equipment: torque wrench, stand, charger. Belongs to the
    # collection, not to a vehicle; `compatible_with` says what it serves.
    "tool",
    # Where things are kept: a garage bay, a shelf, a shed. The house domain
    # has rooms; this is the vehicles' own notion of place. A cross-domain
    # reference to a house room is ADR-012 §4, not this.
    "location",
    # A purchase: what was paid, to whom, when. Its own entity so one purchase
    # can cover several items and carry its own invoice.
    "purchase",
    # One maintenance event: a service, a repair, an inspection, dated when it
    # happened (`content.performed_at`) with mileage/hours and what was done.
    "service_record",
    # A known problem with a vehicle or part, open until a service resolves it.
    "issue",
    # Free text.
    "note",
]

# --- Source types ---------------------------------------------------------
SOURCE_TYPES = [
    "manual",     # human-entered, e.g. during a vehicle walk
    "imported",   # from a spreadsheet, dealer export, service portal
    "telemetry",  # from the vehicle itself (OBD, an app's export)
    "generated",  # seed data
]

# --- Relationship types ---------------------------------------------------
RELATIONSHIP_RULES = [
    # Where a thing IS. Same word as the house uses for the same idea.
    RelationshipRule(
        name="located_in",
        allowed_endpoints=(
            ("vehicle", "location"),
            ("part", "location"),
            ("tool", "location"),
            ("location", "location"),
        ),
    ),
    # A part is on a vehicle. THE interval edge of this domain: end it when
    # the part comes off, start a new one when its replacement goes on.
    RelationshipRule(name="fitted_to", allowed_endpoints=(("part", "vehicle"),)),
    # The new part took the old one's place.
    RelationshipRule(name="replaced", allowed_endpoints=(("part", "part"),)),
    # A spare or a tool that serves a vehicle without being fitted to it.
    RelationshipRule(
        name="compatible_with",
        allowed_endpoints=(("part", "vehicle"), ("tool", "vehicle")),
    ),
    # An item was bought in a purchase.
    RelationshipRule(
        name="purchased_via",
        allowed_endpoints=(("vehicle", "purchase"), ("part", "purchase"), ("tool", "purchase")),
    ),
    # A service was done to a vehicle (or to a part off the vehicle).
    RelationshipRule(name="service_for", allowed_endpoints=(("service_record", "vehicle"), ("service_record", "part"))),
    # A service used a tool or fitted a part.
    RelationshipRule(name="used", allowed_endpoints=(("service_record", "tool"), ("service_record", "part"))),
    # An issue concerns a vehicle or part, and a service closed it.
    RelationshipRule(name="issue_for", allowed_endpoints=(("issue", "vehicle"), ("issue", "part"))),
    RelationshipRule(name="resolved_by", allowed_endpoints=(("issue", "service_record"),)),
    # Documentation and receipts. `invoice` is this domain's attachment type
    # (a PDF), the counterpart of the house's `manual`; `note` is text.
    RelationshipRule(
        name="documented_by",
        allowed_endpoints=(
            ("vehicle", "note"), ("part", "note"), ("tool", "note"),
            ("service_record", "note"), ("issue", "note"),
            ("purchase", "invoice"), ("service_record", "invoice"), ("vehicle", "invoice"),
        ),
    ),
    # Base `manages` narrowed: an app (a maker's telematics app, a service
    # portal) manages vehicles.
    RelationshipRule(name="manages", allowed_endpoints=(("app", "vehicle"),)),
]

# --------------------------------------------------------------------------- #
# Merge rules (ADR-005 §2 rung 2): the domain facts a three-way merge cannot
# know. An odometer only goes up; two readings merge to the higher one.
# --------------------------------------------------------------------------- #

def merge_vehicle(base, local, remote):
    readings = [d["odometer"] for d in (local, remote) if isinstance(d.get("odometer"), (int, float))]
    return {"odometer": max(readings)} if readings else {}


MERGE_RULES = {"vehicle": merge_vehicle}

# --------------------------------------------------------------------------- #
# Tools (ADR-012 §2). Every one but the history is a declarative walk -- the
# engine runs them; this file only says which edge to follow and what to keep.
# --------------------------------------------------------------------------- #

TOOLS = (
    DomainTool(
        name="get_vehicles_in_location",
        description="Vehicles kept in a location (a bay, a shed, a shelf).",
        anchor="location_id", anchor_types=("location",),
        walk=(Walk("located_in", "incoming", ("vehicle",)),),
        result_key="vehicles",
    ),
    DomainTool(
        name="get_parts_on_vehicle",
        description="Parts currently fitted to a vehicle; with `at`, the parts fitted then.",
        anchor="vehicle_id", anchor_types=("vehicle",),
        walk=(Walk("fitted_to", "incoming", ("part",)),),
        result_key="parts",
    ),
    DomainTool(
        name="get_tools_for_vehicle",
        description="Workshop tools and spares declared compatible with a vehicle.",
        anchor="vehicle_id", anchor_types=("vehicle",),
        walk=(Walk("compatible_with", "incoming", ("tool", "part")),),
        result_key="items",
    ),
    DomainTool(
        name="get_items_in_location",
        description="Parts and tools stored in a location.",
        anchor="location_id", anchor_types=("location",),
        walk=(Walk("located_in", "incoming", ("part", "tool")),),
        result_key="items",
    ),
    DomainTool(
        name="get_service_records",
        description="Every service, repair and inspection recorded for a vehicle.",
        anchor="vehicle_id", anchor_types=("vehicle",),
        walk=(Walk("service_for", "incoming", ("service_record",)),),
        result_key="service_records",
    ),
    DomainTool(
        name="get_open_issues",
        description="Issues still open on a vehicle (content.status == open).",
        anchor="vehicle_id", anchor_types=("vehicle",),
        walk=(Walk("issue_for", "incoming", ("issue",), where={"status": "open"}),),
        result_key="issues",
    ),
    DomainTool(
        name="get_purchases_for",
        description="The purchase(s) an item -- vehicle, part or tool -- was bought in.",
        anchor="item_id", anchor_types=("vehicle", "part", "tool"),
        walk=(Walk("purchased_via", "outgoing", ("purchase",)),),
        result_key="purchases",
    ),
    DomainTool(
        name="get_vehicle_history",
        description=(
            "A vehicle's life in date order: purchase, every service, every part "
            "fitted or removed, every issue opened or resolved. With `at`, the "
            "history as it was known then."
        ),
        anchor="vehicle_id", anchor_types=("vehicle",),
        handler=vehicle_tools.get_vehicle_history,
    ),
)

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

VEHICLES = build_manifest(
    name="vehicles",
    entity_types=ENTITY_TYPES,
    source_types=SOURCE_TYPES,
    relationship_rules=RELATIONSHIP_RULES,
    # `photo` is base; `invoice` is this domain's own attachment (a PDF).
    attachment_types=("invoice",),
    merge_rules=MERGE_RULES,
    tools=TOOLS,
    skills={"vehicle-walk": _SKILLS_DIR / "vehicle-walk" / "SKILL.md"},
)
