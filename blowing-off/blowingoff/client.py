"""
Blowing-Off Client - Smart Home Synchronization Client

STATUS: ✅ Production Ready - All tests passing, sync operational

ARCHITECTURE:
Python client for The Goodies smart home system providing real-time
synchronization with FunkyGibbon server, local MCP tool execution,
and offline-capable graph operations.

CORE FUNCTIONALITY:
- Real-time sync with server (33 entities synchronized)
- Local SQLite database for offline operation
- All 12 MCP tools available locally
- Entity-relationship graph operations
- Conflict resolution with multiple strategies
- CLI interface matching server functionality

KEY FEATURES:
- Bidirectional synchronization with server
- Local graph operations for offline use
- MCP tool execution without server dependency
- Connection management with retry logic
- Progress tracking and status reporting

SYNC CAPABILITIES:
- Full sync on initial connection
- Delta sync for ongoing updates
- Conflict detection and resolution
- Offline queue for disconnected operation
- Vector clocks for distributed state

TESTING STATUS:
- 13/13 unit and integration tests passing
- Sync functionality fully operational
- CLI commands working correctly
- Human testing scenarios verified

PRODUCTION READY:
Client successfully connects, syncs, and operates with full functionality.
All MCP tools working locally with server data."""

import os
import asyncio
import gc
import logging
import shutil
import uuid
from typing import Dict, Any, List, Optional, Callable, Union
from datetime import datetime, UTC
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event, text
import json
import httpx

from .models import Base
from .sync.engine import SyncEngine
from inbetweenies.sync import SyncResult
from .mcp import LocalMCPClient
from .graph import LocalGraphStorage, LocalGraphOperations
from .repositories import SyncMetadataRepository
from .auth import AuthManager


logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Graph-store location
#
# The client's graph store used to be derived from the database file's PARENT
# directory (`<parent>/.blowing-off-graph`). That is not a function of the
# client: two clients whose databases merely sit in the same directory got the
# same store, and so shared one entity set, one index and — worst — one set of
# pending (unpushed) marks, letting one client's push clear another's pending
# flag. It also made the test suite non-reentrant, because every client built
# on a NamedTemporaryFile landed in $TMPDIR/.blowing-off-graph.
#
# The store is now derived from the database file's IDENTITY: the full file
# NAME plus a suffix, as a sibling of the database.
#
#     /var/lib/home/client.db  ->  /var/lib/home/client.db.graph/
#
# The full name is used rather than the stem (`<dir>/.blowing-off-graph-client`)
# precisely because the stem is not unique: `client.db` and `client.sqlite`
# share the stem `client` and would collide again. Appending to the whole name
# is injective over a directory, so two distinct database files in one
# directory always get two distinct stores. Keeping the store adjacent to the
# database also means the pair is obvious to a human and travels together when
# a deployment is copied or backed up.
# ----------------------------------------------------------------------

GRAPH_DIR_SUFFIX = ".graph"

#: The pre-fix, shared-per-directory store. Read for migration only.
LEGACY_GRAPH_DIR_NAME = ".blowing-off-graph"

#: Dropped into a legacy store once some database has adopted its contents, so
#: a second database cannot later adopt the same data a second time.
LEGACY_CLAIM_MARKER = "adopted-by.json"

_STORE_FILES = ("entities.json", "relationships.json", "index.json", "pending.json")
_DATABASE_SUFFIXES = (".db", ".sqlite", ".sqlite3")


def graph_storage_path(db_path: Union[str, Path]) -> Path:
    """Return the graph-store directory belonging to `db_path`.

    Collision-free by construction: the directory name contains the database
    file's whole name, so distinct databases in one directory never share one.
    """
    db_file = Path(db_path).expanduser()
    return db_file.parent / (db_file.name + GRAPH_DIR_SUFFIX)


def _sibling_databases(directory: Path, db_name: str) -> set:
    """Names of database files in `directory`, including `db_name` itself.

    The client is often constructed before its database file exists, so the
    client's own name is always counted whether or not it is on disk yet.
    """
    names = {db_name}
    try:
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in _DATABASE_SUFFIXES:
                names.add(path.name)
    except OSError:
        pass
    return names


