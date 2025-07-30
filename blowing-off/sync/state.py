"""
Sync state management for offline support and conflict tracking.

Manages local sync metadata, pending changes, and conflict resolution state.
"""

import json
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict
import sqlite3

from inbetweenies.models import Entity, EntityRelationship


@dataclass
class PendingChange:
    """A change waiting to be synced"""
    id: str
    change_type: str  # create, update, delete
    entity_id: Optional[str] = None
    entity_data: Optional[Dict] = None
    relationship_data: Optional[Dict] = None
    created_at: datetime = None
    attempts: int = 0
    last_error: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


@dataclass  
class SyncMetrics:
    """Sync performance metrics"""
    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    total_entities_synced: int = 0
    total_relationships_synced: int = 0
    total_conflicts: int = 0
    last_sync_duration_ms: float = 0
    average_sync_duration_ms: float = 0
    
    def update_sync(self, success: bool, duration_ms: float, 
                   entities: int = 0, relationships: int = 0, conflicts: int = 0):
        """Update metrics after a sync"""
        self.total_syncs += 1
        if success:
            self.successful_syncs += 1
        else:
            self.failed_syncs += 1
            
        self.total_entities_synced += entities
        self.total_relationships_synced += relationships
        self.total_conflicts += conflicts
        self.last_sync_duration_ms = duration_ms
        
        # Update average
        if self.total_syncs > 0:
            self.average_sync_duration_ms = (
                (self.average_sync_duration_ms * (self.total_syncs - 1) + duration_ms) 
                / self.total_syncs
            )


