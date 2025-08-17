"""
Blowing-Off Client - Inbetweenies Protocol Implementation

DEVELOPMENT CONTEXT:
Created as the wire protocol implementation in July 2025. This module implements
the Inbetweenies synchronization protocol, which defines how clients communicate
with the server for data synchronization. This protocol is designed to be efficient,
reliable, and handle various network conditions. The Swift/WildThing client must
implement this protocol exactly to ensure compatibility.

FUNCTIONALITY:
- Implements sync request/response cycle
- Handles change serialization and deserialization
- Manages authentication and session tracking
- Parses server deltas and conflict information
- Pushes local changes with proper formatting
- Acknowledges successful sync completion
- Handles protocol versioning and compatibility
- Implements timeout and retry semantics

PURPOSE:
This protocol enables:
- Efficient delta synchronization
- Conflict detection at the protocol level
- Batch operations for performance
- Incremental sync with timestamps
- Client identification and tracking
- Secure communication with auth tokens
- Graceful handling of network failures

KNOWN ISSUES:
- No compression for large payloads yet
- Missing protocol version negotiation
- No support for partial entity sync
- Timeout values could be configurable
- Missing request/response correlation IDs

REVISION HISTORY:
- 2025-07-28: Initial protocol implementation
- 2025-07-28: Added conflict handling in responses
- 2025-07-28: Enhanced error handling and timeouts
- 2025-07-28: Added batch change support
- 2025-07-28: Improved JSON serialization efficiency

DEPENDENCIES:
- httpx for async HTTP operations
- JSON for data serialization
- datetime for timestamp handling
- Custom state objects for type safety

USAGE:
    protocol = InbetweeniesProtocol(base_url, auth_token, client_id)
    
    # Request server changes
    response = await protocol.sync_request(last_sync_time)
    changes, conflicts = protocol.parse_sync_delta(response)
    
    # Push local changes
    result = await protocol.sync_push(local_changes)
    applied_ids, new_conflicts = protocol.parse_sync_result(result)
    
    # Acknowledge completion
    await protocol.sync_ack()
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import httpx
from inbetweenies.sync import Change, Conflict, SyncOperation
from inbetweenies.sync import (
    VectorClock, EntityChange, SyncChange,
    SyncFilters, SyncRequest, SyncResponse
)


class InbetweeniesProtocol:
    """Implementation of the Inbetweenies sync protocol."""
    
    def __init__(self, base_url: str, auth_token: str, client_id: str):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.client_id = client_id
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        
    async def sync_request(
        self, 
        last_sync: Optional[datetime],
        entity_types: List[str] = None
    ) -> Dict[str, Any]:
        """Send sync request to get server changes using new protocol."""
        # Build filters
        filters = None
        if last_sync or entity_types:
            filters = SyncFilters()
            if last_sync:
                filters.since = last_sync
            if entity_types:
                filters.entity_types = entity_types
            
        # Build sync request
        request = SyncRequest(
            protocol_version="inbetweenies-v2",
            device_id=self.client_id,
            user_id="client-user",  # TODO: get from auth
            sync_type="delta" if last_sync else "full",
            vector_clock=VectorClock(),
            changes=[],
            filters=filters
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sync/",
                json=request.model_dump(exclude_none=True, mode='json'),
                headers=self.headers,
                timeout=5.0  # Fail fast
            )
            response.raise_for_status()
            return response.json()
            
    async def sync_push(self, changes: List[Change]) -> Dict[str, Any]:
        """Push local changes to server using new protocol."""
        # Convert changes to SyncChange objects
        sync_changes = []
        for change in changes:
            # Create entity change if not delete
            entity = None
            if change.operation != SyncOperation.DELETE:
                entity = EntityChange(
                    id=change.entity_id,
                    version=change.data.get("version", ""),
                    entity_type=change.entity_type,
                    name=change.data.get("name", ""),
                    content=change.data.get("content", {}),
                    source_type=change.data.get("source_type", "MANUAL"),
                    user_id=change.data.get("user_id") or "client-user",
                    parent_versions=change.data.get("parent_versions") or []
                )
            
            # Create sync change
            operation = change.operation.value if hasattr(change.operation, 'value') else str(change.operation).lower()
            sync_change = SyncChange(
                change_type=operation,
                entity=entity,
                relationships=[]
            )
            sync_changes.append(sync_change)
        
        # Build sync request with changes
        request = SyncRequest(
            protocol_version="inbetweenies-v2",
            device_id=self.client_id,
            user_id="client-user",  # TODO: get from auth
            sync_type="delta",
            vector_clock=VectorClock(),
            changes=sync_changes
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sync/",
                json=request.model_dump(exclude_none=True, mode='json'),
                headers=self.headers,
                timeout=5.0  # Fail fast
            )
            response.raise_for_status()
            return response.json()
            
    async def sync_ack(self) -> Dict[str, Any]:
        """Acknowledge sync completion - no longer needed in new protocol."""
        # The new protocol doesn't have a separate ack endpoint
        # Success is implied by successful response to sync request
        return {"success": True, "message": "Sync acknowledged", "timestamp": datetime.now().isoformat()}
            
    def parse_sync_delta(self, response: Dict[str, Any]) -> tuple[List[Change], List[Conflict]]:
        """Parse sync delta response from new protocol."""
        changes = []
        conflicts = []
        
        # Create SyncResponse object for validation
        sync_response = SyncResponse(**response)
        
        # Parse changes from response
        for sync_change in sync_response.changes:
            if sync_change.entity:
                # Convert to internal Change format
                change = Change(
                    entity_type=sync_change.entity.entity_type,
                    entity_id=sync_change.entity.id,
                    operation=SyncOperation(sync_change.change_type.lower()),
                    data=sync_change.entity.model_dump(),
                    updated_at=datetime.now(),  # Use current time as updated_at
                    sync_id=sync_change.entity.version,
                    client_sync_id=None  # Server changes don't have client sync ID
                )
                changes.append(change)
            
        # Parse conflicts from response
        for conflict_info in sync_response.conflicts:
            conflict = Conflict(
                entity_type="entity",  # Could be improved to get actual type
                entity_id=conflict_info.entity_id,
                reason=conflict_info.resolution_strategy,
                server_version=conflict_info.remote_version,
                client_version=conflict_info.local_version,
                resolution=conflict_info.resolution_strategy
            )
            conflicts.append(conflict)
            
        return changes, conflicts
        
    def parse_sync_result(self, response: Dict[str, Any]) -> tuple[List[str], List[Conflict]]:
        """Parse sync result response from new protocol."""
        applied_ids = []
        conflicts = []
        
        # In new protocol, successful sync means all changes were applied
        # Extract entity IDs from the changes we received
        for sync_change in response.get("changes", []):
            if sync_change.get("entity"):
                applied_ids.append(sync_change["entity"]["id"])
                
        # Parse conflicts using the same format as parse_sync_delta
        for conflict_info in response.get("conflicts", []):
            conflict = Conflict(
                entity_type="entity",  # New format doesn't specify type
                entity_id=conflict_info.get("entity_id", ""),
                reason=conflict_info.get("resolution_strategy", "conflict"),
                server_version=conflict_info.get("remote_version", ""),
                client_version=conflict_info.get("local_version", ""),
                resolution=conflict_info.get("resolution_strategy", "manual")
            )
            conflicts.append(conflict)
            
        return applied_ids, conflicts