def migrate_legacy_graph_store(
    db_path: Union[str, Path],
    store_dir: Optional[Union[str, Path]] = None,
) -> str:
    """Adopt a pre-fix shared store into this database's own store, if safe.

    Returns a short status string naming what was decided; the client keeps it
    on `.graph_store_migration` so operators (and tests) can see it.

    The decision has to thread between two unacceptable outcomes. Requiring
    manual action would silently strand an existing install: it would come up
    against an empty graph, and — the sharp edge — any change written while
    offline but never pushed would sit unreachable in the old directory. But
    adopting unconditionally is worse, because the old directory is shared, so
    its contents may belong to a *different* database entirely; adopting would
    silently import a stranger's entities and, through their pending marks,
    push them to the server under this client's identity.

    So adoption happens automatically only where ownership is not in question:
    when this database is the only database in the directory, the shared store
    can only ever have been written by it. Where more than one database shares
    the directory, ownership is genuinely unknowable from what is on disk, and
    the migration declines, warns, and leaves the old directory untouched — no
    data is destroyed, and a human can move the right store into place.

    Adoption copies rather than moves, and stamps the legacy directory with a
    marker, so the original remains available and a second database cannot
    adopt the same data later.
    """
    db_file = Path(db_path).expanduser()
    target = Path(store_dir) if store_dir is not None else graph_storage_path(db_file)
    legacy_dir = db_file.parent / LEGACY_GRAPH_DIR_NAME

    if not legacy_dir.is_dir():
        return "no-legacy-store"

    if target.exists():
        # This database already has a store of its own; it is authoritative.
        # (The directory outliving a clear_graph_data() is deliberate — an
        # explicit clear must not be undone by resurrecting legacy data.)
        return "own-store-exists"

    payload = [legacy_dir / name for name in _STORE_FILES]
    payload = [path for path in payload if path.is_file()]
    if not payload:
        return "legacy-store-empty"

    marker = legacy_dir / LEGACY_CLAIM_MARKER
    if marker.is_file():
        owner = "another database"
        try:
            owner = json.loads(marker.read_text()).get("adopted_by") or owner
        except (OSError, ValueError):
            pass
        logger.warning(
            "Legacy graph store %s was already adopted by %s; not adopting it "
            "again for %s, which starts with an empty graph. Copy the store "
            "into %s by hand if it really belongs to this database.",
            legacy_dir, owner, db_file.name, target,
        )
        return "declined-already-claimed"

    siblings = _sibling_databases(db_file.parent, db_file.name)
    if len(siblings) > 1:
        logger.warning(
            "Legacy graph store %s is shared by %d databases (%s), so it "
            "cannot be attributed to %s. Leaving it untouched and starting "
            "with an empty graph rather than importing data that may belong "
            "to another client. If it is this client's, copy its *.json into "
            "%s.",
            legacy_dir, len(siblings), ", ".join(sorted(siblings)),
            db_file.name, target,
        )
        return "declined-ambiguous"

    target.mkdir(parents=True, exist_ok=True)
    for path in payload:
        shutil.copy2(path, target / path.name)

    try:
        marker.write_text(json.dumps({
            "adopted_by": db_file.name,
            "adopted_into": str(target),
            "adopted_at": datetime.now(UTC).isoformat(),
        }, indent=2))
    except OSError as exc:  # read-only legacy dir: the copy still stands
        logger.warning("Could not mark %s as adopted: %s", legacy_dir, exc)

    logger.info(
        "Adopted legacy graph store %s into %s (the original is left in "
        "place; it is the only database in that directory).",
        legacy_dir, target,
    )
    return "adopted"


