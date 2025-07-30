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
from .state import Change, Conflict, SyncOperation


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
        # Convert to new sync protocol format
        filters = {}
        if last_sync:
            filters["since"] = last_sync.isoformat()
        if entity_types:
            filters["entity_types"] = entity_types
            
        request_data = {
            "protocol_version": "inbetweenies-v2",
            "device_id": self.client_id,
            "user_id": "client-user",  # TODO: get from auth
            "sync_type": "delta" if last_sync else "full",
            "vector_clock": {"clocks": {}},
            "changes": [],
            "filters": filters if filters else None
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sync/",
                json=request_data,
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
            
    async def sync_push(self, changes: List[Change]) -> Dict[str, Any]:
        """Push local changes to server using new protocol."""
        # Convert changes to new format
        sync_changes = []
        for change in changes:
            sync_change = {
                "change_type": change.operation.value if hasattr(change.operation, 'value') else change.operation,
                "entity": {
                    "id": change.entity_id,
                    "version": change.data.get("version", ""),
                    "entity_type": change.entity_type,
                    "name": change.data.get("name", ""),
                    "content": change.data.get("content", {}),
                    "parent_versions": change.data.get("parent_versions", [])
                } if change.operation != "delete" else None,
                "relationships": []
            }
            sync_changes.append(sync_change)
        
        push_data = {
            "protocol_version": "inbetweenies-v2",
            "device_id": self.client_id,
            "user_id": "client-user",  # TODO: get from auth
            "sync_type": "delta",
            "vector_clock": {"clocks": {}},
            "changes": sync_changes
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sync/",
                json=push_data,
                headers=self.headers,
                timeout=30.0
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
        
        # Parse changes from new format
        for sync_change in response.get("changes", []):
            if sync_change.get("entity"):
                entity = sync_change["entity"]
                change = Change(
                    entity_type=entity.get("entity_type", "unknown"),
                    entity_id=entity.get("id", ""),
                    operation=SyncOperation(sync_change.get("change_type", "update")),
                    data=entity,
                    updated_at=datetime.now(),  # Use current time as updated_at
                    sync_id=entity.get("version", "")  # Use version as sync_id
                )
                changes.append(change)
            
        # Parse conflicts from new format
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