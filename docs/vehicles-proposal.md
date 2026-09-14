# A logbook that remembers everything — proposal for a vehicle collection knowledge graph

*Draft for comment, September 2026. This is a personal system I am building for my own cars and bikes, on top of the knowledge graph that already runs my house. I would like input from people who keep collections before I fix the shape of it. Read it as "here is what I think a collection wants to remember"; tell me where you disagree.*

## The idea in one paragraph

Every vehicle gets a permanent, append-only record of its life — from the day you first looked at it (even if you didn't buy it) to long after you sold it. You add to that record by **walking round the car with your phone**: take pictures, talk, and the conversation becomes dated notes, parts, and events on the vehicle's timeline. Nothing is ever deleted; a change is a new entry with a date, so the record can always answer "what was on it in March" or "where was it while the engine was out". It is a logbook that can be asked questions, not a spreadsheet and not a telemetry feed.

## What it records

**The vehicle itself** — make, model, year, the identity numbers you actually have (VIN, frame number, registration), the nicknames you use for it, and a free-form specification: engine, drivetrain, paint code, trim, options, the build sheet if there is one. Factory spec is recorded once; what is on the car *now* is derived from that plus every modification that is still in force.

**Everything that happened to it, as dated events.** An event is *something that happened to this vehicle on a date*, with a mileage, a cost, a place, some text, and evidence (photos, receipts, documents). The kinds I expect: looking at it before buying · buying it · a service · a repair · a modification · an inspection · a fuel or charging stop · a track day, rally or show · selling it · seeing it again years later · a recall or a software update · a condition report during a restoration. I am deliberately *not* deciding the exact list yet — see "the experiment" below.

**Parts with their own identity.** Tyres, a gearbox, a wheelset, the original carburettor now on a shelf. A part is *fitted to* a vehicle for a period, so the record knows what was on it when, what replaced what, and where the displaced original went. Collectors care about originality; this is where it lives.

**Where things are.** Vehicles, parts and tools each have a location for a period — and the location need not be your house: a storage unit, the restorer's shop, a trailer, a friend's barn. "Where was it during the restoration" is answerable.

**Documents and photos** attached to the vehicle, a part, or an event: invoices, titles, certificates, period photographs, setup sheets, the pre-purchase inspection report.

## What it deliberately does not record

This is a **knowledge history**, not a data logger. The test for any entry is: *would you write it in the car's logbook?* An odometer reading on a service date, yes. Every drive, no. Fuel and fast-charge purchases, yes — a few hundred a year, they carry money and mileage. GPS traces and per-second telemetry, no; if a modern car has an app, the app's data is summarised into logbook-grade facts (an odometer on a date, a fault code, a recall) before anything reaches the record. A trip is recorded only when it is a *named event* — the drive home from the seller, the rally, the track day.

## How data gets in: the walk

The main way to add to a vehicle's record is a guided conversation on your phone, standing next to it. The assistant asks the questions appropriate to the kind of vehicle and the stage of its life, you answer and take pictures, and at the end it shows you exactly what it is about to record. Nothing is written until you say *confirm*; afterwards it reads everything back to check it landed. Different vehicles get different questions:

| Kind | The walk asks about |
|---|---|
| A car you drive | spec and options; what has been done and when; what is wrong; apps and feeds it has |
| A new car / EV | build sheet, warranty, software version, charging habits |
| A bike | frame and groupset; wheelsets and tyres as parts; fit; rides that were events |
| A race car | setup sheets; tyre sets and their life; the event log; scrutineering; damage and repairs |
| A restoration | originality of each part; provenance documents; phases of the work; condition reports with photos; where the displaced originals are |

And different stages of life get different questions: *evaluating* (what did the seller say, what did the inspection find, what did you decide — and why not), *owning*, *selling* (condition, price, buyer, what went with it), and *after* (where is it now; sightings).

## Examples

Vehicles from the actual collection (and one illustrative UK car), as the system would hold them. Dates, mileage and money are real fields; the text is what a walk transcribed. Each one stresses a different part of the design.

### A brand-new Mini Cooper SE, UK-registered — the app-connected daily driver

Identity is easy (VIN, a 26-plate registration mark). The interesting part is the **feed**: the MINI app knows every charge and every drive. Only the logbook-grade facts come in.

| When | Miles | Event | Evidence |
|---|---:|---|---|
| 2026-07-19 | 0 | **Evaluation** — test drove at MINI Cambridge; spec chosen: Level 3, Chili Red, black roof, 18" wheels. | build sheet PDF |
| 2026-08-30 | 6 | **Purchase** — delivered on a 26 plate, £36,500. Warranty and battery certificate attached; app paired; V5C to follow. | invoice, warranty PDF |
| 2026-08-30 | 6 | **Location** → UK house garage | |
| 2026-09-02 | 41 | **Software update** — from the app: 2026.3 (charging curve fix). | *from feed* |
| 2026-09-11 | 380 | **Charge** — fast charge, InstaVolt, Cambridge services: 31 kWh, £22.63, 18 min. | *from feed* |
| 2026-09-30 | 640 | **Odometer** — month-end reading from the app. | *from feed* |

What the app has that the logbook does not: the 22 home charges this month (summarised into one monthly `charge` event with kWh and cost), the 40 individual drives (not recorded), the live state of charge (not recorded). The rule is the same as for a paper logbook: fast charges you paid for, yes; every time you plugged in at home, one line a month; every drive, no.

### A 2010 Tesla Roadster with an OVMS box — the collector EV with telemetry

A Roadster is both a collector car and a car with a *third-party* data connection: the Open Vehicle Monitoring System reports state of charge, battery capacity (CAC), temperatures and location, continuously. The battery's health over years is exactly the kind of history the graph should hold — as a **periodic condition report**, not as the raw stream.

| When | Miles | Event | Evidence |
|---|---:|---|---|
| 2019-04-06 | 22,850 | **Evaluation** — Roadster 2.5 Sport, one owner, CAC 138 Ah reported. Viewed in Palo Alto. | 48 photos, OVMS screenshot |
| 2019-04-20 | 22,850 | **Purchase** — $62,000. Came with: original PEM, soft top, hard top, OVMS v2 fitted. | title, receipt |
| 2019-04-20 | — | **Location** → home garage | |
| 2020-01-31 | 24,100 | **Condition report** — battery: CAC 135 Ah, ideal range 202 mi. *(monthly, from OVMS)* | *from feed* |
| 2021-10-14 | 27,400 | **Service** — PEM fan replacement at Gruber Motors. *Fitted:* PEM fan (part). *Displaced:* original fan → parts bin. | invoice |
| 2023-06-03 | 29,900 | **Modification** — OVMS v3 module replaces v2. *Fitted:* OVMS v3 (part). | photos |
| 2024-08-17 | 30,600 | **Show** — Monterey, Tesla Roadster gathering. | 20 photos |
| 2026-01-31 | 31,850 | **Condition report** — battery: CAC 129 Ah, ideal range 189 mi. *(monthly, from OVMS)* | *from feed* |

Ask it *how has the battery aged* and it plots the monthly CAC readings — six years, 72 points — without ever having stored the per-minute telemetry OVMS actually produces. The OVMS box itself is a **part** with its own history (v2 fitted 2019, displaced by v3 in 2023) and an **app** that manages the car.

### A BMW E30-based 24 Hours of Lemons race car — stored elsewhere, no single VIN

The hard case, and the one the vocabulary has to survive. There is no one VIN: the shell has been replaced once, engines have come and gone, and what persists is the *team's car* — the Lemons logbook number and the roll cage. It lives at a storage yard with its **trailer** (a vehicle in its own right) and a pallet of **spares** (parts with identity, not fitted to anything). Events are races.

| When | Hours | Event | Evidence |
|---|---:|---|---|
| 2017-02-11 | — | **Purchase** — donor 1989 325i, $600, no title (bill of sale only). Shell VIN WBAAA…4471. | bill of sale |
| 2017-02-11 | — | **Location** → team storage yard, Hollister | |
| 2017-05-20 | 0 | **Modification** — cage built, Lemons logbook #4471-L issued; this is the car's identity from here on. | logbook scan, 30 photos |
| 2017-09-16 | 14 | **Race** — Thunderhill, 24h. Finished 31st. Setup sheet: 32/30 psi, 3° camber. | setup sheet, results |
| 2018-04-08 | 27 | **Repair** — spun engine bearing. *Displaced:* M20B25 #1 → scrap. *Fitted:* M20B25 #2 (from spares). | photos |
| 2019-11-02 | 55 | **Repair** — crash damage, shell scrapped. *Displaced:* shell WBAAA…4471. *Fitted:* shell WBAAA…9083 (a $300 donor). Cage, logbook, engine #2, suspension carried over. | 40 photos, Lemons tech re-inspection |
| 2020-02-01 | — | **Location** (spares pallet) → team storage yard, bay C. Contents: M20 #3, 2 gearboxes, 12 wheels, brake kits. | photos |
| 2024-06-15 | 96 | **Race** — Sonoma. DNF, fuel pump. *Fitted at track:* fuel pump (from spares). | results, photos |
| 2026-03-07 | — | **Location** (trailer) → home driveway for the season | |

What the walk needs to ask here that it never asks a road car: *which car is this* — the answer is "logbook #4471-L, currently on shell …9083, engine #2"; *what is in the spares pile and where*; *what is the trailer*. Hours, not miles. Identity is a **set of numbers over time**, and the graph handles that because the shell is just another part with an interval.

### A 2009 Porsche Boxster S — a gas car in the family since new

The long, ordinary history: seventeen years, one family, a folder of receipts. What the record adds is the *shape* of that history — the handover inside the family, the trip everyone remembers, and fuel as a logbook line rather than a bank statement.

| When | Miles | Event | Evidence |
|---|---:|---|---|
| 2009-05-16 | 12 | **Purchase** — bought new by Dad at Porsche Redwood City, $61,000. Window sticker in the folder. | window sticker, invoice |
| 2009-05-16 | — | **Location** → home garage | |
| 2011-06-04 | 12,300 | **Service** — oil and filter, dealer. | invoice |
| 2014-08-09 | 31,200 | **Road trip** — PCH to Big Sur; top down the whole way. | 40 photos |
| 2016-03-12 | 48,000 | **Service** — clutch and flywheel at an independent. *Fitted:* clutch kit. "Everyone learned to drive stick on the old one." | invoice |
| 2019-10-05 | 64,500 | **Transfer** — title transferred within the family; Dad kept the spare key. | title |
| 2021-07-17 | 72,100 | **Repair** — rear window seam failed; whole top replaced. *Fitted:* convertible top. | invoice, photos |
| 2023-02-11 | 80,300 | **Inspection** — California smog: pass. | certificate |
| 2025-04-19 | 88,900 | **Service** — four tyres, front pads and discs. | invoice |
| 2026-09-06 | 91,400 | **Fuel** — Chevron, Woodside: 14.1 gal premium, $71.20. | |

Ask it *what has this car cost since it came to me* and it sums the events after the transfer; *when was the clutch done* and it answers with the invoice attached.

### A UK-registered car — the other side of the Atlantic *(illustrative)*

The collection straddles the US and the UK (the Mini above is UK-registered), and the admin differs. In the UK the **registration mark** is the working identity, the V5C is the logbook, road tax and SORN are states the car is in, and — usefully — **the MOT history is a public feed** (DVLA), so every annual test arrives as an inspection event with its advisories and mileage. Money is in pounds, fuel in litres. The record holds all of that per vehicle; nothing about the design is American.

| When | Miles | Event | Evidence |
|---|---:|---|---|
| 2015-06-13 | 48,900 | **Purchase** — 1998 Lotus Elise S1, R123 LTS, at auction, Bicester, £14,500. V5C in the folder. | V5C scan, invoice |
| 2015-06-13 | — | **Location** → lock-up, Cambridge | |
| 2024-05-09 | 59,800 | **Inspection** — MOT pass; advisory: nearside front tyre wearing on inner edge. £54.85. | *from DVLA feed* |
| 2025-05-07 | 60,900 | **Inspection** — MOT pass, no advisories. | *from DVLA feed* |
| 2025-08-16 | 61,200 | **Fuel** — Shell, Newmarket Road: 45.2 litres super unleaded, £68.40. | |
| 2025-11-01 | — | **SORN** — off the road for the winter; declared with DVLA. | |

## The experiment

I do not think the right set of entities can be designed at a desk. The plan is to walk a few vehicles of each kind with a deliberately loose vocabulary — "vehicle, part, location, event-of-some-kind, note, photo, document" — and then look at what actually recurs with structure. Services always have mileage and parts; modifications always have a displaced original and a reversible flag; track days have a venue and a setup. Those become proper things. The rest stay as dated events with text and pictures. That is how the house side of this system found its real vocabulary too: from live data, not from the design.

## What I would like from you

1. **The questions you would ask it.** Given a collection of N vehicles with this record, what do you want to know — about one car, across all of them, about money, about time?
2. **What you record today and where.** Spreadsheet, folder of receipts, a notes app, memory? What do you always wish you had written down?
3. **What a walk should ask for *your* kind of vehicle** — especially race cars and restorations, where I know least.
4. **Identity, and country.** What is *the* number for a car in your world — VIN, chassis number, registration mark, something else? For bikes? For race cars that have been re-shelled? If you keep cars in more than one country, what admin do you track for each (MOT, tax, SORN, title, smog)?
5. **After the sale.** Do you keep following cars you sold? What would you want recorded?
6. **Apps and feeds.** Which of your vehicles have apps, and what from them is worth keeping in a logbook rather than in the app?
7. **Anything here that is wrong** for a collection — a distinction I have missed or one I have invented.

Short answers in any form are fine. The record of *your* input will be, appropriately, a dated event.