class BlowingOffClient:
    """Python test client for The Goodies smart home system."""

    def __init__(self, db_path: str = "blowingoff.db"):
        """Initialize client with local SQLite database."""
        self.db_path = db_path
        self.engine = None
        self.session_factory = None
        self.sync_engine = None
        self._observers = []
        self._background_task = None
        self.auth_manager = None
        self._is_offline = False  # Track offline status
        self._offline_changes_count = 0  # Track pending changes

        # Initialize MCP and graph functionality.
        # The store belongs to THIS database file, not to its directory — see
        # graph_storage_path() for why the directory was the wrong key.
        self.graph_storage_dir = graph_storage_path(db_path)
        self.graph_store_migration = migrate_legacy_graph_store(
            db_path, self.graph_storage_dir
        )
        self.graph_storage = LocalGraphStorage(str(self.graph_storage_dir))
        self.graph_operations = LocalGraphOperations(self.graph_storage)
        self.mcp_client = LocalMCPClient(self.graph_storage)

    async def connect(
        self,
        server_url: str,
        auth_token: str = None,
        client_id: str = None,
        password: str = None,
        qr_data: str = None
    ):
        """Connect to server and initialize local database.

        Args:
            server_url: Base URL of the FunkyGibbon server
            auth_token: Optional JWT token (if already authenticated)
            client_id: Optional client identifier
            password: Admin password for authentication
            qr_data: QR code data for guest authentication
        """
        # Initialize auth manager
        self.auth_manager = AuthManager(server_url)

        # Handle authentication
        if auth_token:
            # Use provided token
            self.auth_manager.token = auth_token
        elif password:
            # Authenticate with admin password
            success = await self.auth_manager.login_admin(password)
            if not success:
                raise RuntimeError("Admin authentication failed")
        elif qr_data:
            # Authenticate with QR code
            success = await self.auth_manager.login_guest(qr_data)
            if not success:
                raise RuntimeError("Guest authentication failed")
        elif not self.auth_manager.is_authenticated():
            raise RuntimeError("No authentication method provided")
        # Initialize database
        db_url = f"sqlite+aiosqlite:///{self.db_path}"
        self.engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
            pool_pre_ping=True,  # Verify connections before use
            poolclass=None  # Disable pooling for SQLite
        )

        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            # Enable SQLite optimizations for better concurrency
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))
            await conn.execute(text("PRAGMA cache_size=10000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))

        # Create session factory
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        # Initialize sync engine with authentication
        async with self.session_factory() as session:
            # Use auth token from auth manager
            auth_token = self.auth_manager.token if self.auth_manager else auth_token
            self.sync_engine = SyncEngine(session, server_url, auth_token, client_id)
            self.sync_engine.set_graph_operations(self.graph_operations)

            # Set auth headers for sync engine
            if self.auth_manager:
                self.sync_engine.auth_headers = self.auth_manager.get_headers()

    async def disconnect(self):
        """Disconnect and cleanup resources."""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

        if self.engine:
            await self.engine.dispose()
            gc.collect()

    async def check_server_connectivity(self) -> bool:
        """Check if server is reachable and responding."""
        if not self.sync_engine or not self.sync_engine.base_url:
            return False

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.sync_engine.base_url}/health")
                return response.status_code == 200
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            return False

    async def sync(self) -> SyncResult:
        """Perform manual sync with server.

        Returns a SyncResult indicating success or failure.
        Works in disconnected mode if server is not reachable.
        """
        if not self.sync_engine:
            raise RuntimeError("Client not connected")

        # Check server connectivity first
        server_available = await self.check_server_connectivity()

        if not server_available:
            # Server is not available - return disconnected result
            self._is_offline = True

            # Count pending changes
            self._offline_changes_count = (
                self.graph_operations.pending_count() if self.graph_operations else 0
            )

            result = SyncResult(
                success=False,
                synced_entities=0,
                conflicts=[],
                errors=[f"Server not reachable - operating in disconnected mode ({self._offline_changes_count} pending changes)"]
            )

            # Notify observers
            await self._notify_observers("sync_disconnected", result)

            return result

        # Server is available - we're online
        self._is_offline = False

        async with self.session_factory() as session:
            try:
                self.sync_engine.session = session
                result = await self.sync_engine.sync()
                await session.commit()
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                # Network error - switch to disconnected mode
                await session.rollback()
                result = SyncResult(
                    success=False,
                    synced_entities=0,
                    conflicts=[],
                    errors=[f"Network error: {str(e)} - operating in disconnected mode"]
                )
                await self._notify_observers("sync_disconnected", result)
                return result
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

        # Notify observers
        await self._notify_observers("sync_complete", result)

        return result

    async def start_background_sync(self, interval: int = 30):
        """Start background sync task.

        Automatically handles disconnected mode and retries when server becomes available.
        """
        async def sync_loop():
            consecutive_failures = 0
            while True:
                try:
                    await asyncio.sleep(interval)
                    result = await self.sync()

                    if result.success:
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        # Back off if multiple failures
                        if consecutive_failures >= 3:
                            print(f"Multiple sync failures, backing off...")
                            await asyncio.sleep(interval * 2)  # Double the interval on failures

                except asyncio.CancelledError:
                    break
                except (ConnectionError, TimeoutError, ValueError) as e:
                    print(f"Background sync error: {e}")
                    consecutive_failures += 1

        self._background_task = asyncio.create_task(sync_loop())

    def add_observer(self, callback: Callable):
        """Add observer for sync events."""
        self._observers.append(callback)

    def remove_observer(self, callback: Callable):
        """Remove observer."""
        if callback in self._observers:
            self._observers.remove(callback)

    async def _notify_observers(self, event: str, data: Any):
        """Notify all observers of an event."""
        for observer in self._observers:
            try:
                if asyncio.iscoroutinefunction(observer):
                    await observer(event, data)
                else:
                    observer(event, data)
            except (TypeError, ValueError) as e:
                print(f"Observer error: {e}")

    # MCP and Graph Operations

    async def execute_mcp_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute an MCP tool by name."""
        return await self.mcp_client.execute_tool(tool_name, **kwargs)

    def get_available_mcp_tools(self) -> List[str]:
        """Get list of available MCP tools."""
        return self.mcp_client.get_available_tools()

    def clear_graph_data(self):
        """Clear this client's graph data, including its pending marks.

        Scoped to this client's own store (`<db_path>.graph`). It used to reach
        into the store shared by every database in the directory, so one
        client's clear wiped the others' entities and dropped their unpushed
        changes.

        The store directory itself is kept, empty: its existence is what tells
        a later start that this database has a store of its own, so a deliberate
        clear is not undone by adopting a legacy store on the next run.
        """
        if hasattr(self, 'graph_storage'):
            self.graph_storage.clear()

    @property
    def is_offline(self) -> bool:
        """Check if client is currently in offline mode."""
        return self._is_offline

    @property
    def pending_changes_count(self) -> int:
        """Get count of local changes waiting to be pushed to the server.

        Read live from local storage rather than from the last sync attempt, so
        it stays accurate for writes made since — including across a restart.
        """
        if self.graph_operations:
            return self.graph_operations.pending_count()
        return self._offline_changes_count

    def check_write_permission(self) -> bool:
        """Check if client has write permission."""
        if not self.auth_manager:
            return False
        return self.auth_manager.has_permission('write')

    def check_admin_permission(self) -> bool:
        """Check if client has admin permission."""
        if not self.auth_manager:
            return False
        return self.auth_manager.role == 'admin'

    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and statistics."""
        async with self.session_factory() as session:
            try:
                repo = SyncMetadataRepository(session)
                metadata = await repo.get_metadata(
                    self.sync_engine.client_id if self.sync_engine else "default"
                )

                if not metadata:
                    # Return default values if no metadata exists yet
                    return {
                        "last_sync": None,
                        "last_success": None,
                        "total_syncs": 0,
                        "sync_failures": 0,
                        "total_conflicts": 0,
                        "sync_in_progress": False,
                        "last_error": None
                    }

                return {
                    "last_sync": metadata.last_sync_time.isoformat() if metadata.last_sync_time else None,
                    "last_success": metadata.last_sync_success.isoformat() if metadata.last_sync_success else None,
                    "total_syncs": metadata.total_syncs or 0,
                    "sync_failures": metadata.sync_failures or 0,
                    "total_conflicts": metadata.total_conflicts or 0,
                    "sync_in_progress": bool(metadata.sync_in_progress),
                    "last_error": metadata.last_sync_error
                }
            finally:
                await session.close()

    async def demo_mcp_functionality(self):
        """Demonstrate MCP functionality with sample data."""
        from inbetweenies.models import Entity, EntityType, SourceType, EntityRelationship, RelationshipType

        # Create sample entities
        print("\n📝 Creating sample entities...")

        # Create a home
        home = Entity(
            entity_type=EntityType.HOME,
            name="Demo Smart Home",
            content={
                "address": "456 Demo Street",
                "city": "Demo City"
            },
            source_type=SourceType.MANUAL
        )
        stored_home = await self.graph_operations.store_entity(home)

        # Create rooms
        living_room = Entity(
            entity_type=EntityType.ROOM,
            name="Living Room",
            content={"floor": "1st"},
            source_type=SourceType.MANUAL
        )
        kitchen = Entity(
            entity_type=EntityType.ROOM,
            name="Kitchen",
            content={"floor": "1st"},
            source_type=SourceType.MANUAL
        )

        stored_living = await self.graph_operations.store_entity(living_room)
        stored_kitchen = await self.graph_operations.store_entity(kitchen)

        # Create devices
        tv = Entity(
            entity_type=EntityType.DEVICE,
            name="Smart TV",
            content={
                "manufacturer": "Samsung",
                "model": "Q90",
                "capabilities": ["power", "volume", "input"]
            },
            source_type=SourceType.MANUAL
        )
        fridge = Entity(
            entity_type=EntityType.DEVICE,
            name="Smart Fridge",
            content={
                "manufacturer": "LG",
                "model": "InstaView",
                "capabilities": ["temperature", "door_status"]
            },
            source_type=SourceType.MANUAL
        )

        stored_tv = await self.graph_operations.store_entity(tv)
        stored_fridge = await self.graph_operations.store_entity(fridge)

        # Create relationships
        # Rooms in home
        await self.graph_operations.store_relationship(
            EntityRelationship(
                id=str(uuid.uuid4()),
                from_entity_id=stored_living.id,
                from_entity_version=stored_living.version,
                to_entity_id=stored_home.id,
                to_entity_version=stored_home.version,
                relationship_type=RelationshipType.LOCATED_IN,
                properties={},
                created_at=datetime.now(UTC),
                user_id="demo"
            )
        )
        await self.graph_operations.store_relationship(
            EntityRelationship(
                id=str(uuid.uuid4()),
                from_entity_id=stored_kitchen.id,
                from_entity_version=stored_kitchen.version,
                to_entity_id=stored_home.id,
                to_entity_version=stored_home.version,
                relationship_type=RelationshipType.LOCATED_IN,
                properties={},
                created_at=datetime.now(UTC),
                user_id="demo"
            )
        )

        # Devices in rooms
        await self.graph_operations.store_relationship(
            EntityRelationship(
                id=str(uuid.uuid4()),
                from_entity_id=stored_tv.id,
                from_entity_version=stored_tv.version,
                to_entity_id=stored_living.id,
                to_entity_version=stored_living.version,
                relationship_type=RelationshipType.LOCATED_IN,
                properties={},
                created_at=datetime.now(UTC),
                user_id="demo"
            )
        )
        await self.graph_operations.store_relationship(
            EntityRelationship(
                id=str(uuid.uuid4()),
                from_entity_id=stored_fridge.id,
                from_entity_version=stored_fridge.version,
                to_entity_id=stored_kitchen.id,
                to_entity_version=stored_kitchen.version,
                relationship_type=RelationshipType.LOCATED_IN,
                properties={},
                created_at=datetime.now(UTC),
                user_id="demo"
            )
        )

        print("✅ Created demo entities and relationships")

        # Test MCP tools
        print("\n🔍 Testing MCP tools...")

        # Get devices in living room
        result = await self.execute_mcp_tool(
            "get_devices_in_room",
            room_id=stored_living.id
        )
        if result and result.get('success') and result.get('result'):
            count = result['result'].get('count', 0)
            print(f"\nDevices in Living Room: {count}")
        else:
            print("\nDevices in Living Room: 0")

        # Search for devices
        result = await self.execute_mcp_tool(
            "search_entities",
            query="Smart",
            entity_types=[EntityType.DEVICE.value],
            limit=10
        )
        if result and result.get('success') and result.get('result'):
            count = result['result'].get('count', 0)
            print(f"Found {count} smart devices")
        else:
            print("Found 0 smart devices")

        print("\n✅ MCP demo complete!")
