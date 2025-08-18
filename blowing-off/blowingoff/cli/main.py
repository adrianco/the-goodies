#!/usr/bin/env python3
"""
Blowing-Off CLI - Command line interface for The Goodies client

This tool provides direct access to the graph API and MCP tools,
matching the functionality of oook but for the client-side.
"""

import json
import sys
import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path

import click
import httpx
from tabulate import tabulate
from rich.console import Console
from rich.table import Table
from rich.json import JSON
from rich.panel import Panel

from ..client import BlowingOffClient

console = Console()

# Global client instance
client = None


def get_client():
    """Get or create client instance."""
    global client
    if client is None:
        client = BlowingOffClient()
    return client


async def load_client():
    """Load client with saved connection info."""
    config_path = Path(".blowingoff.json")
    if not config_path.exists():
        console.print("[red]❌ Not connected. Run 'blowing-off connect' first.[/red]")
        raise click.Abort()

    config = json.loads(config_path.read_text())

    client = BlowingOffClient(config["db_path"])
    await client.connect(config["server_url"], config["auth_token"], config.get("client_id"))

    return client


def save_config(server_url: str, auth_token: str, client_id: str, db_path: str):
    """Save connection configuration."""
    config = {
        "server_url": server_url,
        "auth_token": auth_token,
        "client_id": client_id,
        "db_path": db_path
    }
    config_path = Path(".blowingoff.json")
    config_path.write_text(json.dumps(config, indent=2))


@click.group()
def cli():
    """Blowing-Off: Client for The Goodies smart home system.

    This tool provides direct access to graph operations and MCP tools
    for the client-side, with sync capabilities.
    """
    pass


@cli.command()
@click.option("--server-url", required=True, help="FunkyGibbon server URL")
@click.option("--auth-token", required=True, help="Authentication token")
@click.option("--client-id", default=None, help="Client device ID")
@click.option("--db-path", default="blowingoff.db", help="Local database path")
def connect(server_url, auth_token, client_id, db_path):
    """Connect to FunkyGibbon server."""
    async def _connect():
        client = BlowingOffClient(db_path)
        await client.connect(server_url, auth_token, client_id)

        # Save configuration
        save_config(server_url, auth_token, client_id or "default", db_path)

        console.print(f"[green]✅ Connected to {server_url}[/green]")
        console.print(f"[dim]Configuration saved to .blowingoff.json[/dim]")

        await client.disconnect()

    asyncio.run(_connect())


@cli.command()
def disconnect():
    """Disconnect and remove saved configuration."""
    config_path = Path(".blowingoff.json")
    if config_path.exists():
        config_path.unlink()
        console.print("[green]✅ Disconnected[/green]")
    else:
        console.print("[yellow]Not connected[/yellow]")


@cli.command()
def status():
    """Show sync status and connection info."""
    async def _status():
        client = await load_client()
        status = await client.get_sync_status()

        # Connection info
        config_path = Path(".blowingoff.json")
        config = json.loads(config_path.read_text())

        console.print("\n[bold]Connection Info[/bold]")
        console.print(f"Server: {config['server_url']}")
        console.print(f"Client ID: {config['client_id']}")
        console.print(f"Database: {config['db_path']}")

        # Sync status
        console.print("\n[bold]Sync Status[/bold]")
        table_data = [
            ["Last Sync", status["last_sync"] or "Never"],
            ["Last Success", status["last_success"] or "Never"],
            ["Total Syncs", status["total_syncs"]],
            ["Sync Failures", status["sync_failures"]],
            ["Total Conflicts", status["total_conflicts"]],
            ["In Progress", "Yes" if status["sync_in_progress"] else "No"],
            ["Last Error", status["last_error"] or "None"]
        ]

        print(tabulate(table_data, tablefmt="simple"))

        await client.disconnect()

    asyncio.run(_status())


@cli.command()
@click.option("--full", is_flag=True, help="Force full sync")
def sync(full):
    """Perform sync with server."""
    async def _sync():
        client = await load_client()
        console.print("[cyan]🔄 Starting sync...[/cyan]")

        try:
            result = await client.sync()

            console.print(f"\n[green]✅ Sync completed![/green]")
            console.print(f"  Entities synced: {result.synced_entities}")
            console.print(f"  Changes sent: {getattr(result, 'changes_sent', 0)}")
            console.print(f"  Changes received: {getattr(result, 'changes_received', 0)}")
            console.print(f"  Conflicts resolved: {result.conflicts_resolved}")
            console.print(f"  Duration: {result.duration:.2f}s")

            if result.conflicts:
                console.print(f"\n[yellow]⚠️  {len(result.conflicts)} conflicts detected:[/yellow]")
                for conflict in result.conflicts[:5]:
                    console.print(f"  - {conflict.entity_type} {conflict.entity_id}: {conflict.reason}")

        except Exception as e:
            console.print(f"[red]❌ Sync failed: {e}[/red]")
        finally:
            await client.disconnect()

    asyncio.run(_sync())


