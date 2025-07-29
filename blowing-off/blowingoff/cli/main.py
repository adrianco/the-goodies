"""
Blowing-Off Client - Command Line Interface

DEVELOPMENT CONTEXT:
Created as the interactive testing interface in January 2024. This CLI provides
a comprehensive way to test all aspects of the Inbetweenies protocol and the
Blowing-Off client implementation. It serves as both a development tool and a
reference for how the client API should be used. The Swift/WildThing client
should provide similar functionality through its UI.

FUNCTIONALITY:
- Connect to FunkyGibbon server with authentication
- Perform manual and automated synchronization
- Browse and manage houses, rooms, and devices
- View and update device states in real-time
- Monitor sync status and conflict resolution
- Run background sync daemon for continuous operation
- Store connection credentials securely
- Provide formatted output for all operations

PURPOSE:
This CLI enables:
- Interactive testing of sync protocol
- Debugging sync issues and conflicts
- Simulating real-world usage patterns
- Performance testing with various scenarios
- Demonstrating client capabilities
- Validating server compatibility

KNOWN ISSUES:
- No support for multiple simultaneous connections
- Limited error handling in some commands
- Missing bulk operations for testing
- No export/import functionality
- Basic credential storage (plain text)

REVISION HISTORY:
- 2024-01-15: Initial CLI implementation
- 2024-01-18: Added sync daemon mode
- 2024-01-20: Enhanced device management commands
- 2024-01-22: Added formatted output with tabulate
- 2024-01-25: Improved error handling and status display

DEPENDENCIES:
- click for command-line interface
- tabulate for formatted table output
- asyncio for async command execution
- BlowingOffClient for all operations

USAGE:
    # Connect to server
    blowingoff connect --server-url https://api.thegoodies.app --auth-token TOKEN
    
    # Perform manual sync
    blowingoff sync
    
    # Run background sync
    blowingoff sync-daemon --interval 30
    
    # List devices in a room
    blowingoff device list --room-id living-room-1
    
    # Update device state
    blowingoff device set-state light-1 '{"on": true, "brightness": 80}'
"""

import asyncio
import json
from pathlib import Path
import click
from tabulate import tabulate
from datetime import datetime

from ..client import BlowingOffClient


# Global client instance
client = None


def get_client():
    """Get or create client instance."""
    global client
    if not client:
        client = BlowingOffClient()
    return client


@click.group()
def cli():
    """Blowing-Off: Python test client for The Goodies smart home system."""
    pass


@cli.command()
@click.option("--server-url", required=True, help="FunkyGibbon server URL")
@click.option("--auth-token", required=True, help="Authentication token")
@click.option("--client-id", help="Client ID (auto-generated if not provided)")
@click.option("--db-path", default="blowingoff.db", help="Local database path")
def connect(server_url, auth_token, client_id, db_path):
    """Connect to FunkyGibbon server."""
    async def _connect():
        client = BlowingOffClient(db_path)
        await client.connect(server_url, auth_token, client_id)
        
        # Save connection info
        config = {
            "server_url": server_url,
            "auth_token": auth_token,
            "client_id": client.sync_engine.client_id,
            "db_path": db_path
        }
        Path(".blowingoff.json").write_text(json.dumps(config, indent=2))
        
        click.echo(f"✅ Connected to {server_url}")
        click.echo(f"Client ID: {config['client_id']}")
        
    asyncio.run(_connect())


@cli.command()
def sync():
    """Perform manual sync with server."""
    async def _sync():
        client = await load_client()
        click.echo("🔄 Starting sync...")
        
        result = await client.sync()
        
        if result.success:
            click.echo(f"✅ Sync completed successfully")
            click.echo(f"  Synced entities: {result.synced_entities}")
            click.echo(f"  Conflicts resolved: {result.conflicts_resolved}")
            click.echo(f"  Duration: {result.duration:.2f}s")
        else:
            click.echo(f"❌ Sync failed")
            for error in result.errors:
                click.echo(f"  Error: {error}")
                
        if result.conflicts:
            click.echo(f"\n⚠️  {len(result.conflicts)} conflicts detected:")
            for conflict in result.conflicts[:5]:
                click.echo(f"  - {conflict.entity_type} {conflict.entity_id}: {conflict.reason}")
                
    asyncio.run(_sync())


@cli.command()
@click.option("--interval", default=30, help="Sync interval in seconds")
def sync_daemon(interval):
    """Run background sync daemon."""
    async def _daemon():
        client = await load_client()
        click.echo(f"🔄 Starting sync daemon (interval: {interval}s)")
        click.echo("Press Ctrl+C to stop")
        
        await client.start_background_sync(interval)
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            click.echo("\n👋 Stopping sync daemon")
            await client.disconnect()
            
    asyncio.run(_daemon())


@cli.command()
def status():
    """Show sync status."""
    async def _status():
        client = await load_client()
        status = await client.get_sync_status()
        
        table = [
            ["Last Sync", status["last_sync"] or "Never"],
            ["Last Success", status["last_success"] or "Never"],
            ["Total Syncs", status["total_syncs"]],
            ["Sync Failures", status["sync_failures"]],
            ["Total Conflicts", status["total_conflicts"]],
            ["In Progress", "Yes" if status["sync_in_progress"] else "No"],
            ["Last Error", status["last_error"] or "None"]
        ]
        
        click.echo("\n📊 Sync Status")
        click.echo(tabulate(table, tablefmt="simple"))
        
    asyncio.run(_status())


