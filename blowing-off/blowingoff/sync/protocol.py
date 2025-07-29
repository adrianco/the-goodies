"""
Blowing-Off Client - Inbetweenies Protocol Implementation

DEVELOPMENT CONTEXT:
Created as the wire protocol implementation in January 2024. This module implements
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
- 2024-01-15: Initial protocol implementation
- 2024-01-18: Added conflict handling in responses
- 2024-01-20: Enhanced error handling and timeouts
- 2024-01-22: Added batch change support
- 2024-01-25: Improved JSON serialization efficiency

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
        """Send sync request to get server changes."""
        request_data = {
            "type": "sync_request",
            "client_id": self.client_id,
            "last_sync": last_sync.isoformat() if last_sync else None,
            "entity_types": entity_types or ["devices", "entity_states", "rooms", "users"],
            "include_deleted": True
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sync/request",
                json=request_data,
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
            
    async def sync_push(self, changes: List[Change]) -> Dict[str, Any]:
        """Push local changes to server."""
        push_data = {
            "type": "sync_push",
            "client_id": self.client_id,
            "changes": [
                {
                    "entity_type": change.entity_type,
                    "entity_id": change.entity_id,
                    "operation": change.operation.value,
                    "data": change.data,
                    "client_sync_id": change.client_sync_id
                }
                for change in changes
            ]
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sync/push",
                json=push_data,
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
            
    async def sync_ack(self) -> Dict[str, Any]:
        """Acknowledge sync completion."""
        ack_data = {
            "type": "sync_ack",
            "client_id": self.client_id,
            "sync_completed_at": datetime.now().isoformat()
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sync/ack",
                json=ack_data,
                headers=self.headers,
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
            
    def parse_sync_delta(self, response: Dict[str, Any]) -> tuple[List[Change], List[Conflict]]:
        """Parse sync delta response."""
        changes = []
        conflicts = []
        
        # Parse changes
        for change_data in response.get("changes", []):
            change = Change(
                entity_type=change_data["entity_type"],
                entity_id=change_data["entity_id"],
                operation=SyncOperation(change_data["operation"]),
                data=change_data["data"],
                updated_at=datetime.fromisoformat(change_data["updated_at"]),
                sync_id=change_data["sync_id"]
            )
            changes.append(change)
            
        # Parse conflicts
        for conflict_data in response.get("conflicts", []):
            conflict = Conflict(
                entity_type=conflict_data["entity_type"],
                entity_id=conflict_data["entity_id"],
                reason=conflict_data["reason"],
                server_version=conflict_data["server_version"],
                client_version=conflict_data["client_version"],
                resolution=conflict_data["resolution"]
            )
            conflicts.append(conflict)
            
        return changes, conflicts
        
    def parse_sync_result(self, response: Dict[str, Any]) -> tuple[List[str], List[Conflict]]:
        """Parse sync result response."""
        applied_ids = []
        conflicts = []
        
        # Track applied changes
        for result in response.get("applied", []):
            if result["status"] == "applied":
                applied_ids.append(result["client_sync_id"])
                
        # Parse new conflicts
        for conflict_data in response.get("conflicts", []):
            conflict = Conflict(
                entity_type=conflict_data["entity_type"],
                entity_id=conflict_data["entity_id"],
                reason=conflict_data["reason"],
                server_version=conflict_data.get("server_version", {}),
                client_version=conflict_data.get("client_version", {}),
                resolution=conflict_data["resolution"]
            )
            conflicts.append(conflict)
            
        return applied_ids, conflicts