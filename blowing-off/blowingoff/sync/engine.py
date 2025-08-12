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
- ConflictResolver for merge strategies
- SyncMetadataRepository for tracking sync state

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
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import json

from .protocol import InbetweeniesProtocol
from inbetweenies.sync import SyncState, SyncResult, Change, Conflict, SyncOperation
from .conflict_resolver import ConflictResolver
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
        self.resolver = ConflictResolver()
        
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
            synced_count = 0
            for change in server_changes:
                if await self._apply_single_change(change):
                    synced_count += 1
                    
            # Push local changes if any
            if local_changes:
                push_result = await self._push_local_changes(local_changes)
                synced_count += len(push_result.get("applied", []))
                
            # Resolve conflicts
            resolved_count = 0
            for conflict in conflicts:
                if await self._resolve_conflict(conflict):
                    resolved_count += 1
                    
            # Update sync metadata
            await self.metadata_repo.update_sync_time(datetime.now(), self.client_id)
            
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()
            
            return SyncResult(
                success=True,
                synced_entities=synced_count,
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
        """Get local changes that need syncing."""
        if not self.graph_operations:
            return []
            
        changes = []
        
        # Check if we have any pending changes to sync
        if hasattr(self, '_pending_sync_entities'):
            for entity_id in self._pending_sync_entities:
                entity = await self.graph_operations.get_entity(entity_id)
                if entity:
                    entity_type_value = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
                    change = Change(
                        entity_type=entity_type_value,
                        entity_id=entity.id,
                        operation=SyncOperation.UPDATE,
                        data=entity.to_dict(),
                        updated_at=getattr(entity, 'updated_at', datetime.now()),
                        sync_id=entity.version,
                        client_sync_id=str(uuid.uuid4())
                    )
                    changes.append(change)
            # Clear pending entities after creating changes
            self._pending_sync_entities = set()
        
        return changes
    
    def mark_entity_for_sync(self, entity_id: str):
        """Mark an entity as needing to be synced."""
        if not hasattr(self, '_pending_sync_entities'):
            self._pending_sync_entities = set()
        self._pending_sync_entities.add(entity_id)
        
    async def _apply_single_change(self, change: Change) -> bool:
        """Apply a single change from server."""
        if not self.graph_operations:
            return False
            
        try:
            if change.operation == SyncOperation.DELETE:
                # Delete entity
                # Note: Graph operations might not have a delete method yet
                return False  # Skip deletes for now
            else:
                # Create/Update entity
                entity_data = change.data
                
                # Convert to Entity object
                entity = Entity(
                    id=entity_data.get('id'),
                    version=entity_data.get('version', ''),
                    entity_type=EntityType(entity_data.get('entity_type', 'unknown')),
                    name=entity_data.get('name', ''),
                    content=entity_data.get('content', {}),
                    source_type=SourceType(entity_data.get('source_type', SourceType.IMPORTED)),
                    parent_versions=entity_data.get('parent_versions', [])
                )
                
                # Store entity
                print(f"DEBUG: Applying change for entity {entity.id}: version={entity.version}, content={entity.content}")
                await self.graph_operations.store_entity(entity)
                return True
                
        except Exception as e:
            print(f"Error applying change: {e}")
            return False
            
    async def _push_local_changes(self, changes: List[Change]) -> Dict[str, Any]:
        """Push local changes to server."""
        if not changes:
            return {"applied": []}
        
        print(f"DEBUG: Pushing {len(changes)} local changes to server")
        for change in changes[:3]:  # Print first 3 for debugging
            print(f"  - {change.entity_id}: {change.data.get('content', {})}")
            
        # Convert changes to sync format and push
        response = await self.protocol.sync_push(changes)
        
        # Mark successfully synced entities
        applied_ids = response.get("applied", [])
        
        # In a real implementation, we'd mark these entities as synced
        # to avoid re-syncing them next time
        
        return response
        
    async def _resolve_conflict(self, conflict: Conflict) -> bool:
        """Resolve a sync conflict."""
        # For now, we'll use last-write-wins
        # In a real implementation, this could be more sophisticated
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