@cli.group()
def house():
    """House management commands."""
    pass


@house.command("show")
def house_show():
    """Show house information."""
    async def _show():
        client = await load_client()
        house = await client.get_house()
        
        if house:
            click.echo(f"\n🏠 House: {house['name']}")
            click.echo(f"   ID: {house['id']}")
            click.echo(f"   Address: {house['address'] or 'Not set'}")
            click.echo(f"   Timezone: {house['timezone']}")
            
            rooms = await client.get_rooms(house['id'])
            click.echo(f"   Rooms: {len(rooms)}")
        else:
            click.echo("❌ No house found")
            
    asyncio.run(_show())


@house.command("create")
@click.option("--name", required=True, help="House name")
@click.option("--address", help="House address")
@click.option("--timezone", default="UTC", help="Timezone (default: UTC)")
def house_create(name, address, timezone):
    """Create a new house."""
    async def _create():
        client = await load_client()
        house_id = await client.create_house(name, address=address, timezone=timezone)
        click.echo(f"✅ Created house: {house_id}")
        
    asyncio.run(_create())


@cli.group()
def room():
    """Room management commands."""
    pass


@room.command("list")
def room_list():
    """List all rooms."""
    async def _list():
        client = await load_client()
        rooms = await client.get_rooms()
        
        if rooms:
            headers = ["ID", "Name", "Floor", "Type"]
            rows = [
                [r["id"], r["name"], r["floor"], r["room_type"] or "-"]
                for r in rooms
            ]
            click.echo("\n📋 Rooms")
            click.echo(tabulate(rows, headers=headers, tablefmt="simple"))
        else:
            click.echo("❌ No rooms found")
            
    asyncio.run(_list())


@room.command("create")
@click.option("--house-id", required=True, help="House ID")
@click.option("--name", required=True, help="Room name")
@click.option("--floor", default=0, help="Floor number")
@click.option("--type", help="Room type")
def room_create(house_id, name, floor, type):
    """Create a new room."""
    async def _create():
        client = await load_client()
        room_id = await client.create_room(
            house_id, name, floor=floor, room_type=type
        )
        click.echo(f"✅ Created room: {room_id}")
        
    asyncio.run(_create())


@cli.group()
def device():
    """Device management commands."""
    pass


@device.command("list")
@click.option("--room-id", help="Filter by room")
def device_list(room_id):
    """List devices."""
    async def _list():
        client = await load_client()
        devices = await client.get_devices(room_id)
        
        if devices:
            headers = ["ID", "Name", "Type", "Room", "Manufacturer"]
            rows = [
                [
                    d["id"][:12] + "...",
                    d["name"],
                    d["device_type"],
                    d["room_id"][:12] + "...",
                    d["manufacturer"] or "-"
                ]
                for d in devices
            ]
            click.echo("\n📱 Devices")
            click.echo(tabulate(rows, headers=headers, tablefmt="simple"))
        else:
            click.echo("❌ No devices found")
            
    asyncio.run(_list())


@device.command("create")
@click.option("--room-id", required=True, help="Room ID")
@click.option("--name", required=True, help="Device name")
@click.option("--type", required=True, type=click.Choice([
    "light", "switch", "sensor", "thermostat", "lock", "camera", "speaker", "other"
]), help="Device type")
@click.option("--manufacturer", help="Manufacturer")
@click.option("--model", help="Model")
def device_create(room_id, name, type, manufacturer, model):
    """Create a new device."""
    async def _create():
        client = await load_client()
        device_id = await client.create_device(
            room_id, name, type,
            manufacturer=manufacturer,
            model=model
        )
        click.echo(f"✅ Created device: {device_id}")
        
    asyncio.run(_create())


@device.command("state")
@click.argument("device_id")
def device_state(device_id):
    """Show device state."""
    async def _state():
        client = await load_client()
        state = await client.get_device_state(device_id)
        
        if state:
            click.echo(f"\n💡 Device State: {device_id}")
            click.echo(f"   State: {json.dumps(state['state'], indent=2)}")
            click.echo(f"   Attributes: {json.dumps(state['attributes'], indent=2)}")
            click.echo(f"   Updated: {state['updated_at']}")
        else:
            click.echo("❌ No state found")
            
    asyncio.run(_state())


@device.command("set-state")
@click.argument("device_id")
@click.argument("state_json")
def device_set_state(device_id, state_json):
    """Update device state."""
    async def _set_state():
        client = await load_client()
        
        try:
            state = json.loads(state_json)
        except json.JSONDecodeError:
            click.echo("❌ Invalid JSON")
            return
            
        await client.update_device_state(device_id, state)
        click.echo(f"✅ Updated device state")
        
    asyncio.run(_set_state())


async def load_client():
    """Load client with saved connection info."""
    config_path = Path(".blowingoff.json")
    if not config_path.exists():
        click.echo("❌ Not connected. Run 'blowingoff connect' first.")
        raise click.Abort()
        
    config = json.loads(config_path.read_text())
    
    client = BlowingOffClient(config["db_path"])
    await client.connect(config["server_url"], config["auth_token"], config["client_id"])
    
    return client


if __name__ == "__main__":
    cli()