@cli.command("sync-daemon")
@click.option("--interval", default=30, help="Sync interval in seconds")
def sync_daemon(interval):
    """Run background sync daemon."""
    async def _daemon():
        client = await load_client()
        console.print(f"[cyan]🔄 Starting sync daemon (interval: {interval}s)[/cyan]")
        console.print("[dim]Press Ctrl+C to stop[/dim]")

        try:
            await client.start_background_sync(interval)
            # Keep running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]👋 Stopping sync daemon[/yellow]")
            await client.disconnect()

    asyncio.run(_daemon())


@cli.command()
def tools():
    """List available MCP tools."""
    async def _tools():
        client = await load_client()

        tools = client.get_available_mcp_tools()

        table = Table(title="Available MCP Tools", show_lines=True)
        table.add_column("Tool Name", style="cyan", no_wrap=True)
        table.add_column("Description", style="white")

        # Get tool descriptions from the MCP client
        for tool_name in tools:
            # For now, just show the tool name
            # In a full implementation, we'd get descriptions from tool metadata
            table.add_row(tool_name, "MCP tool for graph operations")

        console.print(table)

        await client.disconnect()

    asyncio.run(_tools())


@cli.command()
@click.argument('tool_name')
@click.option('--args', '-a', multiple=True, help='Tool arguments in key=value format')
@click.option('--json-args', '-j', help='Tool arguments as JSON string')
def execute(tool_name, args, json_args):
    """Execute an MCP tool.

    Examples:

        blowing-off execute search_entities -a query="smart light"

        blowing-off execute get_devices_in_room --json-args '{"room_id": "abc123"}'
    """
    async def _execute():
        client = await load_client()

        # Parse arguments
        arguments = {}

        if json_args:
            try:
                arguments = json.loads(json_args)
            except json.JSONDecodeError as e:
                console.print(f"[red]Invalid JSON: {e}[/red]")
                sys.exit(1)

        for arg in args:
            if '=' not in arg:
                console.print(f"[red]Invalid argument format: {arg} (use key=value)[/red]")
                sys.exit(1)

            key, value = arg.split('=', 1)

            # Try to parse value as JSON first
            try:
                arguments[key] = json.loads(value)
            except json.JSONDecodeError:
                # If not JSON, treat as string
                arguments[key] = value

        try:
            console.print(f"[cyan]Executing {tool_name} with arguments:[/cyan]")
            console.print(JSON(json.dumps(arguments, indent=2)))

            result = await client.execute_mcp_tool(tool_name, **arguments)

            console.print("\n[green]Result:[/green]")
            console.print(JSON(json.dumps(result, indent=2)))

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)
        finally:
            await client.disconnect()

    asyncio.run(_execute())


@cli.command()
@click.argument('query')
@click.option('--type', '-t', 'entity_types', multiple=True, help='Filter by entity type')
@click.option('--limit', '-l', default=10, help='Maximum results')
def search(query, entity_types, limit):
    """Search for entities locally.

    Examples:

        blowing-off search "smart light"

        blowing-off search "light" -t device -t automation
    """
    async def _search():
        client = await load_client()

        try:
            # Use the search_entities MCP tool
            result = await client.execute_mcp_tool(
                "search_entities",
                query=query,
                entity_types=list(entity_types) if entity_types else None,
                limit=limit
            )

            if result.get('success') and 'result' in result:
                search_results = result['result']
                console.print(f"\n[bold]Search Results for '{query}':[/bold]\n")

                for item in search_results.get('results', []):
                    entity = item['entity']
                    score = item.get('score', 0)

                    console.print(Panel(
                        f"[cyan]Name:[/cyan] {entity['name']}\n"
                        f"[cyan]Type:[/cyan] {entity['entity_type']}\n"
                        f"[cyan]ID:[/cyan] {entity['id']}\n"
                        f"[cyan]Score:[/cyan] {score:.2f}",
                        title=f"[bold]{entity['name']}[/bold]"
                    ))

                    if item.get('highlights'):
                        console.print("[yellow]Highlights:[/yellow]")
                        for highlight in item['highlights']:
                            console.print(f"  • {highlight}")

                    console.print()

                console.print(f"[dim]Found {search_results.get('count', 0)} results[/dim]")
            else:
                console.print("[yellow]No results found[/yellow]")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await client.disconnect()

    asyncio.run(_search())


