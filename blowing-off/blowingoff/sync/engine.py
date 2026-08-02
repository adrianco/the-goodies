"""
Blowing-Off Client - Sync Engine Implementation

DEVELOPMENT CONTEXT:
Updated to use the Entity model and graph operations for synchronization.
No longer uses HomeKit-specific models - everything is an Entity with
HomeKit-compatible data embedded in the content field.

FUNCTIONALITY:
- Orchestrates client-server synchronization
- Handles delta sync, full sync, and conflict resolution
- Manages offline queue and retry logic
- Tracks sync metadata and state
- Provides progress callbacks for UI updates
- Works with Entity model and graph operations

CRITICAL COMPONENTS:
- InbetweeniesProtocol for wire protocol
- GraphOperations for entity storage
- SyncMetadataRepository for tracking sync state

Conflict resolution is deliberately absent here: it is server-authoritative
(PROTOCOL.md §7). The server applies the single canonical rule and returns the
winner; this client pushes, reads the per-id acks, and applies what comes back.
The client-side resolver this file used to instantiate was never invoked and
has been removed.

PURPOSE:
Central coordination point for all sync operations. Manages the complexity
of bidirectional sync while providing a simple interface to the client.

REVISION HISTORY:
- 2025-07-30: Updated to use Entity model instead of HomeKit models
- 2025-07-28: Initial implementation with InbetweeniesProtocol v2
- 2025-07-28: Added conflict resolution and offline queue
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import json

from .protocol import InbetweeniesProtocol
from inbetweenies.sync import SyncState, SyncResult, Change, Conflict, SyncOperation
from ..repositories import SyncMetadataRepository
from inbetweenies.models import Entity, EntityType, SourceType


class SyncEngine:
    """Main sync engine coordinating client-server synchronization using Entity model."""

    def __init__(self, session: AsyncSession, base_url: str, auth_token: str, client_id: str = None):
        self.session = session
        self.base_url = base_url
        self.auth_token = auth_token
        self.client_id = client_id or str(uuid.uuid4())

        # Protocol and state
        self.protocol = InbetweeniesProtocol(base_url, auth_token, self.client_id)
        self.state = SyncState()

        # Graph operations will be set by the client
        self.graph_operations = None

        # Metadata tracking
        self.metadata_repo = SyncMetadataRepository(self.session)

        # Callbacks
        self.progress_callback = None
        self.conflict_callback = None

        # Sync control
        self._is_syncing = False
        self._sync_lock = asyncio.Lock()

    def set_graph_operations(self, graph_ops):
        """Set the graph operations instance for entity storage."""
        self.graph_operations = graph_ops

    async def sync(self) -> SyncResult:
        """Perform a sync operation."""
        async with self._sync_lock:
            if self._is_syncing:
                return SyncResult(
                    success=False,
                    errors=["Sync already in progress"]
                )

            self._is_syncing = True

        try:
            start_time = datetime.now()

            # Debug: Check if graph operations is set
            if not self.graph_operations:
                return SyncResult(
                    success=False,
                    errors=["Graph operations not set"],
                    timestamp=datetime.now()
                )

            # Get last sync time
            metadata = await self.metadata_repo.get_metadata(self.client_id)
            last_sync = metadata.last_sync_time if metadata else None

            # Get local changes (entities that need to be synced)
            local_changes = await self._get_local_changes(last_sync)

            # Request sync from server
            sync_response = await self.protocol.sync_request(
                last_sync=last_sync,
                entity_types=None  # Sync all entity types
            )

            # Process server changes
            server_changes, conflicts = self.protocol.parse_sync_delta(sync_response)

            # Apply server changes
            pulled_count = 0
            for change in server_changes:
                if await self._apply_single_change(change):
                    pulled_count += 1

            # Push local changes if any
            pushed_entities = 0
            pushed_relationships = 0
            if local_changes:
                push_result = await self._push_local_changes(local_changes)
                pushed_entities = len(push_result.get("applied", []))
                pushed_relationships = len(push_result.get("applied_relationships", []))

            synced_count = pulled_count + pushed_entities

            # Resolve conflicts
            resolved_count = 0
            for conflict in conflicts:
                if await self._resolve_conflict(conflict):
                    resolved_count += 1

            # Persist the SERVER's clock as our delta watermark (PROTOCOL.md §4),
            # never the client's local time. We send this back as `since` next sync.
            watermark = self._parse_server_time(sync_response.get("server_time"))
            await self.metadata_repo.update_sync_time(watermark, self.client_id)

            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()

            return SyncResult(
                success=True,
                synced_entities=synced_count,
                pulled_entities=pulled_count,
                pushed_entities=pushed_entities,
                pushed_relationships=pushed_relationships,
                pending_after_sync=self.graph_operations.pending_count(),
                conflicts_resolved=resolved_count,
                conflicts=[],  # All resolved
                errors=[],
                duration=duration,
                timestamp=datetime.now()
            )

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"SYNC ERROR: {type(e).__name__}: {str(e)}")
            print(f"TRACEBACK: {error_detail}")
            return SyncResult(
                success=False,
                errors=[f"{type(e).__name__}: {str(e)}", error_detail],
                timestamp=datetime.now()
            )
        finally:
            self._is_syncing = False

    async def _get_local_changes(self, since: Optional[datetime]) -> List[Change]:
        """Build the push payload from the storage-backed pending set.

        Pending marks are deliberately NOT cleared here — that only happens
        once the server confirms it applied a change (see _push_local_changes).
        Clearing early loses the write whenever a push fails.
        """
        if not self.graph_operations:
            return []

        pending_entities = self.graph_operations.get_pending_entities()
        pending_relationships = self.graph_operations.get_pending_relationships()

        # Group pending relationships onto the entity change they originate
        # from, which is how the wire protocol carries them.
        relationships_by_entity: Dict[str, List[Dict[str, Any]]] = {}
        orphan_relationships: List[Dict[str, Any]] = []
        for relationship_id in pending_relationships:
            relationship = await self._get_relationship(relationship_id)
            if not relationship:
                continue
            serialized = relationship.to_dict()
            if relationship.from_entity_id in pending_entities:
                relationships_by_entity.setdefault(
                    relationship.from_entity_id, []
                ).append(serialized)
            else:
                orphan_relationships.append(serialized)

        changes = []
        for entity_id, operation in pending_entities.items():
            entity = await self.graph_operations.get_entity(entity_id)
            if not entity:
                continue
            entity_type_value = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
            changes.append(Change(
                entity_type=entity_type_value,
                entity_id=entity.id,
                operation=SyncOperation(operation),
                data=entity.to_dict(),
                updated_at=getattr(entity, 'updated_at', datetime.now()),
                sync_id=entity.version,
                client_sync_id=str(uuid.uuid4()),
                relationships=relationships_by_entity.get(entity.id, [])
            ))

        # A relationship whose endpoint entity is already in sync still has to
        # be pushed, so it rides on its own entity-less change.
        for serialized in orphan_relationships:
            changes.append(Change(
                entity_type="",
                entity_id="",
                operation=SyncOperation.UPDATE,
                data={},
                updated_at=datetime.now(),
                sync_id="",
                client_sync_id=str(uuid.uuid4()),
                relationships=[serialized]
            ))

        return changes

    async def _get_relationship(self, relationship_id: str):
        """Look up a single relationship by id from the local graph."""
        for relationship in await self.graph_operations.get_relationships():
            if relationship.id == relationship_id:
                return relationship
        return None

    def mark_entity_for_sync(self, entity_id: str):
        """Explicitly queue an entity for the next push.

        Local writes mark themselves dirty, so this is rarely needed. It
        remains for callers that mutate storage out-of-band and for tests.
        """
        if not self.graph_operations:
            return
        self.graph_operations.storage.mark_entity_pending(entity_id)

    @staticmethod
    def _parse_server_time(server_time: Optional[str]) -> datetime:
        """Parse the response's server_time into a UTC-aware datetime.

        Falls back to 'now' (UTC) only if the server omitted it (older server)."""
        if server_time:
            try:
                parsed = datetime.fromisoformat(server_time.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    async def _apply_single_change(self, change: Change) -> bool:
        """Apply a single change from the server.

        Creates, updates and deletes are all stored as entity versions — a delete
        is a tombstone version (content.deleted=true), so applying it is the same
        store operation as any other version (PROTOCOL.md §8). The local graph's
        active views filter out tombstoned entities.
        """
        if not self.graph_operations:
            return False

        try:
            entity_data = change.data
            entity = Entity(
                id=entity_data.get('id'),
                version=entity_data.get('version', ''),
                entity_type=EntityType(entity_data.get('entity_type', 'unknown')),
                name=entity_data.get('name', ''),
                content=entity_data.get('content', {}),
                source_type=SourceType(entity_data.get('source_type', SourceType.IMPORTED)),
                parent_versions=entity_data.get('parent_versions', []),
                user_id=entity_data.get('user_id', 'sync')
            )
            # mark_dirty=False: this version came FROM the server, so queuing it
            # for push would bounce the server's own change straight back.
            await self.graph_operations.store_entity(entity, mark_dirty=False)
            return True

        except Exception as e:
            print(f"Error applying change: {e}")
            return False

    async def _push_local_changes(self, changes: List[Change]) -> Dict[str, Any]:
        """Push local changes to server."""
        if not changes:
            return {"applied": []}

        # Convert changes to sync format and push
        response = await self.protocol.sync_push(changes)

        # Clear pending marks only for what the server acknowledged by id.
        # Anything it rejected — or that was written while this push was in
        # flight — keeps its mark and goes out on the next sync.
        applied_ids = response.get("applied", [])
        applied_relationship_ids = response.get("applied_relationships", [])
        if applied_ids or applied_relationship_ids:
            self.graph_operations.clear_pending(
                entity_ids=applied_ids,
                relationship_ids=applied_relationship_ids
            )

        return response

    async def _resolve_conflict(self, conflict: Conflict) -> bool:
        """Acknowledge a conflict the server already resolved.

        Conflict resolution is server-authoritative: the server runs the single
        canonical algorithm (inbetweenies.sync.ConflictResolver — LWW + version
        tiebreak, PROTOCOL.md §7) and sends the winning version in `changes`, which
        we have already applied. The `conflicts` list is informational, so there is
        nothing to resolve locally; we just count it as handled.
        """
        return True

    def _convert_datetime_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert datetime string fields to datetime objects."""
        datetime_fields = ['created_at', 'updated_at', 'deleted_at', 'last_sync']

        result = data.copy()
        for field in datetime_fields:
            if field in result and isinstance(result[field], str):
                try:
                    # Handle ISO format with or without timezone
                    result[field] = datetime.fromisoformat(result[field].replace("Z", "+00:00"))
                except:
                    # If parsing fails, remove the field
                    del result[field]

        return result
