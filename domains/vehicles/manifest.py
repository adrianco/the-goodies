"""Vehicles vocabulary — a walk-first knowledge history graph (ADR-016).

Deliberately a *capture* vocabulary. The owner's direction is that the right
entities cannot be designed at a desk: do real walks of each kind — a new
Mini Cooper SE with an app feed, the 2010 Roadster with its OVMS box, the E30
Lemons race car with no single VIN, the family's 2009 Boxster S — and promote
what recurs with structure afterwards, the way ADR-013 cleaned up the house
from live data. So everything a walk captures is one of three things:

* a **thing** — `vehicle`, `part`, `tool`;
* a **place** — `location`, which may well not be the house;
* **something that happened to a thing on a date, with evidence** — one
  `event` type with an open `kind`.

What is not loose is the temporal spine: `event.when`, `fitted_to`'s interval
and `located_in`'s interval are what make "what was on the car in March" and
"where was it during the restoration" answerable, and they are set from day one.

This is a knowledge history graph, not a data logger (ADR-016 §1.2): fuel and
charging purchases are events; trips are not unless they are named events;
telemetry is summarised into logbook-grade facts before it is written.

Base vocabulary (``photo`` / ``has_photo``, ``app`` / ``manages``) is inherited
and NOT restated here; see ``inbetweenies/domain.py``.
"""

from pathlib import Path

from inbetweenies.domain import DomainTool, RelationshipRule, Walk, build_manifest

from . import tools as vehicle_tools

# --- Entity types ---------------------------------------------------------
ENTITY_TYPES = [
    # The machine, across its whole life -- evaluated, owned, sold, remembered.
    # `content.kind`: car / ev / motorcycle / bicycle / race_car / trailer ...
    # `content.identity`: whichever numbers exist -- VIN, frame number,
    # registration, a race logbook number. A race car may have several over
    # its life (the shell is a part; see the Lemons seed). `content.aliases`
    # are the nicknames. `content.spec` is the free-form factory /
    # as-delivered specification. `content.status`: evaluating / owned /
    # sold / not_bought. `content.country` (US / UK / ...) and, inside
    # `identity`, `registration_country` and a US `state`: a UK car's working
    # identity is its registration mark and its admin is MOT / V5C / tax / SORN;
    # a US car's is title, state registration and (in California) smog.
    # Units are per vehicle (`odometer_unit`: mi / km / hours) and money is
    # per event (`currency`), so a collection can straddle both countries.
    "vehicle",
    # A component with identity: fitted to a vehicle for a period, or on a
    # shelf. An asset, not a consumable, because modifications and
    # restorations care about the displaced original. A race car's shell and
    # its engines are parts.
    "part",
    # Workshop equipment.
    "tool",
    # Where things are kept, for a period. `content.kind`: home_garage /
    # storage_unit / shop / yard / trailer / in_transit; an address. May be
    # off-site, and in another country (`content.country`); a house room is an
    # optional ADR-017 reference, never required.
    "location",
    # Something that happened to a vehicle on a date. `content.kind` is OPEN:
    # evaluation, purchase, transfer, service, repair, modification,
    # inspection, fuel, charge, odometer, software_update, recall,
    # condition_report, track_day, race, rally, show, road_trip, sale,
    # sighting ... plus `when` (ISO-8601), `odometer` / `hours`, `cost`,
    # `currency` (USD / GBP / ...), `where` (text), free `text`, and `source`
    # (walk / feed). Volumes carry their unit (`gallons` or `litres`).
    "event",
    # Transcribed speech and free text. The walk's transcript is a note.
    "note",
]

# --- Source types ---------------------------------------------------------
SOURCE_TYPES = [
    "manual",     # human-entered, e.g. during a vehicle walk
    "imported",   # from a spreadsheet, a folder of receipts, a dealer export
    "telemetry",  # summarised from the vehicle or its app (OVMS, the MINI app)
    "generated",  # seed data
]

