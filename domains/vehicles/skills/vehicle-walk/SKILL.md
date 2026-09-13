---
name: vehicle-walk
description: Walk the garage with the owner and record each vehicle -- what it is, what is fitted to it, which tools and spares serve it, where it is kept, what was bought when, and what has been done to it -- as entities and dated relationships in the vehicles graph via MCP tools. The vehicles domain's counterpart of the house room walk.
---

# Vehicle walk

A guided walk through a collection of vehicles -- cars, motorcycles, bicycles,
e-bikes, trailers -- that records what the owner tells you as a graph, one
vehicle at a time, using the vehicles domain's MCP tools. It works the way the
house room walk works: you ask, the owner answers, and every answer becomes an
entity or a relationship *now*, so nothing is lost if the walk stops early.

The graph is append-only and temporal. Fitting a part is an interval edge;
taking it off **ends** that edge rather than deleting it. Record dates as the
owner remembers them -- "last August" is better than nothing -- because the
history tools answer "what was on the bike then" from exactly these dates.

## Before you start

1. Confirm the MCP server you are talking to serves the **vehicles** domain:
   `get_statistics` should count `vehicle` / `part` / `tool`, and the tool
   list should include `get_parts_on_vehicle`. If you see `get_devices_in_room`
   you are on a house server -- stop and say so.
2. `list_entities` with `entity_type: location` and `entity_type: vehicle` to
   learn what is already recorded. Never create a duplicate of something that
   exists; update it (`update_entity`) or add to it.

## The walk, per vehicle

Ask in this order. Create as you go.

1. **The vehicle.** Kind (car / motorcycle / bicycle / ebike / trailer), make,
   model, year, registration or frame number, current odometer and its unit.
   `create_entity` with `entity_type: vehicle` and those fields in `content`
   (use the key names `kind`, `make`, `model`, `year`, `registration`,
   `odometer`, `odometer_unit`). Offer to `attach_photo`.
2. **Where it lives.** A bay, a shed, a rack. `create_entity` a `location` if
   it is new, then `create_relationship` `located_in` vehicle → location.
3. **How it was acquired.** Date, vendor, price. `create_entity` a `purchase`
   with `content.date` (ISO-8601), `vendor`, `price`, `currency`; then
   `purchased_via` vehicle → purchase. If there is a receipt, `attach_document`
   it to the purchase (it becomes an `invoice`).
4. **What is fitted to it.** Walk round it: tyres, chain, battery, brake pads,
   rack, lights -- anything the owner replaces or would want to track. Each is
   a `part` (`content.category`, size or spec); link with `fitted_to`
   part → vehicle. If the owner knows when it went on, say so in the
   relationship's `properties` as `fitted_on` for now; the edge's own start is
   the moment you record it.
5. **What was taken off and kept.** A part on the shelf that used to be on the
   vehicle: create it, `located_in` its shelf, and if its replacement is known,
   `replaced` new → old. Do not invent a `fitted_to` for it.
6. **Tools and spares.** Workshop tools and spare parts that serve this
   vehicle but are not on it: `tool` or `part`, `located_in` where kept,
   `compatible_with` item → vehicle.
7. **What has been done to it.** Each service, repair or inspection is a
   `service_record`: `content.performed_at` (ISO-8601), `odometer`,
   `performed_by`, `notes`; then `service_for` record → vehicle, and `used`
   record → part/tool for anything fitted or used.
8. **What is wrong with it.** Each open problem is an `issue`:
   `content.status: open`, `opened_at`, `severity`; `issue_for` issue →
   vehicle. When a service fixed one, `update_entity` the issue to
   `status: resolved` with `resolved_at`, and add `resolved_by` issue → record.
9. **Anything else** is a `note`, attached with `documented_by`.

Then say what you recorded for that vehicle in three lines and move on.

## Finishing

Run `get_vehicle_history` for each vehicle you touched and read it back to the
owner as a short timeline. Ask what is missing. `get_open_issues` per vehicle
is the natural to-do list to leave them with.

## Rules

- Never delete. Ending a `fitted_to` edge (`end_relationship`) is how a part
  comes off; `tombstone_entity` is only for something recorded in error.
- One vehicle type, `content.kind` says which. Do not invent `car` or `bike`
  entity types; the server will refuse them.
- Dates are ISO-8601 strings in `content`. Odometers are numbers plus a unit.
- If a tool call fails with "unknown entity_type" or "does not permit", the
  vocabulary is telling you the shape; re-read it, do not work around it.