@cli.command()
@click.argument('entity_type', type=click.Choice([
    'home', 'room', 'device', 'zone', 'door', 'window',
    'procedure', 'manual', 'note', 'schedule', 'automation'
]))
@click.argument('name')
@click.option('--content', '-c', help='Entity content as JSON')
def create(entity_type, name, content):
    """Create a new entity locally.

    Examples:

        blowing-off create device "Smart Bulb"

        blowing-off create room "Kitchen" -c '{"area": 25, "floor": 1}'
    """
    async def _create():
        client = await load_client()

        content_data = {}
        if content:
            try:
                content_data = json.loads(content)
            except json.JSONDecodeError as e:
                console.print(f"[red]Invalid JSON content: {e}[/red]")
                sys.exit(1)

        try:
            result = await client.execute_mcp_tool(
                "create_entity",
                entity_type=entity_type,
                name=name,
                content=content_data,
                user_id="blowing-off-cli"
            )

            if result.get('success'):
                console.print("[green]Entity created successfully![/green]\n")
                console.print(JSON(json.dumps(result['result'], indent=2)))
            else:
                console.print(f"[red]Failed to create entity: {result.get('error', 'Unknown error')}[/red]")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await client.disconnect()

    asyncio.run(_create())


@cli.command()
def stats():
    """Show local graph statistics."""
    async def _stats():
        client = await load_client()

        try:
            # Get statistics from the local graph
            stats = client.graph_storage.get_statistics()

            console.print("[bold]Local Graph Statistics[/bold]\n")

            console.print(f"[cyan]Total Entities:[/cyan] {stats['total_entities']}")
            console.print(f"[cyan]Total Relationships:[/cyan] {stats['total_relationships']}")
            console.print(f"[cyan]Average Degree:[/cyan] {stats['average_degree']:.2f}")
            console.print(f"[cyan]Isolated Entities:[/cyan] {stats['isolated_entities']}")

            if stats.get('entity_types'):
                console.print("\n[bold]Entity Types:[/bold]")
                for entity_type, count in stats['entity_types'].items():
                    console.print(f"  • {entity_type}: {count}")

            if stats.get('relationship_types'):
                console.print("\n[bold]Relationship Types:[/bold]")
                for rel_type, count in stats['relationship_types'].items():
                    console.print(f"  • {rel_type}: {count}")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await client.disconnect()

    asyncio.run(_stats())


@cli.command()
def demo():
    """Run demo showing MCP functionality."""
    async def _demo():
        client = await load_client()

        try:
            console.print("[bold cyan]Running MCP Demo...[/bold cyan]\n")
            await client.demo_mcp_functionality()

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            await client.disconnect()

    asyncio.run(_demo())


@cli.command()
def list_entities():
    """List all entities in local graph."""
    async def _list():
        client = await load_client()

        try:
            # Search for all entities
            result = await client.execute_mcp_tool(
                "search_entities",
                query="*",
                limit=100
            )

            if result.get('success') and 'result' in result:
                entities = result['result'].get('results', [])

                if not entities:
                    console.print("[yellow]No entities found.[/yellow]")
                    return

                # Group by type
                by_type = {}
                for item in entities:
                    if not isinstance(item, dict) or 'entity' not in item:
                        console.print(f"[yellow]Warning: Invalid item format: {item}[/yellow]")
                        continue

                    entity = item['entity']
                    if not isinstance(entity, dict):
                        console.print(f"[yellow]Warning: Invalid entity format: {entity}[/yellow]")
                        continue

                    entity_type = entity.get('entity_type', 'unknown')
                    if entity_type not in by_type:
                        by_type[entity_type] = []
                    by_type[entity_type].append(entity)

                # Display by type
                for entity_type, entities_list in sorted(by_type.items()):
                    console.print(f"\n[bold]{entity_type.upper()}S[/bold] ({len(entities_list)})")

                    table = Table(show_header=True, header_style="bold cyan")
                    table.add_column("Name", style="white")
                    table.add_column("ID", style="dim")
                    table.add_column("Updated", style="dim")

                    for entity in entities_list:
                        # Handle None or missing updated_at
                        updated_at = entity.get('updated_at')
                        if updated_at:
                            updated_str = str(updated_at)[:19]
                        else:
                            updated_str = 'Unknown'

                        table.add_row(
                            entity.get('name', 'Unnamed'),
                            (entity.get('id', '') or '')[:8] + "...",
                            updated_str
                        )

                    console.print(table)
            else:
                console.print(f"[red]Failed to retrieve entities: {result}[/red]")

        except Exception as e:
            import traceback
            console.print(f"[red]Error: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        finally:
            await client.disconnect()

    asyncio.run(_list())


if __name__ == "__main__":
    cli()