class SyncStateManager:
    """Manage local sync state and metadata"""
    
    def __init__(self, storage_path: str = None):
        self.storage_path = Path(storage_path or "~/.blowing-off/sync").expanduser()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.storage_path / "sync_state.db"
        self.vector_clock = {}
        self.pending_changes: List[PendingChange] = []
        self.metrics = SyncMetrics()
        
        self._init_database()
        self._load_state()
        
    def _init_database(self):
        """Initialize SQLite database for sync state"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_changes (
                    id TEXT PRIMARY KEY,
                    change_type TEXT NOT NULL,
                    entity_id TEXT,
                    entity_data TEXT,
                    relationship_data TEXT,
                    created_at TIMESTAMP,
                    attempts INTEGER DEFAULT 0,
                    last_error TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    sync_type TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    success BOOLEAN,
                    entities_synced INTEGER,
                    relationships_synced INTEGER,
                    conflicts INTEGER,
                    error TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conflict_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT,
                    local_version TEXT,
                    remote_version TEXT,
                    resolution_strategy TEXT,
                    resolved_version TEXT,
                    created_at TIMESTAMP,
                    resolved_at TIMESTAMP
                )
            """)
            
    def _load_state(self):
        """Load state from database"""
        with sqlite3.connect(self.db_path) as conn:
            # Load vector clock
            cursor = conn.execute(
                "SELECT value FROM sync_metadata WHERE key = 'vector_clock'"
            )
            row = cursor.fetchone()
            if row:
                self.vector_clock = json.loads(row[0])
            
            # Load pending changes
            cursor = conn.execute(
                "SELECT * FROM pending_changes ORDER BY created_at"
            )
            for row in cursor:
                change = PendingChange(
                    id=row[0],
                    change_type=row[1],
                    entity_id=row[2],
                    entity_data=json.loads(row[3]) if row[3] else None,
                    relationship_data=json.loads(row[4]) if row[4] else None,
                    created_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    attempts=row[6],
                    last_error=row[7]
                )
                self.pending_changes.append(change)
            
            # Load metrics
            cursor = conn.execute(
                "SELECT value FROM sync_metadata WHERE key = 'metrics'"
            )
            row = cursor.fetchone()
            if row:
                metrics_data = json.loads(row[0])
                self.metrics = SyncMetrics(**metrics_data)
    
    def update_vector_clock(self, device_id: str, version: str):
        """Update vector clock for device"""
        self.vector_clock[device_id] = version
        self._save_metadata("vector_clock", self.vector_clock)
    
    def add_pending_change(self, change: PendingChange):
        """Add a change to pending queue"""
        self.pending_changes.append(change)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO pending_changes 
                (id, change_type, entity_id, entity_data, relationship_data, 
                 created_at, attempts, last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                change.id,
                change.change_type,
                change.entity_id,
                json.dumps(change.entity_data) if change.entity_data else None,
                json.dumps(change.relationship_data) if change.relationship_data else None,
                change.created_at.isoformat() if change.created_at else None,
                change.attempts,
                change.last_error
            ))
    
    def get_pending_changes(self) -> List[PendingChange]:
        """Get changes pending sync"""
        return self.pending_changes.copy()
    
    def mark_synced(self, change_id: str):
        """Mark a change as synced"""
        self.pending_changes = [c for c in self.pending_changes if c.id != change_id]
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM pending_changes WHERE id = ?", (change_id,))
    
    def mark_failed(self, change_id: str, error: str):
        """Mark a change as failed"""
        for change in self.pending_changes:
            if change.id == change_id:
                change.attempts += 1
                change.last_error = error
                break
                
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE pending_changes 
                SET attempts = attempts + 1, last_error = ?
                WHERE id = ?
            """, (error, change_id))
    
    def get_sync_metrics(self) -> SyncMetrics:
        """Get sync performance metrics"""
        return self.metrics
    
    def record_sync(self, device_id: str, sync_type: str, start_time: datetime,
                   success: bool, entities: int = 0, relationships: int = 0,
                   conflicts: int = 0, error: str = None):
        """Record a sync operation"""
        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        # Update metrics
        self.metrics.update_sync(success, duration_ms, entities, relationships, conflicts)
        self._save_metadata("metrics", asdict(self.metrics))
        
        # Record in history
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO sync_history
                (device_id, sync_type, started_at, completed_at, success,
                 entities_synced, relationships_synced, conflicts, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, sync_type, start_time.isoformat(), end_time.isoformat(),
                success, entities, relationships, conflicts, error
            ))
    
    def record_conflict(self, entity_id: str, local_version: str, remote_version: str,
                       resolution_strategy: str, resolved_version: str = None):
        """Record a conflict resolution"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO conflict_log
                (entity_id, local_version, remote_version, resolution_strategy,
                 resolved_version, created_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                entity_id, local_version, remote_version, resolution_strategy,
                resolved_version, datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat() if resolved_version else None
            ))
    
    def get_sync_history(self, limit: int = 10) -> List[Dict]:
        """Get recent sync history"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM sync_history 
                ORDER BY started_at DESC 
                LIMIT ?
            """, (limit,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor]
    
    def get_conflict_history(self, entity_id: str = None) -> List[Dict]:
        """Get conflict history"""
        with sqlite3.connect(self.db_path) as conn:
            if entity_id:
                cursor = conn.execute(
                    "SELECT * FROM conflict_log WHERE entity_id = ? ORDER BY created_at DESC",
                    (entity_id,)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM conflict_log ORDER BY created_at DESC LIMIT 100"
                )
                
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor]
    
    def clear_old_history(self, days: int = 30):
        """Clear old sync history"""
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM sync_history WHERE started_at < datetime(?, 'unixepoch')",
                (cutoff,)
            )
            conn.execute(
                "DELETE FROM conflict_log WHERE created_at < datetime(?, 'unixepoch')",
                (cutoff,)
            )
    
    def _save_metadata(self, key: str, value: any):
        """Save metadata to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sync_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, json.dumps(value), datetime.now(timezone.utc).isoformat()))
    
    def get_last_sync_time(self, device_id: str) -> Optional[datetime]:
        """Get last successful sync time for device"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT completed_at FROM sync_history
                WHERE device_id = ? AND success = 1
                ORDER BY completed_at DESC
                LIMIT 1
            """, (device_id,))
            
            row = cursor.fetchone()
            if row:
                return datetime.fromisoformat(row[0])
        
        return None