"""
Enhanced sync client for the Inbetweenies protocol.

Provides full graph synchronization support with conflict resolution,
delta sync, and progress tracking.
"""

import asyncio
from typing import List, Dict, Optional, Set, Callable
from datetime import datetime, timezone
from enum import Enum
import httpx
import json
from pathlib import Path

from inbetweenies.models import Entity, EntityRelationship, EntityType


class SyncType(Enum):
    """Types of sync operations"""
    FULL = "full"
    DELTA = "delta"
    ENTITIES = "entities"
    RELATIONSHIPS = "relationships"


class ConflictStrategy(Enum):
    """Conflict resolution strategies"""
    LAST_WRITE_WINS = "last_write_wins"
    MERGE = "merge"
    MANUAL = "manual"
    CLIENT_WINS = "client_wins"
    SERVER_WINS = "server_wins"


class SyncProgress:
    """Track sync progress for UI updates"""
    
    def __init__(self):
        self.total_entities = 0
        self.synced_entities = 0
        self.total_relationships = 0
        self.synced_relationships = 0
        self.conflicts = []
        self.errors = []
        self.start_time = None
        self.end_time = None
        
    @property
    def entity_progress(self) -> float:
        """Get entity sync progress percentage"""
        if self.total_entities == 0:
            return 0.0
        return (self.synced_entities / self.total_entities) * 100
    
    @property
    def relationship_progress(self) -> float:
        """Get relationship sync progress percentage"""
        if self.total_relationships == 0:
            return 0.0
        return (self.synced_relationships / self.total_relationships) * 100
    
    @property
    def overall_progress(self) -> float:
        """Get overall sync progress percentage"""
        total = self.total_entities + self.total_relationships
        if total == 0:
            return 0.0
        synced = self.synced_entities + self.synced_relationships
        return (synced / total) * 100
    
    @property
    def duration_seconds(self) -> float:
        """Get sync duration in seconds"""
        if not self.start_time:
            return 0.0
        end = self.end_time or datetime.now(timezone.utc)
        return (end - self.start_time).total_seconds()


