"""Seed a vehicles database with the four example lifecycles (ADR-016 §4).

The counterpart of ``funkygibbon/populate_graph_db.py`` for the second domain,
built on the same primitives so the two fixtures make the same promises:
deterministic dates, backdated versions, interval edges with real history.
It writes straight to the database named by ``DATABASE_URL`` -- run it before
the server opens the file.

    DATABASE_URL=sqlite+aiosqlite:///./vehicles.db python domains/vehicles/seed.py

The four vehicles are the ones ``docs/vehicles-proposal.md`` works through,
each stressing a different part of the capture vocabulary:

* **2026 Mini Cooper SE**, UK-registered — a new EV with an app feed: only
  logbook-grade facts arrive (a fast charge, a software update, a month-end
  odometer); pounds, and a UK garage.
* **2010 Tesla Roadster Sport** with an OVMS box — third-party telemetry
  summarised into monthly battery condition reports; the OVMS module is a
  part with its own v2 → v3 history.
* **E30 Lemons race car #4471-L** — stored off-site with its trailer and
  spares, no single VIN: the shell and the engines are parts with intervals,
  the logbook number is the identity, hours not miles.
* **2009 Porsche Boxster S** — a gas car in the family since new: a long
  history with a transfer of ownership inside the family, fuel purchases,
  one named road trip, and the parts a seventeen-year life accumulates.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Runnable as a script from the repo root (the way conftest runs the house seed).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from funkygibbon.populate_graph_db import GraphPopulator  # noqa: E402


def _utc(year, month, day, hour=12):
    return datetime(year, month, day, hour, 0, tzinfo=timezone.utc)


#: The fixture's dates. Tests import these rather than restating them.
TIMELINE = {
    # Mini
    "mini_evaluated": _utc(2026, 7, 19), "mini_delivered": _utc(2026, 8, 30),
    "mini_update": _utc(2026, 9, 2), "mini_charge": _utc(2026, 9, 11), "mini_odometer": _utc(2026, 9, 30),
    # Roadster
    "roadster_evaluated": _utc(2019, 4, 6), "roadster_bought": _utc(2019, 4, 20),
    "roadster_cac_2020": _utc(2020, 1, 31), "roadster_pem_fan": _utc(2021, 10, 14),
    "roadster_ovms_v3": _utc(2023, 6, 3), "roadster_show": _utc(2024, 8, 17), "roadster_cac_2026": _utc(2026, 1, 31),
    # Lemons
    "lemons_bought": _utc(2017, 2, 11), "lemons_caged": _utc(2017, 5, 20), "lemons_race_1": _utc(2017, 9, 16),
    "lemons_engine_swap": _utc(2018, 4, 8), "lemons_reshell": _utc(2019, 11, 2),
    "lemons_spares_pallet": _utc(2020, 2, 1), "lemons_race_2": _utc(2024, 6, 15), "trailer_home": _utc(2026, 3, 7),
    # Boxster
    "boxster_bought": _utc(2009, 5, 16), "boxster_first_service": _utc(2011, 6, 4),
    "boxster_road_trip": _utc(2014, 8, 9), "boxster_clutch": _utc(2016, 3, 12),
    "boxster_transfer": _utc(2019, 10, 5), "boxster_top": _utc(2021, 7, 17),
    "boxster_smog": _utc(2023, 2, 11), "boxster_tyres": _utc(2025, 4, 19), "boxster_fuel": _utc(2026, 9, 6),
    # Elise (UK, illustrative)
    "elise_bought": _utc(2015, 6, 13), "elise_mot_2024": _utc(2024, 5, 9), "elise_mot_2025": _utc(2025, 5, 7),
    "elise_fuel": _utc(2025, 8, 16), "elise_sorn": _utc(2025, 11, 1),
}

DATABASE_URL = os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./vehicles.db"


def _d(moment: datetime) -> str:
    return moment.date().isoformat()


async def populate_vehicles(populator: GraphPopulator) -> None:
    T = TIMELINE
    async with populator.session_maker() as session:
        ent, rel = populator.create_entity, populator.create_relationship

        async def event(vehicle, name, kind, when, *, odometer=None, hours=None, cost=None, currency="USD",
                        text="", source="walk", where=None, involved=(), key=None, **extra):
            content = {"kind": kind, "when": _d(when), "text": text, "source": source}
            if odometer is not None:
                content["odometer"] = odometer
            if hours is not None:
                content["hours"] = hours
            if cost is not None:
                content.update({"cost": cost, "currency": currency})
            if where:
                content["where"] = where
            content.update(extra)
            e = await ent(session, "event", name, content, key=key, at=when)
            await rel(session, e, vehicle, "happened_to", valid_from=when)
            for thing in involved:
                await rel(session, e, thing, "involved", valid_from=when)
            return e

        # --- Places ---------------------------------------------------------
        # Places are backdated to the first fact that mentions them: an as-of
        # read for 2017 must find the yard, so the yard must exist in 2017.
        garage = await ent(session, "location", "Home garage", {"kind": "home_garage", "country": "US"},
                           key="home_garage", at=T["boxster_bought"])
        driveway = await ent(session, "location", "Home driveway", {"kind": "driveway", "country": "US"},
                             key="home_driveway", at=T["boxster_bought"])
        yard = await ent(session, "location", "Team storage yard, Hollister",
                         {"kind": "yard", "address": "Hollister, CA", "country": "US"}, key="yard", at=T["lemons_bought"])
        uk_garage = await ent(session, "location", "UK house garage",
                              {"kind": "home_garage", "address": "Cambridge, UK", "country": "UK"}, key="uk_garage", at=T["mini_evaluated"])
        lockup = await ent(session, "location", "Lock-up, Cambridge",
                           {"kind": "storage_unit", "address": "Cambridge, UK", "country": "UK"}, key="lockup", at=T["elise_bought"])

        # ================================================================== #
        # 2026 Mini Cooper SE -- a new EV with an app feed, UK-registered
        # ================================================================== #
        mini = await ent(session, "vehicle", "2026 Mini Cooper SE", {
            "kind": "ev", "make": "Mini", "model": "Cooper SE", "year": 2026,
            "identity": {"vin": "WMW13DJ0XS2T00147", "registration": "EY26 MNI", "registration_country": "UK"},
            "country": "UK", "aliases": ["the Mini"], "status": "owned",
            "odometer": 640, "odometer_unit": "mi",
            "spec": {"trim": "Level 3", "colour": "Chili Red", "roof": "black", "wheels": "18in",
                     "battery_kwh": 54.2, "motor_kw": 160},
        }, key="mini", at=T["mini_evaluated"])
        await event(mini, "Test drive and spec", "evaluation", T["mini_evaluated"], odometer=0,
                    text="Test drove at the dealer; spec chosen: Level 3, Chili Red, black roof, 18in wheels.",
                    where="MINI Cambridge")
        await event(mini, "Delivery", "purchase", T["mini_delivered"], odometer=6, cost=36500, currency="GBP",
                    text="Delivered on a 26 plate. Warranty and battery certificate attached; app paired; V5C to follow.")
        await rel(session, mini, uk_garage, "located_in", valid_from=T["mini_delivered"])
        mini_app = await ent(session, "app", "MINI app", {"vendor": "BMW Group"}, key="mini_app")
        await rel(session, mini_app, mini, "manages", valid_from=T["mini_delivered"])
        await event(mini, "Software 2026.3", "software_update", T["mini_update"], odometer=41,
                    text="From the app: 2026.3 (charging curve fix).", source="feed")
        await event(mini, "Fast charge, Cambridge services", "charge", T["mini_charge"], odometer=380, cost=22.63, currency="GBP",
                    text="InstaVolt, Cambridge services: 31 kWh in 18 min at 73p/kWh.", source="feed",
                    where="InstaVolt, Cambridge services", kwh=31, charge_kind="fast")
        await event(mini, "Month-end odometer", "odometer", T["mini_odometer"], odometer=640,
                    text="Month-end reading from the app; 22 home charges this month, 118 kWh.",
                    source="feed", home_charges=22, home_kwh=118)

        # ================================================================== #
        # 2010 Tesla Roadster Sport with OVMS -- telemetry, summarised
        # ================================================================== #
        roadster = await ent(session, "vehicle", "2010 Tesla Roadster Sport", {
            "kind": "ev", "make": "Tesla", "model": "Roadster 2.5 Sport", "year": 2010,
            "identity": {"vin": "5YJRE1A38A1001204", "registration": "6ROA DST", "registration_country": "US", "state": "CA"},
            "country": "US", "aliases": ["the Roadster"], "status": "owned",
            "odometer": 31850, "odometer_unit": "mi",
            "spec": {"battery_kwh": 53, "motor_kw": 215, "colour": "Radiant Red", "tops": ["soft", "hard"]},
        }, key="roadster", at=T["roadster_evaluated"])
        await event(roadster, "Viewed in Palo Alto", "evaluation", T["roadster_evaluated"], odometer=22850,
                    text="Roadster 2.5 Sport, one owner, CAC 138 Ah reported.", where="Palo Alto")
        await event(roadster, "Purchase", "purchase", T["roadster_bought"], odometer=22850, cost=62000,
                    text="Came with: original PEM, soft top, hard top, OVMS v2 fitted.")
        await rel(session, roadster, garage, "located_in", valid_from=T["roadster_bought"])
        ovms_v2 = await ent(session, "part", "OVMS v2 module", {"category": "telematics", "version": "v2"},
                            key="ovms_v2", at=T["roadster_bought"])
        await rel(session, ovms_v2, roadster, "fitted_to", valid_from=T["roadster_bought"], valid_to=T["roadster_ovms_v3"])
        ovms_app = await ent(session, "app", "OVMS", {"vendor": "Open Vehicle Monitoring System"}, key="ovms_app")
        await rel(session, ovms_app, roadster, "manages", valid_from=T["roadster_bought"])
        await event(roadster, "Battery condition, Jan 2020", "condition_report", T["roadster_cac_2020"], odometer=24100,
                    text="Battery: CAC 135 Ah, ideal range 202 mi (monthly, from OVMS).", source="feed",
                    cac_ah=135, ideal_range_mi=202)
        pem_fan_old = await ent(session, "part", "PEM fan (original)", {"category": "cooling"},
                                key="pem_fan_old", at=T["roadster_bought"])
        await rel(session, pem_fan_old, roadster, "fitted_to", valid_from=T["roadster_bought"], valid_to=T["roadster_pem_fan"])
        pem_fan_new = await ent(session, "part", "PEM fan (Gruber)", {"category": "cooling"},
                                key="pem_fan_new", at=T["roadster_pem_fan"])
        await rel(session, pem_fan_new, roadster, "fitted_to", valid_from=T["roadster_pem_fan"])
        await rel(session, pem_fan_new, pem_fan_old, "replaced", valid_from=T["roadster_pem_fan"])
        await rel(session, pem_fan_old, garage, "located_in", valid_from=T["roadster_pem_fan"])
        await event(roadster, "PEM fan replacement", "service", T["roadster_pem_fan"], odometer=27400, cost=1450,
                    text="PEM fan replacement at Gruber Motors. Original fan kept in the parts bin.",
                    where="Gruber Motors, Phoenix", involved=(pem_fan_new, pem_fan_old))
        ovms_v3 = await ent(session, "part", "OVMS v3 module", {"category": "telematics", "version": "v3"},
                            key="ovms_v3", at=T["roadster_ovms_v3"])
        await rel(session, ovms_v3, roadster, "fitted_to", valid_from=T["roadster_ovms_v3"])
        await rel(session, ovms_v3, ovms_v2, "replaced", valid_from=T["roadster_ovms_v3"])
        await event(roadster, "OVMS v3 fitted", "modification", T["roadster_ovms_v3"], odometer=29900, cost=280,
                    text="OVMS v3 module replaces v2.", involved=(ovms_v3, ovms_v2), reversible=True)
        await event(roadster, "Monterey Roadster gathering", "show", T["roadster_show"], odometer=30600,
                    text="Monterey Car Week, Tesla Roadster gathering.", where="Monterey")
        await event(roadster, "Battery condition, Jan 2026", "condition_report", T["roadster_cac_2026"], odometer=31850,
                    text="Battery: CAC 129 Ah, ideal range 189 mi (monthly, from OVMS).", source="feed",
                    cac_ah=129, ideal_range_mi=189)

        # ================================================================== #
        # E30 Lemons race car #4471-L -- off-site, no single VIN, hours
        # ================================================================== #
        lemons = await ent(session, "vehicle", "E30 Lemons car #4471-L", {
            "kind": "race_car", "make": "BMW", "model": "325i (E30) Lemons build", "year": 1989,
            "identity": {"lemons_logbook": "4471-L", "shell_vin": "WBAAA1300K8129083"},
            "country": "US", "aliases": ["the Lemons car", "4471"], "status": "owned",
            "hours": 96, "odometer_unit": "hours",
            "spec": {"engine": "M20B25", "cage": "6-point, 2017", "series": "24 Hours of Lemons"},
        }, key="lemons", at=T["lemons_bought"])
        await event(lemons, "Donor purchase", "purchase", T["lemons_bought"], cost=600,
                    text="Donor 1989 325i, $600, no title (bill of sale only). Shell VIN WBAAA1300K8124471.")
        await rel(session, lemons, yard, "located_in", valid_from=T["lemons_bought"])
        shell_1 = await ent(session, "part", "Shell WBAAA1300K8124471", {"category": "shell", "vin": "WBAAA1300K8124471"},
                            key="shell_1", at=T["lemons_bought"])
        await rel(session, shell_1, lemons, "fitted_to", valid_from=T["lemons_bought"], valid_to=T["lemons_reshell"])
        engine_1 = await ent(session, "part", "M20B25 engine #1", {"category": "engine"}, key="engine_1", at=T["lemons_bought"])
        await rel(session, engine_1, lemons, "fitted_to", valid_from=T["lemons_bought"], valid_to=T["lemons_engine_swap"])
        await event(lemons, "Cage built, logbook issued", "modification", T["lemons_caged"], hours=0,
                    text="Cage built; Lemons logbook #4471-L issued -- the car's identity from here on.")
        await event(lemons, "Thunderhill 24h", "race", T["lemons_race_1"], hours=14,
                    text="Finished 31st. Setup: 32/30 psi, 3 deg camber.", where="Thunderhill", result="31st")
        engine_2 = await ent(session, "part", "M20B25 engine #2", {"category": "engine"}, key="engine_2", at=T["lemons_engine_swap"])
        await rel(session, engine_2, lemons, "fitted_to", valid_from=T["lemons_engine_swap"])
        await rel(session, engine_2, engine_1, "replaced", valid_from=T["lemons_engine_swap"])
        await event(lemons, "Spun bearing, engine swap", "repair", T["lemons_engine_swap"], hours=27,
                    text="Spun engine bearing. Engine #1 scrapped; engine #2 fitted from spares.",
                    involved=(engine_2, engine_1))
        shell_2 = await ent(session, "part", "Shell WBAAA1300K8129083", {"category": "shell", "vin": "WBAAA1300K8129083"},
                            key="shell_2", at=T["lemons_reshell"])
        await rel(session, shell_2, lemons, "fitted_to", valid_from=T["lemons_reshell"])
        await rel(session, shell_2, shell_1, "replaced", valid_from=T["lemons_reshell"])
        await event(lemons, "Crash, re-shell", "repair", T["lemons_reshell"], hours=55, cost=300,
                    text="Crash damage, shell scrapped; $300 donor shell. Cage, logbook, engine #2, suspension carried over. Lemons tech re-inspection passed.",
                    involved=(shell_2, shell_1))
        engine_3 = await ent(session, "part", "M20B25 engine #3 (spare)", {"category": "engine"}, key="engine_3", at=T["lemons_spares_pallet"])
        await rel(session, engine_3, yard, "located_in", valid_from=T["lemons_spares_pallet"])
        await rel(session, engine_3, lemons, "compatible_with", valid_from=T["lemons_spares_pallet"])
        fuel_pump = await ent(session, "part", "Fuel pump (spare)", {"category": "fuel"}, key="fuel_pump", at=T["lemons_spares_pallet"])
        await rel(session, fuel_pump, yard, "located_in", valid_from=T["lemons_spares_pallet"], valid_to=T["lemons_race_2"])
        await rel(session, fuel_pump, lemons, "fitted_to", valid_from=T["lemons_race_2"])
        await event(lemons, "Sonoma", "race", T["lemons_race_2"], hours=96,
                    text="DNF, fuel pump. Spare fitted at the track.", where="Sonoma Raceway", result="DNF",
                    involved=(fuel_pump,))
        trailer = await ent(session, "vehicle", "Car trailer", {
            "kind": "trailer", "make": "Carson", "model": "18ft flatbed", "year": 2016,
            "identity": {"vin": "4HXSF1823GC123456"}, "aliases": ["the trailer"], "status": "owned",
        }, key="trailer", at=T["lemons_bought"])
        await rel(session, trailer, yard, "located_in", valid_from=T["lemons_bought"], valid_to=T["trailer_home"])
        await rel(session, trailer, driveway, "located_in", valid_from=T["trailer_home"])
        await event(trailer, "Trailer home for the season", "transfer", T["trailer_home"],
                    text="Moved from the yard to the home driveway for the season.")

        # ================================================================== #
        # 2009 Porsche Boxster S -- in the family since new
        # ================================================================== #
        boxster = await ent(session, "vehicle", "2009 Porsche Boxster S", {
            "kind": "car", "make": "Porsche", "model": "Boxster S (987.2)", "year": 2009,
            "identity": {"vin": "WP0CB29879U730412", "registration": "6BOX STR", "registration_country": "US", "state": "CA"},
            "country": "US", "aliases": ["the Boxster", "Dad's car"], "status": "owned",
            "odometer": 91400, "odometer_unit": "mi",
            "spec": {"engine": "3.4 DFI flat-six, 310 hp", "gearbox": "6-speed manual",
                     "colour": "Arctic Silver", "interior": "black leather", "options": ["PASM", "Sport Chrono", "Bose"]},
            "fuel": "gasoline",
        }, key="boxster", at=T["boxster_bought"])
        await event(boxster, "Bought new", "purchase", T["boxster_bought"], odometer=12, cost=61000,
                    text="Bought new by Dad at Porsche Redwood City. Window sticker in the folder.",
                    where="Porsche Redwood City")
        await rel(session, boxster, garage, "located_in", valid_from=T["boxster_bought"])
        await event(boxster, "First service", "service", T["boxster_first_service"], odometer=12300, cost=410,
                    text="Oil and filter, dealer.")
        await event(boxster, "PCH to Big Sur", "road_trip", T["boxster_road_trip"], odometer=31200,
                    text="The drive everyone remembers; top down the whole way.", where="Highway 1")
        clutch = await ent(session, "part", "Clutch kit (Sachs)", {"category": "drivetrain"}, key="boxster_clutch", at=T["boxster_clutch"])
        await rel(session, clutch, boxster, "fitted_to", valid_from=T["boxster_clutch"])
        await event(boxster, "Clutch", "service", T["boxster_clutch"], odometer=48000, cost=2350,
                    text="Clutch and flywheel at an independent; everyone learned to drive stick on the old one.",
                    involved=(clutch,))
        await event(boxster, "Handed down", "transfer", T["boxster_transfer"], odometer=64500,
                    text="Title transferred within the family; Dad kept the spare key.")
        top = await ent(session, "part", "Convertible top (Robbins)", {"category": "body"}, key="boxster_top", at=T["boxster_top"])
        await rel(session, top, boxster, "fitted_to", valid_from=T["boxster_top"])
        await event(boxster, "Top replaced", "repair", T["boxster_top"], odometer=72100, cost=1890,
                    text="Rear window seam failed; whole top replaced.", involved=(top,))
        await event(boxster, "Smog check", "inspection", T["boxster_smog"], odometer=80300, cost=60,
                    text="California smog: pass.", result="pass")
        tyres = await ent(session, "part", "Michelin Pilot Sport 4S (set)", {"category": "tyres"}, key="boxster_tyres", at=T["boxster_tyres"])
        await rel(session, tyres, boxster, "fitted_to", valid_from=T["boxster_tyres"])
        await event(boxster, "Tyres and brakes", "service", T["boxster_tyres"], odometer=88900, cost=2140,
                    text="Four tyres, front pads and discs.", involved=(tyres,))
        await event(boxster, "Fuel, Chevron", "fuel", T["boxster_fuel"], odometer=91400, cost=71.20,
                    text="14.1 gal premium.", where="Chevron, Woodside", gallons=14.1)
        note = await ent(session, "note", "Boxster walk transcript",
                         {"text": "Walked the Boxster with Dad; he remembers the delivery day and the Big Sur trip."},
                         key="boxster_note")
        await rel(session, boxster, note, "documented_by")

        # ================================================================== #
        # 1998 Lotus Elise S1 -- UK-registered (illustrative): reg number as
        # the working identity, MOT history as a public feed, GBP, litres,
        # tax / SORN status.
        # ================================================================== #
        elise = await ent(session, "vehicle", "1998 Lotus Elise S1", {
            "kind": "car", "make": "Lotus", "model": "Elise S1", "year": 1998,
            "identity": {"vin": "SCCGA111XWHA12345", "registration": "R123 LTS", "registration_country": "UK",
                         "v5c": "on file"},
            "country": "UK", "aliases": ["the Elise"], "status": "owned",
            "odometer": 61200, "odometer_unit": "mi",
            "spec": {"engine": "Rover K-series 1.8", "colour": "Azure Blue", "weight_kg": 725},
            "fuel": "petrol",
        }, key="elise", at=T["elise_bought"])
        await event(elise, "Bought at auction", "purchase", T["elise_bought"], odometer=48900, cost=14500, currency="GBP",
                    text="Bought at a UK auction; V5C in the folder.", where="Bicester")
        await rel(session, elise, lockup, "located_in", valid_from=T["elise_bought"])
        await event(elise, "MOT 2024", "inspection", T["elise_mot_2024"], odometer=59800, cost=54.85, currency="GBP",
                    text="MOT pass; advisory: nearside front tyre wearing on inner edge.", source="feed",
                    result="pass", advisories=["nearside front tyre wearing on inner edge"], test="MOT")
        await event(elise, "MOT 2025", "inspection", T["elise_mot_2025"], odometer=60900, cost=54.85, currency="GBP",
                    text="MOT pass, no advisories.", source="feed", result="pass", advisories=[], test="MOT")
        await event(elise, "Fuel, Shell", "fuel", T["elise_fuel"], odometer=61200, cost=68.40, currency="GBP",
                    text="45.2 litres super unleaded.", where="Shell, Newmarket Road", litres=45.2)
        await event(elise, "Declared SORN", "transfer", T["elise_sorn"],
                    text="Off the road for the winter; SORN declared with DVLA.", status="SORN")

        await session.commit()


async def main() -> bool:
    print("🏁 Populating the vehicles database...")
    populator = GraphPopulator(DATABASE_URL)
    try:
        await populator.setup_database()
        await populate_vehicles(populator)
        print(f"✅ {len(populator.entities)} keyed entities seeded into {DATABASE_URL}")
        return True
    except Exception as exc:  # pragma: no cover - a seed failure is fatal and loud
        import traceback
        print(f"❌ vehicles seed failed: {exc}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
