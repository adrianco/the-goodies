#!/usr/bin/env python3
"""
Populate FunkyGibbon MCP graph database with comprehensive test data.

Creates a realistic smart home knowledge graph with:
- Multiple homes with rooms and zones
- Various device types with relationships
- Procedures and manuals for devices
- Automations and schedules
- Notes and documentation
- **A recorded past** (see "The house has a history" below)

This is the fixture the live-server end-to-end suite runs against
(``conftest.py`` seeds it before starting a real ``funkygibbon`` process), so
what it does NOT contain is a hole in that suite's coverage rather than a
missing demo nicety.

The house has a history (ADR-004)
---------------------------------
Until this section existed, every entity here was v1 and every edge was a
single open interval whose ``valid_from`` came from the column default — so all
47 edges were stamped within about 23 microseconds of the seed's own run
instant. The whole house sprang into existence "now", which meant the fixture
could not exercise one line of the temporal model: no edge was ever moved or
ended, no entity was ever revised or deleted, and ``snapshot(any past T)`` was
either empty or identical to the present. Every v3 code path was unreachable
from end to end, and the one case the fixture did cover — a house with no past —
is precisely the case the pre-v3 code already got right.

Four episodes are now recorded, each isolating one mechanism:

===========================  ==========================================
what                         which v3 feature it makes observable
===========================  ==========================================
the blower moved rooms       interval edges: two tiling intervals on one
                             logical edge id, so snapshot(2024) and
                             snapshot(now) disagree about where it is
HomeKit stopped managing     a retired edge: ``valid_to`` set, the row
the oven                     kept rather than deleted
the thermostat was renamed   entity version history: a second version row
                             with ``parent_versions`` and ``is_latest``
                             moved onto it
the motion sensor was        a tombstone, plus the edge ending that goes
removed                      with it
===========================  ==========================================

**The dates are fixed constants, not offsets from today.** A fixture whose
timeline drifts with the wall clock cannot be asserted against: the test that
wants "the blower was in the office on 2024-06-01" has to recompute the
expected answer using the same arithmetic as the code under test, which is how
a test ends up agreeing with a bug. See ``TIMELINE`` below.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from itertools import count
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

from inbetweenies.models import Base, Entity, EntityType, SourceType, EntityRelationship, RelationshipType, Blob, BlobType, BlobStatus


def _demo_bytes(tag: str) -> str:
    """A few deterministic bytes, base64-encoded, standing in for a real file.

    The seed used to write a made-up ``blob_id`` pointing at no row at all, so a
    freshly seeded database had dangling blob references before anyone touched
    it. Real bytes mean the migration's extractor creates a real blob and the
    integrity check passes.
    """
    import base64
    return base64.b64encode(f"demo-blob:{tag}".encode()).decode()



# --------------------------------------------------------------------------- #
# The recorded timeline (ADR-004 §2 — the valid-time axis)
#
# Fixed dates, deliberately. These are the instants a test asserts against
# ("the blower was in the office on 2024-06-01"), and a fixture that computes
# them from `now` forces every test to redo the same arithmetic as the code
# under test — which is how a test ends up agreeing with a bug rather than
# catching it. All of them are safely in the past, and they stay that way.
#
# They are also *client edit times*, not server apply times: this is the axis
# an as-of query runs on, and the whole point is that it is independent of when
# this script happens to run.
# --------------------------------------------------------------------------- #
def _utc(year, month, day, hour=12):
    return datetime(year, month, day, hour, 0, tzinfo=timezone.utc)


TIMELINE = {
    # The earliest fact the graph records. Everything the seed creates without
    # an explicit date is "current" and carries the run instant instead.
    "history_begins": _utc(2024, 1, 15),
    # The PVFY air handler: installed upstairs, later relocated to the garage.
    # This pair is the headline ADR-004 case — one logical edge, two intervals.
    "blower_installed": _utc(2024, 3, 10),
    "blower_moved": _utc(2025, 6, 1),
    # HomeKit stopped managing the oven when it moved to the vendor app.
    "oven_left_homekit": _utc(2025, 9, 15),
    # The Nest was renamed when a second thermostat arrived and "Thermostat"
    # stopped being unambiguous.
    "thermostat_renamed": _utc(2025, 11, 20),
    # The hallway motion sensor failed and was removed.
    "sensor_removed": _utc(2026, 2, 5),
}


def _version_at(moment: datetime, user_id: str, counter: int) -> str:
    """A version string stamped at `moment` rather than at now.

    ``Entity.create_version`` reads the wall clock, which is right for a live
    edit and wrong for seeded history: a 2024 revision carrying a 2026 version
    string would sort as the newest edit of its entity, so `is_latest` (and
    anything that re-derives it, such as the migration's backfill) would name
    the wrong row as current. The format is PROTOCOL.md §2's exactly —
    ``{utc-iso8601}-{counter:06d}-{user_id}`` — because lexical order equals
    chronological order only while the timestamp prefix is fixed-width UTC.
    """
    return f"{moment.isoformat()}-{counter:06d}-{user_id}"


# Default database URL - can be overridden by environment variable
# Use 'or' to handle empty string case
DATABASE_URL = os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./funkygibbon.db"


class GraphPopulator:
    """Populate graph database with realistic smart home data"""

    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
        self.engine = create_async_engine(db_url, echo=False)
        self.session_maker = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.entities = {}  # Store created entities by key for relationships
        # Disambiguates two revisions stamped at the same instant (PROTOCOL.md
        # §2's counter field). Per-populator so a re-run is reproducible.
        self._revision_counter = count(1)
        # ADR-002 §2's replication axis. Dense and monotonic in write order,
        # which for this script IS apply order: one transaction, one writer.
        self._seq_counter = count(1)

    async def setup_database(self):
        """Create tables and clear existing data"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            print("🗑️  Clearing existing graph data...")
            # Clear in reverse dependency order
            await conn.execute(text("DELETE FROM entity_relationships"))
            await conn.execute(text("DELETE FROM entities"))
            # Try to clear blobs table if it exists
            try:
                await conn.execute(text("DELETE FROM blobs"))
            except:
                pass  # Table might not exist yet
            print("✅ Database ready for population")

    async def create_entity(self, session: AsyncSession, entity_type: EntityType,
                          name: str, content: dict, key: str = None,
                          at: datetime = None) -> Entity:
        """Create and store an entity.

        ``at`` backdates the version string and timestamps to when the entity
        actually came into existence. It matters for anything that is later
        revised: version strings sort lexically by their UTC prefix
        (PROTOCOL.md §2), so a 2024 device stamped with today's clock and then
        tombstoned in the past produces a *tombstone that sorts older than the
        creation it supersedes*. `is_latest` would still be written correctly
        here, but everything that re-derives it — the migration's backfill, and
        conflict resolution comparing version strings — would name the wrong
        row as current.

        Omitted means "created when the seed ran", which is right for the
        present-tense bulk of this fixture.
        """
        entity = Entity(
            id=str(uuid4()),
            version=(_version_at(at, "populate-script", next(self._revision_counter))
                     if at is not None else Entity.create_version("populate-script")),
            entity_type=entity_type,
            name=name,
            content=content,
            source_type=SourceType.GENERATED,
            user_id="populate-script",
            parent_versions=[],
            # ADR-002 §2: stamp the replication axis. The seed writes rows
            # straight to the session rather than through GraphRepository, so
            # nothing else assigns this — and an unstamped row is INVISIBLE to
            # every cursor-based delta, because `server_seq > :cursor` is NULL
            # for a NULL. A client that used the cursor path therefore synced
            # the entire house and received none of it, silently: no error, no
            # warning, just an empty page.
            #
            # A plain counter is the right allocator here. The seed writes in a
            # defined order in a single transaction, so "apply order" is exactly
            # its own sequence, and a fixed sequence keeps the fixture
            # reproducible run to run.
            server_seq=next(self._seq_counter),
            **({"created_at": at, "updated_at": at} if at is not None else {}),
        )
        session.add(entity)

        if key:
            self.entities[key] = entity

        return entity

    async def create_relationship(self, session: AsyncSession,
                                from_entity: Entity, to_entity: Entity,
                                rel_type: RelationshipType,
                                properties: dict = None,
                                edge_id: str = None,
                                valid_from: datetime = None,
                                valid_to: datetime = None) -> EntityRelationship:
        """Create one edge interval (ADR-004 §1).

        ``edge_id`` is what makes history expressible. The row's primary key is
        ``(id, valid_from)``: ``id`` is the LOGICAL edge, stable across every
        interval of its life, and ``valid_from`` picks the interval. Minting a
        fresh uuid per call — which is all this used to do — makes two intervals
        of the same edge look like two unrelated edges, so "the blower moved"
        becomes "the blower is in two rooms", which is the exact wrong answer
        the interval model exists to prevent.

        ``valid_from`` omitted means "true since the seed ran", which is right
        for the present-tense bulk of this fixture. Pass it to date a fact to
        when it actually happened.
        """
        relationship = EntityRelationship(
            id=edge_id or str(uuid4()),
            from_entity_id=from_entity.id,
            to_entity_id=to_entity.id,
            relationship_type=rel_type,
            properties=properties or {},
            user_id="populate-script",
            valid_from=valid_from or datetime.now(timezone.utc),
            valid_to=valid_to,
            # ADR-002 §2: one sequence over entities and edges (see
            # next_server_seq). The seed's counter is that sequence.
            server_seq=next(self._seq_counter),
        )
        session.add(relationship)
        return relationship

    async def retire_relationship(self, session: AsyncSession,
                                  relationship: EntityRelationship,
                                  at: datetime) -> EntityRelationship:
        """End an edge's open interval at `at` (ADR-004 §1).

        Ending is not deleting. The row stays, and every question about the
        period it covered still answers correctly — which is the difference
        between "the oven is not managed by HomeKit" and "the oven was never
        managed by HomeKit".
        """
        relationship.valid_to = at
        # Ending is a replicated change: re-stamp so a cursor client sees it.
        relationship.server_seq = next(self._seq_counter)
        return relationship

    async def revise_entity(self, session: AsyncSession, entity: Entity, *,
                            at: datetime, name: str = None,
                            content: dict = None, deleted: bool = False) -> Entity:
        """Append a new version of `entity`, dated `at` (PROTOCOL.md §2/§8).

        Entities are immutable: an edit is a new row, never an update. Two
        bookkeeping details this fixture has to get right by hand, because it
        writes to storage rather than going through the sync path that normally
        maintains them:

        * ``parent_versions`` carries the superseded version, so the DAG is
          walkable and a three-way merge could find a common ancestor.
        * ``is_latest`` moves to the new row. It is a stored fact rather than a
          derived one precisely so three different call sites cannot disagree
          about which version won — but that means a writer has to move it.

        ``deleted=True`` writes a tombstone: a version whose content carries
        ``deleted: true`` (§8), which is how a delete converges like any other
        edit instead of leaving a hole.
        """
        entity.is_latest = False

        new_content = dict(content if content is not None else (entity.content or {}))
        if deleted:
            new_content["deleted"] = True

        revision = Entity(
            id=entity.id,
            version=_version_at(at, "populate-script", next(self._revision_counter)),
            entity_type=entity.entity_type,
            name=name if name is not None else entity.name,
            content=new_content,
            source_type=entity.source_type,
            user_id="populate-script",
            parent_versions=[entity.version],
            is_latest=True,
            server_seq=next(self._seq_counter),
            created_at=at,
            updated_at=at,
        )
        session.add(revision)
        return revision

    async def backdate_predecessor(self, session: AsyncSession, entity: Entity, *,
                                   at: datetime, name: str = None,
                                   content: dict = None) -> Entity:
        """Give `entity` an older version it descends from.

        The inverse of :meth:`revise_entity`, and the safer direction for this
        fixture. Revising forward would change the entity's CURRENT name or
        content, and the current graph is what the rest of the suite —
        and `oook`, and the README's worked examples — already expect. Adding an
        ancestor instead leaves every present-tense answer byte-identical and
        gives the version DAG something to walk.

        The predecessor is written non-latest, and the existing row's
        ``parent_versions`` is pointed at it. Version strings sort lexically by
        their UTC prefix (PROTOCOL.md §2), so a backdated version is correctly
        ordered as the older one without anything having to re-derive it.
        """
        predecessor = Entity(
            id=entity.id,
            version=_version_at(at, "populate-script", next(self._revision_counter)),
            entity_type=entity.entity_type,
            name=name if name is not None else entity.name,
            content=dict(content if content is not None else (entity.content or {})),
            source_type=entity.source_type,
            user_id="populate-script",
            parent_versions=[],
            is_latest=False,
            server_seq=next(self._seq_counter),
            created_at=at,
            updated_at=at,
        )
        session.add(predecessor)
        entity.parent_versions = [predecessor.version]
        return predecessor

    async def populate(self):
        """Populate the database with comprehensive test data"""
        async with self.session_maker() as session:
            print("\n🏠 Creating Smart Home Graph...")

            # Create main home
            home = await self.create_entity(
                session, EntityType.HOME,
                "The Martinez Smart Home",
                {
                    "address": "456 Innovation Drive, Smart City, SC 90210",
                    "timezone": "America/Los_Angeles",
                    "floors": 2,
                    "square_feet": 2500
                },
                key="main_home"
            )

            # Create zones
            print("\n🗺️  Creating zones...")
            ground_floor = await self.create_entity(
                session, EntityType.ZONE,
                "Ground Floor",
                {"floor": 1, "description": "Main living areas"},
                key="ground_floor"
            )

            upper_floor = await self.create_entity(
                session, EntityType.ZONE,
                "Upper Floor",
                {"floor": 2, "description": "Bedrooms and office"},
                key="upper_floor"
            )

            outdoor = await self.create_entity(
                session, EntityType.ZONE,
                "Outdoor Areas",
                {"description": "Patio, garden, and garage"},
                key="outdoor"
            )

            # Create zone relationships
            await self.create_relationship(session, ground_floor, home, RelationshipType.PART_OF)
            await self.create_relationship(session, upper_floor, home, RelationshipType.PART_OF)
            await self.create_relationship(session, outdoor, home, RelationshipType.PART_OF)

            # Create rooms
            print("\n🚪 Creating rooms...")
            living_room = await self.create_entity(
                session, EntityType.ROOM,
                "Living Room",
                {"area": 350, "floor": 1, "features": ["fireplace", "bay_window"]},
                key="living_room"
            )

            kitchen = await self.create_entity(
                session, EntityType.ROOM,
                "Kitchen",
                {"area": 250, "floor": 1, "features": ["island", "pantry"]},
                key="kitchen"
            )

            dining_room = await self.create_entity(
                session, EntityType.ROOM,
                "Dining Room",
                {"area": 200, "floor": 1, "features": ["chandelier"]},
                key="dining_room"
            )

            master_bedroom = await self.create_entity(
                session, EntityType.ROOM,
                "Master Bedroom",
                {"area": 300, "floor": 2, "features": ["walk_in_closet", "ensuite"]},
                key="master_bedroom"
            )

            office = await self.create_entity(
                session, EntityType.ROOM,
                "Home Office",
                {"area": 150, "floor": 2, "features": ["built_in_shelves"]},
                key="office"
            )

            garage = await self.create_entity(
                session, EntityType.ROOM,
                "Garage",
                {"area": 400, "capacity": 2, "features": ["ev_charger", "workbench"]},
                key="garage"
            )

            # Room relationships
            await self.create_relationship(session, living_room, ground_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, kitchen, ground_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, dining_room, ground_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, master_bedroom, upper_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, office, upper_floor, RelationshipType.LOCATED_IN)
            await self.create_relationship(session, garage, outdoor, RelationshipType.LOCATED_IN)

            # Room to home relationships
            for room in [living_room, kitchen, dining_room, master_bedroom, office, garage]:
                await self.create_relationship(session, room, home, RelationshipType.PART_OF)

            # Create doors connecting rooms
            print("\n🚪 Creating doors and connections...")
            kitchen_dining_door = await self.create_entity(
                session, EntityType.DOOR,
                "Kitchen-Dining Door",
                {"type": "swinging", "material": "wood"},
                key="kitchen_dining_door"
            )

            await self.create_relationship(session, kitchen_dining_door, kitchen, RelationshipType.CONNECTS_TO)
            await self.create_relationship(session, kitchen_dining_door, dining_room, RelationshipType.CONNECTS_TO)
            await self.create_relationship(session, kitchen, dining_room, RelationshipType.CONNECTS_TO,
                                         {"via": "door", "accessibility": "wheelchair_accessible"})

            # Create devices
            print("\n📱 Creating devices...")

            # Living room devices
            tv = await self.create_entity(
                session, EntityType.DEVICE,
                "65\" Smart TV",
                {
                    "manufacturer": "Samsung",
                    "model": "QN90A",
                    "type": "entertainment",
                    "capabilities": ["power", "volume", "input", "apps"],
                    "network": "wifi",
                    "ip": "192.168.1.100"
                },
                key="tv"
            )

            thermostat = await self.create_entity(
                session, EntityType.DEVICE,
                "Smart Thermostat",
                {
                    "manufacturer": "Nest",
                    "model": "Learning Thermostat",
                    "type": "climate",
                    "capabilities": ["temperature", "humidity", "schedule", "eco_mode"],
                    "network": "wifi",
                    "ip": "192.168.1.101"
                },
                key="thermostat"
            )

            # Kitchen devices
            fridge = await self.create_entity(
                session, EntityType.DEVICE,
                "Smart Refrigerator",
                {
                    "manufacturer": "LG",
                    "model": "InstaView",
                    "type": "appliance",
                    "capabilities": ["temperature", "door_sensor", "inventory"],
                    "network": "wifi",
                    "ip": "192.168.1.102"
                },
                key="fridge"
            )

            oven = await self.create_entity(
                session, EntityType.DEVICE,
                "Smart Oven",
                {
                    "manufacturer": "Samsung",
                    "model": "Flex Duo",
                    "type": "appliance",
                    "capabilities": ["temperature", "timer", "preheat", "self_clean"],
                    "network": "wifi",
                    "ip": "192.168.1.103"
                },
                key="oven"
            )

            # Lighting
            living_room_lights = await self.create_entity(
                session, EntityType.DEVICE,
                "Living Room Lights",
                {
                    "manufacturer": "Philips",
                    "model": "Hue Go",
                    "type": "light",
                    "capabilities": ["power", "brightness", "color", "scenes"],
                    "count": 4,
                    "network": "zigbee",
                    "hub": "philips_hue_bridge"
                },
                key="living_room_lights"
            )

            # Security
            doorbell = await self.create_entity(
                session, EntityType.DEVICE,
                "Video Doorbell",
                {
                    "manufacturer": "Ring",
                    "model": "Doorbell Pro 2",
                    "type": "security",
                    "capabilities": ["video", "motion", "two_way_audio", "night_vision"],
                    "network": "wifi",
                    "ip": "192.168.1.104"
                },
                key="doorbell"
            )

            # Mitsubishi thermostat for kitchen area
            mitsubishi_thermostat = await self.create_entity(
                session, EntityType.DEVICE,
                "Mitsubishi PAR-42MAA Thermostat",
                {
                    "manufacturer": "Mitsubishi",
                    "model": "PAR-42MAAUB",
                    "type": "climate",
                    "capabilities": ["temperature", "fan_speed", "mode", "schedule", "remote_control"],
                    "network": "proprietary",
                    "location_notes": "Kitchen wall - controls air blower for kitchen, dining room, living room, bar and kitchen bathroom",
                    "remote_app": "Mitsubishi Comfort"
                },
                key="mitsubishi_thermostat"
            )

            # Air handler blower unit
            pvfy_blower = await self.create_entity(
                session, EntityType.DEVICE,
                "PVFY Air Handler Blower",
                {
                    "manufacturer": "Mitsubishi",
                    "model": "PVFY",
                    "type": "hvac",
                    "capabilities": ["heating", "cooling", "fan"],
                    "location_notes": "Closet in garage",
                    "serial_number": "See photo documentation"
                },
                key="pvfy_blower"
            )

            # Device location relationships
            await self.create_relationship(session, tv, living_room, RelationshipType.LOCATED_IN,
                                         {"position": "wall_mounted", "height": "eye_level"})
            await self.create_relationship(session, thermostat, living_room, RelationshipType.LOCATED_IN,
                                         {"position": "wall", "height": "5ft"})
            await self.create_relationship(session, fridge, kitchen, RelationshipType.LOCATED_IN,
                                         {"position": "north_wall"})
            await self.create_relationship(session, oven, kitchen, RelationshipType.LOCATED_IN,
                                         {"position": "east_wall"})
            await self.create_relationship(session, living_room_lights, living_room, RelationshipType.LOCATED_IN,
                                         {"positions": ["ceiling_center", "corners"]})
            # device -> room, not device -> home: `monitors` is declared for
            # device->device, device->room and automation->device.
            await self.create_relationship(session, doorbell, living_room, RelationshipType.MONITORS,
                                         {"location": "front_entrance"})
            await self.create_relationship(session, mitsubishi_thermostat, kitchen, RelationshipType.LOCATED_IN,
                                         {"position": "wall", "height": "5ft"})
            # ---- Episode 1: the blower moved rooms (ADR-004 §1) ----------
            #
            # ONE logical edge, TWO intervals, sharing an id and a boundary
            # instant. This is the case the whole temporal model is built for,
            # and the fixture could not express it before `create_relationship`
            # took an `edge_id`: two calls meant two edges, and the blower
            # showed up in the office and the garage simultaneously.
            #
            # The intervals are half-open — [installed, moved) then [moved, ∞) —
            # so exactly one is current at the handover instant itself, never
            # zero and never two.
            blower_location_edge = str(uuid4())
            await self.create_relationship(
                session, pvfy_blower, office, RelationshipType.LOCATED_IN,
                {"position": "closet", "note": "original install, upstairs"},
                edge_id=blower_location_edge,
                valid_from=TIMELINE["blower_installed"],
                valid_to=TIMELINE["blower_moved"],
            )
            await self.create_relationship(
                session, pvfy_blower, garage, RelationshipType.LOCATED_IN,
                {"position": "closet"},
                edge_id=blower_location_edge,
                valid_from=TIMELINE["blower_moved"],
            )

            # Control relationship between thermostat and blower
            await self.create_relationship(session, mitsubishi_thermostat, pvfy_blower, RelationshipType.CONTROLS,
                                         {"control_type": "temperature_and_fan"})

            # Create procedures
            print("\n📋 Creating procedures and manuals...")

            tv_setup = await self.create_entity(
                session, EntityType.PROCEDURE,
                "TV Initial Setup",
                {
                    "steps": [
                        "1. Connect power cable",
                        "2. Turn on TV with remote",
                        "3. Select language",
                        "4. Connect to WiFi network",
                        "5. Sign in to Samsung account",
                        "6. Run channel scan",
                        "7. Install streaming apps"
                    ],
                    "duration": "30 minutes",
                    "difficulty": "easy"
                },
                key="tv_setup"
            )

            thermostat_schedule = await self.create_entity(
                session, EntityType.PROCEDURE,
                "Configure Thermostat Schedule",
                {
                    "steps": [
                        "1. Press thermostat to wake",
                        "2. Navigate to Settings > Schedule",
                        "3. Set Wake time and temperature",
                        "4. Set Away time and temperature",
                        "5. Set Sleep time and temperature",
                        "6. Repeat for each day",
                        "7. Enable Auto-Schedule learning"
                    ],
                    "duration": "15 minutes",
                    "difficulty": "medium"
                },
                key="thermostat_schedule"
            )

            # Create manuals
            tv_manual = await self.create_entity(
                session, EntityType.MANUAL,
                "Samsung QN90A User Manual",
                {
                    "manufacturer": "Samsung",
                    "model": "QN90A",
                    "version": "1.2",
                    "languages": ["en", "es", "fr"],
                    "pages": 120,
                    "sections": ["setup", "features", "troubleshooting", "specifications"],
                    "url": "https://samsung.com/support/QN90A"
                },
                key="tv_manual"
            )

            # Procedure relationships
            await self.create_relationship(session, tv_setup, tv, RelationshipType.PROCEDURE_FOR)
            await self.create_relationship(session, thermostat_schedule, thermostat, RelationshipType.PROCEDURE_FOR)
            await self.create_relationship(session, tv, tv_manual, RelationshipType.DOCUMENTED_BY)

            # Create automations
            print("\n🤖 Creating automations...")

            good_morning = await self.create_entity(
                session, EntityType.AUTOMATION,
                "Good Morning Routine",
                {
                    "trigger": {
                        "type": "time",
                        "time": "07:00",
                        "days": ["mon", "tue", "wed", "thu", "fri"]
                    },
                    "actions": [
                        {"device": "thermostat", "action": "set_temperature", "value": 72},
                        {"device": "living_room_lights", "action": "turn_on", "brightness": 50},
                        {"device": "kitchen_lights", "action": "turn_on", "brightness": 100}
                    ],
                    "enabled": True
                },
                key="good_morning"
            )

            movie_time = await self.create_entity(
                session, EntityType.AUTOMATION,
                "Movie Time Scene",
                {
                    "trigger": {"type": "manual", "voice_command": "movie time"},
                    "actions": [
                        {"device": "tv", "action": "turn_on"},
                        {"device": "living_room_lights", "action": "dim", "brightness": 10},
                        {"device": "thermostat", "action": "set_temperature", "value": 70}
                    ],
                    "enabled": True
                },
                key="movie_time"
            )

            # Automation relationships
            await self.create_relationship(session, good_morning, thermostat, RelationshipType.AUTOMATES)
            await self.create_relationship(session, good_morning, living_room_lights, RelationshipType.AUTOMATES)
            await self.create_relationship(session, movie_time, tv, RelationshipType.CONTROLS)
            await self.create_relationship(session, movie_time, living_room_lights, RelationshipType.CONTROLS)

            # Create schedules
            print("\n📅 Creating schedules...")

            vacation_mode = await self.create_entity(
                session, EntityType.SCHEDULE,
                "Vacation Mode",
                {
                    "start_date": "2025-08-01",
                    "end_date": "2025-08-15",
                    "settings": {
                        "thermostat": {"mode": "eco", "temp_min": 60, "temp_max": 85},
                        "lights": {"mode": "random", "start_time": "sunset", "end_time": "23:00"},
                        "security": {"mode": "enhanced", "notifications": "all"}
                    },
                    "active": False
                },
                key="vacation_mode"
            )

            # Schedule relationships. `manages` starts at an `app` (ADR-013 §4);
            # a schedule acting on a device is `controls`.
            await self.create_relationship(session, vacation_mode, thermostat, RelationshipType.CONTROLS)
            await self.create_relationship(session, vacation_mode, doorbell, RelationshipType.CONTROLS)

            # Create notes
            print("\n📝 Creating notes...")

            wifi_note = await self.create_entity(
                session, EntityType.NOTE,
                "WiFi Configuration",
                {
                    "content": "Network: MartinezHome5G\nPassword: Sm@rtH0me2025!\nGuest Network: MartinezGuest\nGuest Password: Welcome123",
                    "category": "network",
                    "private": True,
                    "created": TIMELINE["history_begins"].isoformat()
                },
                key="wifi_note"
            )

            maintenance_note = await self.create_entity(
                session, EntityType.NOTE,
                "HVAC Maintenance",
                {
                    "content": "Last filter change: July 1, 2025\nNext service due: October 1, 2025\nTechnician: Bob from ComfortPro (555-0123)",
                    "category": "maintenance",
                    "reminder_date": "2025-10-01",
                    "created": TIMELINE["history_begins"].isoformat()
                },
                key="maintenance_note"
            )

            # Note relationships
            await self.create_relationship(session, wifi_note, home, RelationshipType.DOCUMENTED_BY)
            await self.create_relationship(session, maintenance_note, thermostat, RelationshipType.DOCUMENTED_BY)

            # Create APP entities
            print("\n📱 Creating app entities...")

            homekit_app = await self.create_entity(
                session, EntityType.APP,
                "Apple HomeKit",
                {
                    "platform": "iOS",
                    "url_scheme": "com.apple.home://",
                    "icon": "house.fill",
                    "description": "Apple's home automation platform",
                    "compatible_devices": ["lights", "thermostats", "locks", "cameras", "sensors"]
                },
                key="homekit_app"
            )

            comfort_app = await self.create_entity(
                session, EntityType.APP,
                "Mitsubishi Comfort",
                {
                    "platform": "iOS",
                    "url_scheme": "mitsubishicomfort://",
                    "icon": "thermometer",
                    "description": "Remote control app for Mitsubishi HVAC systems",
                    "compatible_devices": ["PAR-42MAA", "PVFY", "Mitsubishi thermostats"]
                },
                key="comfort_app"
            )

            # Link apps to what they run. `controlled_by_app` was the exact
            # inverse of `manages` and is deleted (ADR-013 §4); the app is the
            # actor, so it is the subject.
            await self.create_relationship(session, homekit_app, thermostat, RelationshipType.MANAGES,
                                         {"integration": "native"})
            await self.create_relationship(session, homekit_app, living_room_lights, RelationshipType.MANAGES,
                                         {"integration": "hue_bridge"})
            await self.create_relationship(session, comfort_app, mitsubishi_thermostat, RelationshipType.MANAGES,
                                         {"integration": "wifi_adapter", "features": ["remote_control", "scheduling", "energy_monitoring"]})

            # Create user-generated content notes
            print("\n📝 Creating user-generated content notes...")

            mitsubishi_user_note = await self.create_entity(
                session, EntityType.NOTE,
                "Mitsubishi System User Notes",
                {
                    "content": "This thermostat is in the kitchen, it controls the air blower that heats and cools the kitchen, dining room, living room, bar and kitchen bathroom. The air blower is in a closet in the garage. The thermostat can be remotely controlled using the Mitsubishi Comfort app on iPhone or iPad.",
                    "category": "user_provided",
                    "device_references": ["mitsubishi_thermostat", "pvfy_blower"],
                    "created": TIMELINE["history_begins"].isoformat()
                },
                key="mitsubishi_user_note"
            )

            # Create manual entities for PDFs
            mitsubishi_manual = await self.create_entity(
                session, EntityType.MANUAL,
                "PAR-42MAAUB Instruction Manual",
                {
                    "manufacturer": "Mitsubishi",
                    "model": "PAR-42MAAUB",
                    "document_type": "instruction_manual",
                    "original_filename": "PAR-42MAAUB_Instruction Book.pdf",
                    "summary": "Complete instruction manual for Mitsubishi PAR-42MAAUB thermostat including installation, operation, and maintenance procedures.",
                    # A `manual` IS a PDF attachment (ADR-013 §3), so no
                    # "has_blob" flag: the entity type already says it. One
                    # link only -- blob_id -- and it attaches via DOCUMENTED_BY.
                    "mime_type": "application/pdf",
                    "data_b64": _demo_bytes("pdf_manual_par42")
                },
                key="mitsubishi_manual"
            )

            # Link manual to devices
            await self.create_relationship(session, mitsubishi_thermostat, mitsubishi_manual, RelationshipType.DOCUMENTED_BY,
                                         {"document_type": "user_manual"})

            # Link user note to devices
            await self.create_relationship(session, mitsubishi_user_note, mitsubishi_thermostat, RelationshipType.DOCUMENTED_BY,
                                         {"note_type": "user_provided"})
            await self.create_relationship(session, mitsubishi_user_note, pvfy_blower, RelationshipType.DOCUMENTED_BY,
                                         {"note_type": "user_provided"})

            # Photos are their own entity type (ADR-013 §3). One photo per blob,
            # rather than a note listing several filenames: a photo entity that
            # claims two images has no single blob_id, which is how the
            # "blob_references" plural crept in and made the link ambiguous.
            thermostat_photo = await self.create_entity(
                session, EntityType.PHOTO,
                "PAR-42.jpeg",
                {
                    "description": "Photo of Mitsubishi PAR-42MAA thermostat installed in kitchen",
                    "filename": "PAR-42.jpeg",
                    "mime_type": "image/jpeg",
                    "data_b64": _demo_bytes("photo_par42")
                },
                key="thermostat_photo"
            )

            blower_photo = await self.create_entity(
                session, EntityType.PHOTO,
                "PVFY-Blower.jpeg",
                {
                    "description": "Photo of PVFY air handler blower unit",
                    "filename": "PVFY-Blower.jpeg",
                    "mime_type": "image/jpeg",
                    "data_b64": _demo_bytes("photo_pvfy_blower")
                },
                key="blower_photo"
            )

            blower_serial_photo = await self.create_entity(
                session, EntityType.PHOTO,
                "PVFY-Serial_Number.jpeg",
                {
                    "description": "Photo of PVFY air handler serial number plate",
                    "filename": "PVFY-Serial_Number.jpeg",
                    "mime_type": "image/jpeg",
                    "data_b64": _demo_bytes("photo_pvfy_serial")
                },
                key="blower_serial_photo"
            )

            # device -> photo, not photo -> device. The old edges ran backwards
            # against their own declared endpoints, which nothing caught because
            # the rule was enforced on one write path of three (ADR-013 §5).
            await self.create_relationship(session, mitsubishi_thermostat, thermostat_photo,
                                           RelationshipType.HAS_PHOTO, {})
            await self.create_relationship(session, pvfy_blower, blower_photo,
                                           RelationshipType.HAS_PHOTO, {})
            await self.create_relationship(session, pvfy_blower, blower_serial_photo,
                                           RelationshipType.HAS_PHOTO, {})

            # ==========================================================
            # Episodes 2-4: the rest of the recorded past (ADR-004)
            #
            # These are additive. Every one of them leaves the CURRENT graph
            # exactly as it was — same entities, same live edges, same answers
            # to every present-tense question — and adds only rows that
            # describe periods that have ended. That is the property that makes
            # them safe to put in the shared fixture rather than behind a flag:
            # a test that does not ask about the past cannot notice they exist.
            # ==========================================================
            print("\n🕰️  Recording the house's history...")

            # ---- Episode 2: HomeKit stopped managing the oven ------------
            #
            # A retired edge: `valid_to` set, the row kept. The distinction it
            # demonstrates is between "the oven is not managed by HomeKit"
            # (true now) and "the oven was never managed by HomeKit" (false) —
            # which a delete would have made indistinguishable.
            await self.create_relationship(
                session, homekit_app, oven, RelationshipType.MANAGES,
                {"integration": "homekit", "retired_reason": "moved to vendor app"},
                valid_from=TIMELINE["history_begins"],
                valid_to=TIMELINE["oven_left_homekit"],
            )

            # ---- Episode 3: the thermostat was renamed -------------------
            #
            # Entity version history. The Nest was plain "Thermostat" until a
            # second thermostat arrived and the name stopped being unambiguous.
            # Added as an ANCESTOR rather than a revision, so the current name
            # is untouched and only the DAG grows (see backdate_predecessor).
            await self.backdate_predecessor(
                session, thermostat,
                at=TIMELINE["thermostat_renamed"],
                name="Thermostat",
            )

            # ---- Episode 4: the hallway motion sensor was removed --------
            #
            # A tombstone (PROTOCOL.md §8) and the edge ending that goes with
            # it. Both halves matter: tombstoning the entity without ending its
            # edge leaves the graph asserting that a device which no longer
            # exists is still located somewhere, and the integrity warning in
            # ADR-004 §3.4 exists to catch exactly that shape.
            motion_sensor = await self.create_entity(
                session, EntityType.DEVICE,
                "Hallway Motion Sensor",
                {
                    "manufacturer": "Aqara",
                    "model": "RTCGQ11LM",
                    "type": "sensor",
                    "capabilities": ["motion", "lux"],
                    "network": "zigbee",
                    "hub": "philips_hue_bridge",
                },
                key="motion_sensor",
                at=TIMELINE["history_begins"],
            )
            sensor_location = await self.create_relationship(
                session, motion_sensor, living_room, RelationshipType.LOCATED_IN,
                {"position": "hallway_entrance"},
                valid_from=TIMELINE["history_begins"],
            )
            await self.retire_relationship(
                session, sensor_location, at=TIMELINE["sensor_removed"]
            )
            await self.revise_entity(
                session, motion_sensor,
                at=TIMELINE["sensor_removed"],
                deleted=True,
            )

            # Commit all changes
            await session.commit()

            # Print summary
            print("\n✅ Graph population complete!")
            print("\n📊 Created:")
            print(f"  • 1 Home")
            print(f"  • 3 Zones")
            print(f"  • 6 Rooms")
            print(f"  • 1 Door")
            print(f"  • 8 Devices (including Mitsubishi thermostat & PVFY blower)")
            print(f"  • 2 Procedures")
            print(f"  • 2 Manuals (including Mitsubishi manual)")
            print(f"  • 2 Automations")
            print(f"  • 1 Schedule")
            print(f"  • 6 Notes (including UGC notes and photo documentation)")
            print(f"  • 2 Apps (HomeKit & Mitsubishi Comfort)")
            print(f"  • ~45+ Relationships")
            print("\n🕰️  Recorded history (ADR-004):")
            print(f"  • Blower relocated office → garage on "
                  f"{TIMELINE['blower_moved'].date()} (one edge, two intervals)")
            print(f"  • HomeKit stopped managing the oven on "
                  f"{TIMELINE['oven_left_homekit'].date()} (retired edge)")
            print(f"  • Thermostat renamed on "
                  f"{TIMELINE['thermostat_renamed'].date()} (2 versions)")
            print(f"  • Hallway motion sensor removed on "
                  f"{TIMELINE['sensor_removed'].date()} (tombstone + edge end)")

            return True


async def main():
    """Main entry point"""
    print("🏠 Populating FunkyGibbon MCP Graph Database...")
    print("=" * 50)

    populator = GraphPopulator()

    try:
        await populator.setup_database()
        await populator.populate()
        print("\n🎉 Database population successful!")
        print(f"\n📁 Database location: {DATABASE_URL}")
        print("\n🧪 Test with: oook stats")

    except Exception as e:
        print(f"\n❌ Error populating database: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
