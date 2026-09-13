"""Seed a vehicles database with a small, dated collection (ADR-012).

The counterpart of ``funkygibbon/populate_graph_db.py`` for the second domain,
built on the same primitives so the two fixtures make the same promises:
deterministic dates, backdated versions, interval edges with real history.
It writes straight to the database named by ``DATABASE_URL`` -- run it before
the server opens the file, exactly as the house seed is run.

    DATABASE_URL=sqlite+aiosqlite:///./vehicles.db python domains/vehicles/seed.py

What is in it, and why:

* Three vehicles of three kinds (car, bicycle, motorcycle), because one
  ``vehicle`` type with ``content.kind`` is a claim this fixture should test.
* A set of tyres that was fitted, then replaced: one logical ``fitted_to``
  edge with a closed interval and a second edge that opens the day the old one
  closes. ``get_parts_on_vehicle(at=...)`` is the whole point of the domain.
* An issue that was opened and later resolved by a service, and one still open.
* Purchases with dates, so ``get_vehicle_history`` has a beginning.
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
    "outback_bought": _utc(2021, 5, 14),
    "outback_oil_change": _utc(2024, 4, 2),
    "michelins_fitted": _utc(2023, 9, 10),
    "tyres_swapped": _utc(2025, 8, 22),
    "brake_issue_opened": _utc(2025, 3, 1),
    "tarmac_bought": _utc(2022, 3, 2),
    "bb_issue_opened": _utc(2024, 9, 1),
    "chain_replaced": _utc(2024, 11, 6),
    "zero_bought": _utc(2023, 6, 20),
}

DATABASE_URL = os.environ.get("DATABASE_URL") or "sqlite+aiosqlite:///./vehicles.db"


async def populate_vehicles(populator: GraphPopulator) -> None:
    T = TIMELINE
    async with populator.session_maker() as session:
        ent, rel = populator.create_entity, populator.create_relationship

        # --- Places -----------------------------------------------------
        bay1 = await ent(session, "location", "Garage Bay 1", {"kind": "bay"}, key="bay1")
        bay2 = await ent(session, "location", "Garage Bay 2", {"kind": "bay"}, key="bay2")
        shelf = await ent(session, "location", "Workshop Shelf", {"kind": "shelf"}, key="shelf")

        # --- Vehicles ----------------------------------------------------
        outback = await ent(session, "vehicle", "2019 Subaru Outback", {
            "kind": "car", "make": "Subaru", "model": "Outback", "year": 2019,
            "registration": "8ABC123", "odometer": 48200, "odometer_unit": "mi",
        }, key="outback", at=T["outback_bought"])
        tarmac = await ent(session, "vehicle", "Specialized Tarmac SL7", {
            "kind": "bicycle", "make": "Specialized", "model": "Tarmac SL7", "year": 2022,
            "frame_size": "56", "odometer": 6100, "odometer_unit": "km",
        }, key="tarmac", at=T["tarmac_bought"])
        zero = await ent(session, "vehicle", "Zero SR/F", {
            "kind": "motorcycle", "make": "Zero", "model": "SR/F", "year": 2023,
            "registration": "M0T0EV", "odometer": 4300, "odometer_unit": "mi", "battery_kwh": 14.4,
        }, key="zero", at=T["zero_bought"])
        await rel(session, outback, bay1, "located_in", valid_from=T["outback_bought"])
        await rel(session, zero, bay2, "located_in", valid_from=T["zero_bought"])
        await rel(session, tarmac, shelf, "located_in", valid_from=T["tarmac_bought"])

        # --- Purchases ---------------------------------------------------
        p_outback = await ent(session, "purchase", "Outback purchase", {
            "date": T["outback_bought"].date().isoformat(), "vendor": "Bay Area Subaru",
            "price": 24500, "currency": "USD",
        }, key="p_outback", at=T["outback_bought"])
        p_tarmac = await ent(session, "purchase", "Tarmac purchase", {
            "date": T["tarmac_bought"].date().isoformat(), "vendor": "Mike's Bikes",
            "price": 6800, "currency": "USD",
        }, key="p_tarmac", at=T["tarmac_bought"])
        p_zero = await ent(session, "purchase", "Zero purchase", {
            "date": T["zero_bought"].date().isoformat(), "vendor": "Zero Motorcycles SF",
            "price": 21000, "currency": "USD",
        }, key="p_zero", at=T["zero_bought"])
        p_tyres = await ent(session, "purchase", "Continental tyres purchase", {
            "date": T["tyres_swapped"].date().isoformat(), "vendor": "Tire Rack",
            "price": 640, "currency": "USD",
        }, key="p_tyres", at=T["tyres_swapped"])
        await rel(session, outback, p_outback, "purchased_via", valid_from=T["outback_bought"])
        await rel(session, tarmac, p_tarmac, "purchased_via", valid_from=T["tarmac_bought"])
        await rel(session, zero, p_zero, "purchased_via", valid_from=T["zero_bought"])

        # --- Parts: the tyre swap is the headline interval case -----------
        michelins = await ent(session, "part", "Michelin CrossClimate2 (set of 4)", {
            "category": "tyres", "size": "225/60R18",
        }, key="michelins", at=T["michelins_fitted"])
        continentals = await ent(session, "part", "Continental TrueContact Tour (set of 4)", {
            "category": "tyres", "size": "225/60R18",
        }, key="continentals", at=T["tyres_swapped"])
        await rel(session, continentals, p_tyres, "purchased_via", valid_from=T["tyres_swapped"])
        # One logical edge per part-on-vehicle life. The Michelins' interval
        # closes the day the Continentals' opens: two rows, no overlap, and
        # `at` picks exactly one of them for any instant.
        await rel(session, michelins, outback, "fitted_to",
                  valid_from=T["michelins_fitted"], valid_to=T["tyres_swapped"])
        await rel(session, continentals, outback, "fitted_to", valid_from=T["tyres_swapped"])
        await rel(session, continentals, michelins, "replaced", valid_from=T["tyres_swapped"])
        await rel(session, michelins, shelf, "located_in", valid_from=T["tyres_swapped"])

        chain = await ent(session, "part", "KMC X12 chain", {"category": "drivetrain", "speeds": 12},
                          key="chain", at=T["chain_replaced"])
        await rel(session, chain, tarmac, "fitted_to", valid_from=T["chain_replaced"])

        battery = await ent(session, "part", "Zero ZF14.4 battery", {"category": "battery", "kwh": 14.4},
                            key="battery", at=T["zero_bought"])
        await rel(session, battery, zero, "fitted_to", valid_from=T["zero_bought"])

        # --- Tools -------------------------------------------------------
        torque = await ent(session, "tool", "Torque wrench 10-150 Nm", {"category": "hand tool"}, key="torque")
        stand = await ent(session, "tool", "Park Tool PCS-10 stand", {"category": "workshop"}, key="stand")
        charger = await ent(session, "tool", "Level 2 EV charger", {"category": "charging", "kw": 6}, key="charger")
        for tool in (torque, stand, charger):
            await rel(session, tool, shelf, "located_in")
        await rel(session, torque, outback, "compatible_with")
        await rel(session, torque, tarmac, "compatible_with")
        await rel(session, stand, tarmac, "compatible_with")
        await rel(session, charger, zero, "compatible_with")

        # --- Service records ---------------------------------------------
        oil = await ent(session, "service_record", "Oil and filter change", {
            "performed_at": T["outback_oil_change"].isoformat(), "odometer": 31000,
            "performed_by": "owner", "notes": "0W-20 synthetic, 5.1 qt",
        }, key="oil", at=T["outback_oil_change"])
        await rel(session, oil, outback, "service_for", valid_from=T["outback_oil_change"])

        swap = await ent(session, "service_record", "Tyre replacement", {
            "performed_at": T["tyres_swapped"].isoformat(), "odometer": 46800,
            "performed_by": "Tire Rack installer", "notes": "Michelins at 3/32; replaced all four",
        }, key="swap", at=T["tyres_swapped"])
        await rel(session, swap, outback, "service_for", valid_from=T["tyres_swapped"])
        await rel(session, swap, continentals, "used", valid_from=T["tyres_swapped"])
        await rel(session, swap, torque, "used", valid_from=T["tyres_swapped"])

        chain_job = await ent(session, "service_record", "Chain and bottom bracket service", {
            "performed_at": T["chain_replaced"].isoformat(), "odometer": 4900,
            "performed_by": "owner", "notes": "Chain at 0.75% wear; BB re-greased, creak gone",
        }, key="chain_job", at=T["chain_replaced"])
        await rel(session, chain_job, tarmac, "service_for", valid_from=T["chain_replaced"])
        await rel(session, chain_job, chain, "used", valid_from=T["chain_replaced"])

        # --- Issues: one resolved, one open --------------------------------
        creak = await ent(session, "issue", "Creaking bottom bracket", {
            "status": "resolved", "opened_at": T["bb_issue_opened"].isoformat(),
            "resolved_at": T["chain_replaced"].isoformat(), "severity": "minor",
        }, key="creak", at=T["bb_issue_opened"])
        await rel(session, creak, tarmac, "issue_for", valid_from=T["bb_issue_opened"])
        await rel(session, creak, chain_job, "resolved_by", valid_from=T["chain_replaced"])

        squeal = await ent(session, "issue", "Rear brake squeal", {
            "status": "open", "opened_at": T["brake_issue_opened"].isoformat(), "severity": "minor",
        }, key="squeal", at=T["brake_issue_opened"])
        await rel(session, squeal, outback, "issue_for", valid_from=T["brake_issue_opened"])

        # --- A note --------------------------------------------------------
        note = await ent(session, "note", "Zero charging note",
                         {"text": "Charge to 90% for daily use; balance to 100% monthly."}, key="zero_note")
        await rel(session, zero, note, "documented_by")

        await session.commit()


async def main() -> bool:
    print("🏍️  Populating the vehicles database...")
    populator = GraphPopulator(DATABASE_URL)
    try:
        await populator.setup_database()
        await populate_vehicles(populator)
        print(f"✅ {len(populator.entities)} entities seeded into {DATABASE_URL}")
        return True
    except Exception as exc:  # pragma: no cover - a seed failure is fatal and loud
        import traceback
        print(f"❌ vehicles seed failed: {exc}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
