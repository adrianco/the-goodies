"""The house's own MCP tools (ADR-012 §2).

Four of the five house tools need more than a type filter and a relationship
walk -- ``find_device_controls`` reads capabilities off the device's content,
``get_room_connections`` reports which door or passage each edge came through,
``get_procedures_for_device`` merges two walks into one answer and
``get_automations_in_room`` annotates each automation with the devices it
touches -- so they are handlers. ``get_devices_in_room`` is the walk the
declarative form exists for and lives in the manifest as data.

These used to be methods on the engine's ``MCPTools``, which meant the engine
knew what a room was. Now they take the ``ops`` they run against (FunkyGibbon's
SQL store, a replica's local store, a test double) and the engine dispatches to
them by name from the manifest, exactly as it would for any other domain.
"""

from typing import Optional

from inbetweenies.mcp.tools import ToolResult, _parse_at


async def find_device_controls(ops, device_id: str, at: Optional[str] = None) -> ToolResult:
    """Get available controls and services for a device"""
    try:
        moment = _parse_at(at)
        device = await ops.get_entity(device_id, at=moment)
        if not device or device.entity_type != "device":
            return ToolResult(False, None, f"Device {device_id} not found")

        # Get capabilities from device content
        capabilities = device.content.get("capabilities", []) if device.content else []

        # Get devices this device controls
        controls_relationships = await ops.get_relationships(at=moment, from_id=device_id,
            rel_type="controls"
        )

        controlled_devices = []
        for rel in controls_relationships:
            controlled = await ops.get_entity(rel.to_entity_id, at=moment)
            if controlled:
                controlled_devices.append({
                    "id": controlled.id,
                    "name": controlled.name,
                    "type": getattr(controlled.entity_type, "value", controlled.entity_type)
                })

        return ToolResult(True, {
            "device_id": device_id,
            "device_name": device.name,
            "capabilities": capabilities,
            "controlled_devices": controlled_devices,
            "services": device.content.get("services", []) if device.content else []
        })

    except Exception as e:
        return ToolResult(False, None, str(e))

async def get_room_connections(ops, room_id: str, at: Optional[str] = None) -> ToolResult:
    """Find all rooms connected to a given room"""
    try:
        moment = _parse_at(at)
        room = await ops.get_entity(room_id, at=moment)
        if not room or room.entity_type != "room":
            return ToolResult(False, None, f"Room {room_id} not found")

        # Outgoing connections
        outgoing = await ops.get_relationships(at=moment, from_id=room_id,
            rel_type="connects_to"
        )

        # Incoming connections
        incoming = await ops.get_relationships(at=moment, to_id=room_id,
            rel_type="connects_to"
        )

        connected_rooms = {}

        for rel in outgoing + incoming:
            other_id = rel.to_entity_id if rel.from_entity_id == room_id else rel.from_entity_id

            if other_id not in connected_rooms:
                other_room = await ops.get_entity(other_id, at=moment)
                if other_room and other_room.entity_type == "room":
                    connected_rooms[other_id] = {
                        "id": other_room.id,
                        "name": other_room.name,
                        "connection_type": rel.properties.get("via", "direct") if rel.properties else "direct"
                    }

        return ToolResult(True, {
            "room_id": room_id,
            "room_name": room.name,
            "connections": list(connected_rooms.values()),
            "connection_count": len(connected_rooms)
        })

    except Exception as e:
        return ToolResult(False, None, str(e))

async def get_procedures_for_device(ops, device_id: str, at: Optional[str] = None) -> ToolResult:
    """Get procedures and manuals for a device"""
    try:
        moment = _parse_at(at)
        device = await ops.get_entity(device_id, at=moment)
        if not device or device.entity_type != "device":
            return ToolResult(False, None, f"Device {device_id} not found")

        procedures = []
        manuals = []

        # Get procedures
        proc_relationships = await ops.get_relationships(at=moment, to_id=device_id,
            rel_type="procedure_for"
        )

        for rel in proc_relationships:
            proc = await ops.get_entity(rel.from_entity_id, at=moment)
            if proc and proc.entity_type == "procedure":
                procedures.append({
                    "id": proc.id,
                    "name": proc.name,
                    "content": proc.content
                })

        # Get manuals
        manual_relationships = await ops.get_relationships(at=moment, from_id=device_id,
            rel_type="documented_by"
        )

        for rel in manual_relationships:
            manual = await ops.get_entity(rel.to_entity_id, at=moment)
            if manual and manual.entity_type == "manual":
                manuals.append({
                    "id": manual.id,
                    "name": manual.name,
                    "content": manual.content
                })

        return ToolResult(True, {
            "device_id": device_id,
            "device_name": device.name,
            "procedures": procedures,
            "manuals": manuals,
            "total_documentation": len(procedures) + len(manuals)
        })

    except Exception as e:
        return ToolResult(False, None, str(e))

async def get_automations_in_room(ops, room_id: str, at: Optional[str] = None) -> ToolResult:
    """Find all automations affecting a room"""
    try:
        moment = _parse_at(at)
        room = await ops.get_entity(room_id, at=moment)
        if not room or room.entity_type != "room":
            return ToolResult(False, None, f"Room {room_id} not found")

        # Get devices in room
        device_rels = await ops.get_relationships(at=moment, to_id=room_id,
            rel_type="located_in"
        )

        device_ids = {rel.from_entity_id for rel in device_rels}

        # Find automations that control these devices
        automations = []
        seen_automations = set()

        for device_id in device_ids:
            auto_rels = await ops.get_relationships(at=moment, to_id=device_id,
                rel_type="automates"
            )

            for rel in auto_rels:
                if rel.from_entity_id not in seen_automations:
                    automation = await ops.get_entity(rel.from_entity_id, at=moment)
                    if automation and automation.entity_type == "automation":
                        automations.append({
                            "id": automation.id,
                            "name": automation.name,
                            "content": automation.content,
                            "affects_devices": []
                        })
                        seen_automations.add(automation.id)

            # Track which devices are affected
            for auto in automations:
                if auto["id"] in [r.from_entity_id for r in auto_rels]:
                    device = await ops.get_entity(device_id, at=moment)
                    if device:
                        auto["affects_devices"].append({
                            "id": device.id,
                            "name": device.name
                        })

        # An automation may also automate the room as a whole (the vocabulary
        # allows automation -> room). Blowing-off's replica reported these and
        # the server did not; now both do, from this one handler.
        for rel in await ops.get_relationships(at=moment, to_id=room_id, rel_type="automates"):
            if rel.from_entity_id in seen_automations:
                continue
            automation = await ops.get_entity(rel.from_entity_id, at=moment)
            if automation and automation.entity_type == "automation":
                automations.append({"id": automation.id, "name": automation.name,
                                    "content": automation.content, "affects_devices": []})
                seen_automations.add(automation.id)

        return ToolResult(True, {
            "room_id": room_id,
            "room_name": room.name,
            "automations": automations,
            "automation_count": len(automations)
        })

    except Exception as e:
        return ToolResult(False, None, str(e))