# --- Relationship types ---------------------------------------------------
RELATIONSHIP_RULES = [
    # Where a thing IS, for a period. Same word as the house, same meaning.
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
    # An event is about a vehicle (occasionally about a part on the shelf).
    RelationshipRule(
        name="happened_to",
        allowed_endpoints=(("event", "vehicle"), ("event", "part")),
    ),
    # What an event touched: the parts a service fitted, the original a
    # modification displaced, the tool a repair used, the place it happened.
    RelationshipRule(
        name="involved",
        allowed_endpoints=(("event", "part"), ("event", "tool"), ("event", "location")),
    ),
    # Evidence and text. `document` is this domain's attachment type (a PDF or
    # scan: invoice, build sheet, title, certificate, setup sheet, period
    # photo); `note` is text.
    RelationshipRule(
        name="documented_by",
        allowed_endpoints=(
            ("vehicle", "note"), ("vehicle", "document"),
            ("part", "note"), ("part", "document"),
            ("tool", "note"), ("tool", "document"),
            ("event", "note"), ("event", "document"),
            ("location", "note"), ("location", "document"),
        ),
    ),
    # Base `manages` narrowed: an app (the MINI app, OVMS, a service portal)
    # manages vehicles. Its writes are events with source_type telemetry.
    RelationshipRule(name="manages", allowed_endpoints=(("app", "vehicle"),)),
]

# --------------------------------------------------------------------------- #
# Merge rules (ADR-005 §2 rung 2): the domain facts a three-way merge cannot
# know. An odometer only goes up; two readings merge to the higher one.
# Nothing else until the walks show a concurrent-edit pattern.
# --------------------------------------------------------------------------- #

def merge_vehicle(base, local, remote):
    readings = [d["odometer"] for d in (local, remote) if isinstance(d.get("odometer"), (int, float))]
    return {"odometer": max(readings)} if readings else {}


MERGE_RULES = {"vehicle": merge_vehicle}

# --------------------------------------------------------------------------- #
# Tools (ADR-012 §2). Small, and none presumes structure the walks have not
# revealed: the walks are declarative; the two history tools are handlers.
# `get_modifications`, `get_current_spec`, `get_service_due` arrive when their
# event kinds are promoted (ADR-016 §4).
# --------------------------------------------------------------------------- #

TOOLS = (
    DomainTool(
        name="get_vehicles_in_location",
        description="Vehicles kept in a location (a garage, a storage yard, a trailer); with `at`, the vehicles kept there then.",
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
        description="Parts and tools stored in a location; with `at`, what was there then.",
        anchor="location_id", anchor_types=("location",),
        walk=(Walk("located_in", "incoming", ("part", "tool")),),
        result_key="items",
    ),
    DomainTool(
        name="get_events",
        description=(
            "Events recorded for a vehicle, oldest first. Filter by `kind` "
            "(evaluation, purchase, service, modification, fuel, charge, race, "
            "sale, sighting, ...), and by `since` / `until` on the event's own date."
        ),
        anchor="vehicle_id", anchor_types=("vehicle",),
        handler=vehicle_tools.get_events,
        extra_params={
            "kind": {"type": "string", "description": "Only events of this kind"},
            "since": {"type": "string", "description": "Only events on or after this date (ISO-8601)"},
            "until": {"type": "string", "description": "Only events on or before this date (ISO-8601)"},
        },
    ),
    DomainTool(
        name="where_is",
        description=(
            "Where a part or tool is right now (or `at` an instant): fitted to a "
            "vehicle -- and where that vehicle is -- or on a shelf somewhere, or unknown."
        ),
        anchor="item_id", anchor_types=("part", "tool"),
        handler=vehicle_tools.where_is,
    ),
    DomainTool(
        name="get_part_history",
        description=(
            "A part's life: every vehicle it was fitted to and when, every place it "
            "was kept, and the events that happened to those vehicles while it was on "
            "them -- so 'how many races did that gearbox run' is a count."
        ),
        anchor="part_id", anchor_types=("part",),
        handler=vehicle_tools.get_part_history,
        extra_params={"kind": {"type": "string", "description": "Only count/return events of this kind"}},
    ),
    DomainTool(
        name="get_vehicle_history",
        description=(
            "A vehicle's whole life in date order: every event, every part "
            "fitted or removed, every move between locations. With `at`, the "
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
    # `photo` is base; `document` is this domain's own attachment (PDF/scan).
    attachment_types=("document",),
    merge_rules=MERGE_RULES,
    tools=TOOLS,
    skills={"vehicle-walk": _SKILLS_DIR / "vehicle-walk" / "SKILL.md"},
)
