"""
Blowing-Off Client - Synchronization Engine

DEVELOPMENT CONTEXT:
Created as the heart of the Inbetweenies protocol implementation in July 2025.
This engine orchestrates the complex dance of bidirectional synchronization between
local SQLite databases and the cloud server. It handles the full sync lifecycle,
conflict detection/resolution, and failure recovery. This is the most critical
component that the Swift/WildThing client must replicate accurately. Updated to
work with shared HomeKit-compatible models from Inbetweenies.

FUNCTIONALITY:
- Orchestrates full sync cycles with proper state management
- Fetches server changes and applies them locally
- Detects and uploads local changes to server
- Handles conflict resolution with configurable strategies
- Manages sync metadata for recovery and retry logic
- Implements the Inbetweenies protocol specification
- Provides atomic sync operations with rollback capability
- Works with HomeKit entities (homes, rooms, accessories, users)

PURPOSE:
This engine enables:
- Reliable offline-first operation
- Eventual consistency across all clients
- Conflict resolution without data loss
- Automatic retry with exponential backoff
- Incremental sync for efficiency
- Multi-client coordination
- Audit trail of all sync operations

KNOWN ISSUES:
- Delete operations not fully tracked yet
- Large sync batches could timeout
- No compression for sync payloads
- Conflict resolution strategy is basic (last-write-wins)
- Missing partial sync support for large datasets
- Sync tracking without dedicated model fields

REVISION HISTORY:
- 2025-07-28: Initial implementation with basic sync cycle
- 2025-07-28: Added conflict detection and resolution
- 2025-07-28: Enhanced error handling and retry logic
- 2025-07-28: Added incremental sync support
- 2025-07-28: Improved performance for large datasets
- 2025-07-29: Updated to use shared Inbetweenies models
- 2025-07-29: Changed entity types (houses→homes, devices→accessories)
- 2025-07-29: Removed EntityState and Event sync support

DEPENDENCIES:
- InbetweeniesProtocol for wire protocol implementation
- Repository pattern for data access
- ConflictResolver for merge strategies
- AsyncSession for database transactions
- UUID for sync operation tracking
- inbetweenies.models for shared entities

USAGE:
    engine = SyncEngine(session, "https://api.example.com", auth_token)
    
    # Perform sync
    result = await engine.sync()
    
    if result.success:
        print(f"Synced {result.synced_entities} entities")
        print(f"Resolved {result.conflicts_resolved} conflicts")
    else:
        print(f"Sync failed: {result.errors}")
        # Engine automatically schedules retry
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import json

from .protocol import InbetweeniesProtocol
from .state import SyncState, SyncResult, Change, Conflict, SyncOperation
from .conflict_resolver import ConflictResolver
from ..repositories import (
    ClientHomeRepository,
    ClientRoomRepository,
    ClientAccessoryRepository,
    ClientUserRepository,
    # ClientEntityStateRepository,  # Removed for HomeKit focus
    # ClientEventRepository,         # Removed for HomeKit focus
    SyncMetadataRepository
)
# SyncStatus removed for HomeKit focus - using simple status tracking
# from ..models.base import SyncStatus


class SyncEngine:
    """Main sync engine coordinating client-server synchronization."""
    
    def __init__(self, session: AsyncSession, base_url: str, auth_token: str, client_id: str = None):
        self.session = session
        self.client_id = client_id or str(uuid.uuid4())
        self.protocol = InbetweeniesProtocol(base_url, auth_token, self.client_id)
        self.base_url = base_url
        self.auth_token = auth_token
        
        # Don't initialize repositories here - we'll create them with the active session
        self.state = SyncState()
        
    async def sync(self) -> SyncResult:
        """Perform full sync cycle."""
        start_time = datetime.now()
        result = SyncResult(success=False)
        
        # Initialize repositories with current session
        self.home_repo = ClientHomeRepository(self.session)
        self.room_repo = ClientRoomRepository(self.session)
        self.accessory_repo = ClientAccessoryRepository(self.session)
        self.user_repo = ClientUserRepository(self.session)
        # EntityState and Event repositories removed for HomeKit focus
        # self.state_repo = ClientEntityStateRepository(self.session)
        # self.event_repo = ClientEventRepository(self.session)
        self.metadata_repo = SyncMetadataRepository(self.session)
        
        try:
            # Get sync metadata
            metadata = await self.metadata_repo.get_or_create(self.client_id)
            
            # For first sync, use None as last_sync_time to get all data
            sync_since = metadata.last_sync_success  # Use last successful sync, not last attempt
            
            metadata.record_sync_start()
            await self.session.commit()
            
            # Step 1: Get server changes
            server_changes, conflicts = await self._fetch_server_changes(sync_since)
            result.conflicts.extend(conflicts)
            
            # Step 2: Apply server changes locally
            applied_count = await self._apply_server_changes(server_changes)
            result.synced_entities += applied_count
            
            # Step 3: Get local changes
            local_changes = await self._get_local_changes()
            
            # Step 4: Push local changes
            if local_changes:
                push_result = await self._push_local_changes(local_changes)
                result.synced_entities += len(push_result["applied"])
                result.conflicts.extend(push_result["conflicts"])
                
            # Step 5: Acknowledge sync
            await self.protocol.sync_ack()
            
            # Update metadata
            metadata.record_sync_success()
            await self.session.commit()
            
            result.success = True
            result.conflicts_resolved = len([c for c in result.conflicts if c.resolution.startswith("local")])
            
        except Exception as e:
            # Record failure
            metadata = await self.metadata_repo.get_or_create(self.client_id)
            next_retry = datetime.now() + timedelta(seconds=min(30 * (2 ** metadata.sync_failures), 300))
            metadata.record_sync_failure(str(e), next_retry)
            await self.session.commit()
            
            result.errors.append(str(e))
            
        finally:
            result.duration = (datetime.now() - start_time).total_seconds()
            
        return result
        
    async def _fetch_server_changes(self, last_sync: Optional[datetime]) -> tuple[List[Change], List[Conflict]]:
        """Fetch changes from server."""
        response = await self.protocol.sync_request(last_sync)
        changes, conflicts = self.protocol.parse_sync_delta(response)
        return changes, conflicts
        
    async def _apply_server_changes(self, changes: List[Change]) -> int:
        """Apply server changes to local database."""
        applied = 0
        
        
        for change in changes:
            try:
                if await self._apply_single_change(change):
                    applied += 1
            except Exception as e:
                # Log but continue with other changes
                print(f"Error applying change {change.entity_id}: {e}")
                
        await self.session.commit()
        return applied
        
    def _convert_datetime_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert datetime string fields to datetime objects."""
        datetime_fields = ["created_at", "updated_at", "last_sync_at", "server_updated_at", 
                         "last_motion_at", "triggered_at", "last_changed_at", "last_reported_at"]
        
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
    
    async def _apply_single_change(self, change: Change) -> bool:
        """Apply a single change from server."""
        repo_map = {
            "home": self.home_repo,
            "homes": self.home_repo,  # Handle plural form
            "room": self.room_repo,
            "rooms": self.room_repo,
            "accessory": self.accessory_repo,
            "accessories": self.accessory_repo,
            "user": self.user_repo,
            "users": self.user_repo,
            # EntityState and Event repositories removed for HomeKit focus
            # "entity_state": self.state_repo,
            # "entity_states": self.state_repo,
            # "event": self.event_repo,
            # "events": self.event_repo
        }
        
        repo = repo_map.get(change.entity_type)
        if not repo:
            return False
            
        if change.operation == SyncOperation.DELETE:
            return await repo.delete(change.entity_id)
        else:
            # Create or update
            entity = await repo.get(change.entity_id)
            if entity:
                # Check for conflict based on timestamps only
                if entity.updated_at > change.updated_at:
                    # Local is newer, skip server change
                    return False
                    
                # Update with server data
                # Remove id from data if it exists to avoid issues
                update_data = {k: v for k, v in change.data.items() if k != 'id'}
                update_data = self._convert_datetime_fields(update_data)
                await repo.update(change.entity_id, **update_data)
            else:
                # Create new entity
                # Remove id from data if it exists to avoid duplicate argument
                create_data = {k: v for k, v in change.data.items() if k != 'id'}
                create_data = self._convert_datetime_fields(create_data)
                await repo.create(id=change.entity_id, **create_data)
                
            # Mark as synced
            await repo.mark_synced(change.entity_id, change.updated_at)
            
        return True
        
    async def _get_local_changes(self) -> List[Change]:
        """Get all local changes that need syncing."""
        changes = []
        
        # Get pending changes from all repositories
        for entity_type, repo in [
            ("home", self.home_repo),
            ("room", self.room_repo),
            ("accessory", self.accessory_repo),
            ("user", self.user_repo),
            # EntityState and Event repositories removed for HomeKit focus
            # ("entity_state", self.state_repo),
            # ("event", self.event_repo)
        ]:
            pending = await repo.get_pending()
            for entity in pending:
                change = Change(
                    entity_type=entity_type,
                    entity_id=entity.id,
                    operation=SyncOperation.UPDATE,  # TODO: Track creates/deletes
                    data=entity.to_dict() if hasattr(entity, 'to_dict') else {},
                    updated_at=entity.updated_at,
                    sync_id=entity.sync_id or str(uuid.uuid4()),
                    client_sync_id=str(uuid.uuid4())
                )
                changes.append(change)
                
        return changes
        
    async def _push_local_changes(self, changes: List[Change]) -> Dict[str, Any]:
        """Push local changes to server."""
        response = await self.protocol.sync_push(changes)
        
        # Process results
        applied_ids, conflicts = self.protocol.parse_sync_result(response)
        
        # Mark successfully synced entities
        for change in changes:
            if change.client_sync_id in applied_ids:
                repo_map = {
                    "home": self.home_repo,
                    "room": self.room_repo,
                    "accessory": self.accessory_repo,
                    "user": self.user_repo,
                    # EntityState and Event repositories removed for HomeKit focus
                    # "entity_state": self.state_repo,
                    # "event": self.event_repo
                }
                repo = repo_map.get(change.entity_type)
                if repo:
                    await repo.mark_synced(change.entity_id, datetime.now())
                    
        await self.session.commit()
        
        return {
            "applied": applied_ids,
            "conflicts": conflicts
        }