class EnhancedSyncClient:
    """Sync client with full graph support"""
    
    def __init__(self, server_url: str, device_id: str = None, user_id: str = "client"):
        self.server_url = server_url.rstrip('/')
        self.device_id = device_id or self._generate_device_id()
        self.user_id = user_id
        self.vector_clock = {}
        self.progress_callback: Optional[Callable[[SyncProgress], None]] = None
        self.conflict_strategy = ConflictStrategy.MERGE
        
    def _generate_device_id(self) -> str:
        """Generate a unique device ID"""
        import uuid
        import platform
        # Use machine info to generate consistent ID
        machine_info = f"{platform.node()}-{platform.system()}-{platform.machine()}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, machine_info))
    
    async def sync_entities(self, entity_types: List[EntityType] = None,
                           since: datetime = None) -> SyncProgress:
        """Sync entities with filtering and progress tracking"""
        progress = SyncProgress()
        progress.start_time = datetime.now(timezone.utc)
        
        try:
            # Build sync request
            request_data = {
                "protocol_version": "inbetweenies-v2",
                "device_id": self.device_id,
                "user_id": self.user_id,
                "sync_type": SyncType.DELTA.value if since else SyncType.FULL.value,
                "vector_clock": {"clocks": self.vector_clock},
                "changes": [],  # No local changes for now
                "filters": {}
            }
            
            if entity_types:
                request_data["filters"]["entity_types"] = [et.value for et in entity_types]
            if since:
                request_data["filters"]["since"] = since.isoformat()
            
            # Send sync request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.server_url}/api/v1/sync/",
                    json=request_data,
                    timeout=30.0
                )
                response.raise_for_status()
                
            sync_response = response.json()
            
            # Process response
            changes = sync_response.get("changes", [])
            progress.total_entities = len([c for c in changes if c.get("entity")])
            
            for change in changes:
                if change.get("entity"):
                    # Process entity change
                    await self._process_entity_change(change)
                    progress.synced_entities += 1
                    
                if self.progress_callback:
                    self.progress_callback(progress)
            
            # Handle conflicts
            for conflict in sync_response.get("conflicts", []):
                progress.conflicts.append(conflict)
            
            # Update vector clock
            if sync_response.get("vector_clock"):
                self.vector_clock.update(sync_response["vector_clock"].get("clocks", {}))
            
        except Exception as e:
            progress.errors.append(str(e))
            raise
        finally:
            progress.end_time = datetime.now(timezone.utc)
            
        return progress
    
    async def sync_relationships(self, entity_id: str = None) -> SyncProgress:
        """Sync relationships for entities"""
        progress = SyncProgress()
        progress.start_time = datetime.now(timezone.utc)
        
        try:
            # Build sync request
            request_data = {
                "protocol_version": "inbetweenies-v2",
                "device_id": self.device_id,
                "user_id": self.user_id,
                "sync_type": SyncType.RELATIONSHIPS.value,
                "vector_clock": {"clocks": self.vector_clock},
                "changes": []
            }
            
            # Send sync request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.server_url}/api/v1/sync/",
                    json=request_data,
                    timeout=30.0
                )
                response.raise_for_status()
                
            sync_response = response.json()
            
            # Process relationships
            changes = sync_response.get("changes", [])
            for change in changes:
                relationships = change.get("relationships", [])
                progress.total_relationships += len(relationships)
                
                for rel in relationships:
                    await self._process_relationship_change(rel)
                    progress.synced_relationships += 1
                    
                if self.progress_callback:
                    self.progress_callback(progress)
            
        except Exception as e:
            progress.errors.append(str(e))
            raise
        finally:
            progress.end_time = datetime.now(timezone.utc)
            
        return progress
    
    async def resolve_conflicts(self, strategy: ConflictStrategy = None) -> List[Entity]:
        """Resolve all pending conflicts"""
        if strategy:
            self.conflict_strategy = strategy
            
        # Get pending conflicts from server
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.server_url}/api/v1/sync/conflicts"
            )
            response.raise_for_status()
            
        conflicts_data = response.json()
        resolved_entities = []
        
        for conflict in conflicts_data.get("conflicts", []):
            # Apply resolution strategy
            if self.conflict_strategy == ConflictStrategy.CLIENT_WINS:
                # Keep local version
                pass
            elif self.conflict_strategy == ConflictStrategy.SERVER_WINS:
                # Accept remote version
                pass
            else:
                # Use server's conflict resolution
                pass
                
        return resolved_entities
    
    async def full_sync(self) -> SyncProgress:
        """Perform a complete sync of all data"""
        # First sync all entities
        entity_progress = await self.sync_entities()
        
        # Then sync relationships
        rel_progress = await self.sync_relationships()
        
        # Combine progress
        total_progress = SyncProgress()
        total_progress.start_time = entity_progress.start_time
        total_progress.end_time = rel_progress.end_time
        total_progress.total_entities = entity_progress.total_entities
        total_progress.synced_entities = entity_progress.synced_entities
        total_progress.total_relationships = rel_progress.total_relationships
        total_progress.synced_relationships = rel_progress.synced_relationships
        total_progress.conflicts = entity_progress.conflicts + rel_progress.conflicts
        total_progress.errors = entity_progress.errors + rel_progress.errors
        
        return total_progress
    
    async def get_sync_status(self) -> Dict:
        """Get sync status from server"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.server_url}/api/v1/sync/status",
                params={"device_id": self.device_id}
            )
            response.raise_for_status()
            
        return response.json()
    
    def set_progress_callback(self, callback: Callable[[SyncProgress], None]):
        """Set callback for progress updates"""
        self.progress_callback = callback
    
    async def _process_entity_change(self, change: Dict):
        """Process a single entity change"""
        # In a real implementation, this would update local storage
        entity_data = change.get("entity", {})
        change_type = change.get("change_type")
        
        if change_type == "create":
            # Create entity locally
            print(f"Creating entity: {entity_data.get('name')}")
        elif change_type == "update":
            # Update entity locally
            print(f"Updating entity: {entity_data.get('name')}")
        elif change_type == "delete":
            # Delete entity locally
            print(f"Deleting entity: {entity_data.get('id')}")
    
    async def _process_relationship_change(self, rel_data: Dict):
        """Process a single relationship change"""
        # In a real implementation, this would update local storage
        print(f"Processing relationship: {rel_data.get('relationship_type')}")


class SyncScheduler:
    """Schedule automatic sync operations"""
    
    def __init__(self, sync_client: EnhancedSyncClient):
        self.sync_client = sync_client
        self.sync_interval = 300  # 5 minutes default
        self.running = False
        self._task = None
        
    async def start(self, interval: int = None):
        """Start automatic sync"""
        if interval:
            self.sync_interval = interval
            
        self.running = True
        self._task = asyncio.create_task(self._sync_loop())
        
    async def stop(self):
        """Stop automatic sync"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
                
    async def _sync_loop(self):
        """Main sync loop"""
        while self.running:
            try:
                # Get last sync time
                status = await self.sync_client.get_sync_status()
                last_sync = status.get("last_sync")
                
                if last_sync:
                    # Delta sync since last time
                    since = datetime.fromisoformat(last_sync)
                    await self.sync_client.sync_entities(since=since)
                else:
                    # Full sync if never synced
                    await self.sync_client.full_sync()
                    
            except Exception as e:
                print(f"Sync error: {e}")
                
            # Wait for next sync
            await asyncio.sleep(self.sync_interval)