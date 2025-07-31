# Rollback and Risk Mitigation Strategies

## Overview
This document outlines comprehensive rollback procedures and risk mitigation strategies for each phase of the homegraph migration. The goal is to ensure we can safely revert changes if issues arise while minimizing impact on users.

## Risk Assessment Matrix

| Risk | Probability | Impact | Mitigation Strategy |
|------|------------|--------|-------------------|
| Data Loss During Migration | Low | Critical | Automated backups, validation scripts |
| API Breaking Changes | Medium | High | Versioned endpoints, compatibility layer |
| Performance Degradation | Medium | Medium | Benchmarking, gradual rollout |
| Sync Protocol Incompatibility | Low | High | Protocol negotiation, adapters |
| HomeKit Import Failures | Medium | Low | Fallback to manual entry |
| Client-Server Version Mismatch | High | Medium | Version checking, auto-updates |

## Phase-Specific Strategies

### Phase 2: Graph Operations Rollback

#### Pre-Migration Checklist
```bash
#!/bin/bash
# pre_migration_phase2.sh

# 1. Create full database backup
echo "Creating database backup..."
pg_dump funkygibbon_db > backups/pre_phase2_$(date +%Y%m%d_%H%M%S).sql

# 2. Export current data in portable format
python scripts/export_homekit_data.py --output backups/homekit_export.json

# 3. Document current API responses
python scripts/document_api_responses.py --output docs/api_baseline.json

# 4. Performance baseline
python scripts/performance_baseline.py --output metrics/baseline.json

echo "Pre-migration backup complete"
```

#### Feature Flags Implementation
```python
# funkygibbon/config/features.py
from enum import Enum

class Feature(Enum):
    GRAPH_OPERATIONS = "graph_operations"
    MCP_SERVER = "mcp_server"
    ENHANCED_SYNC = "enhanced_sync"
    ENTITY_VERSIONING = "entity_versioning"

class FeatureFlags:
    """Runtime feature toggles"""
    
    def __init__(self):
        self._flags = {
            Feature.GRAPH_OPERATIONS: False,  # Start disabled
            Feature.MCP_SERVER: False,
            Feature.ENHANCED_SYNC: False,
            Feature.ENTITY_VERSIONING: False
        }
    
    def is_enabled(self, feature: Feature) -> bool:
        """Check if feature is enabled"""
        return self._flags.get(feature, False)
    
    def enable(self, feature: Feature):
        """Enable a feature"""
        self._flags[feature] = True
        self._log_change(feature, True)
    
    def disable(self, feature: Feature):
        """Disable a feature for rollback"""
        self._flags[feature] = False
        self._log_change(feature, False)
```

#### Database Rollback Strategy
```python
# scripts/rollback_phase2.py
import asyncio
from sqlalchemy import text

async def rollback_graph_tables():
    """Rollback graph-specific database changes"""
    
    async with get_db_connection() as conn:
        # Check if new tables exist
        result = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name IN ('entities', 'entity_relationships')
        """))
        
        if result.rowcount > 0:
            print("Rolling back graph tables...")
            
            # Drop new tables
            await conn.execute(text("DROP TABLE IF EXISTS entity_relationships CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS entities CASCADE"))
            
            # Remove new columns from existing tables
            await conn.execute(text("""
                ALTER TABLE accessories 
                DROP COLUMN IF EXISTS entity_id
            """))
            
            await conn.commit()
            print("Graph tables rolled back")
```

#### API Compatibility Layer
```python
# funkygibbon/api/compatibility.py
from functools import wraps

def versioned_endpoint(min_version: str = "v1", max_version: str = None):
    """Decorator for version-specific endpoints"""
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            client_version = request.headers.get("API-Version", "v1")
            
            if client_version < min_version:
                # Use legacy response format
                result = await func(request, *args, **kwargs)
                return convert_to_legacy_format(result)
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator

# Usage in routers
@router.get("/devices")
@versioned_endpoint(min_version="v2")
async def get_devices_v2(room_id: str = None):
    """New graph-based device query"""
    # Implementation
```

### Phase 3: Inbetweenies Protocol Rollback

#### Protocol Version Fallback
```python
# inbetweenies/sync/fallback.py
class ProtocolFallback:
    """Handle protocol version mismatches"""
    
    def __init__(self):
        self.handlers = {
            "inbetweenies-v1": V1ProtocolHandler(),
            "inbetweenies-v2": V2ProtocolHandler()
        }
    
    async def handle_sync_request(self, request: dict) -> dict:
        """Route to appropriate protocol handler"""
        version = request.get("protocol_version", "inbetweenies-v1")
        
        if version not in self.handlers:
            # Fallback to v1
            logger.warning(f"Unknown protocol version {version}, falling back to v1")
            version = "inbetweenies-v1"
        
        handler = self.handlers[version]
        return await handler.process(request)
```

#### Client Update Strategy
```python
# blowing-off/sync/auto_update.py
class AutoUpdateManager:
    """Manage client updates for protocol changes"""
    
    async def check_for_updates(self):
        """Check if client update is required"""
        try:
            response = await self.http_client.get(
                f"{self.server_url}/api/version"
            )
            server_version = response.json()
            
            if self.requires_update(server_version):
                return await self.prompt_update(server_version)
                
        except Exception as e:
            # Continue with current version if check fails
            logger.error(f"Update check failed: {e}")
            return False
```

### Phase 4: Swift/WildThing Rollback

#### Version Migration in Swift
```swift
// Sources/WildThing/Migration/VersionMigration.swift
public class VersionMigration {
    private let storage: StorageProtocol
    
    public func migrateIfNeeded() async throws {
        let currentVersion = try await storage.getSchemaVersion()
        
        switch currentVersion {
        case 1:
            try await migrateV1ToV2()
        case 2:
            // Current version
            break
        default:
            throw MigrationError.unknownVersion(currentVersion)
        }
    }
    
    public func rollback(to version: Int) async throws {
        let currentVersion = try await storage.getSchemaVersion()
        
        if version >= currentVersion {
            throw MigrationError.cannotRollbackToFutureVersion
        }
        
        // Backup current data
        try await storage.createBackup(label: "pre_rollback_\\(Date())")
        
        // Execute rollback
        switch (currentVersion, version) {
        case (2, 1):
            try await rollbackV2ToV1()
        default:
            throw MigrationError.unsupportedRollback
        }
    }
}
```

## Risk Mitigation Procedures

### 1. Data Integrity Protection

#### Continuous Validation
```python
# funkygibbon/monitors/data_integrity.py
class DataIntegrityMonitor:
    """Monitor data integrity during migration"""
    
    async def validate_migration(self):
        """Run integrity checks"""
        checks = [
            self.check_entity_counts(),
            self.check_relationship_integrity(),
            self.check_orphaned_records(),
            self.check_data_consistency()
        ]
        
        results = await asyncio.gather(*checks)
        
        if not all(results):
            raise DataIntegrityError("Migration validation failed")
    
    async def check_entity_counts(self) -> bool:
        """Verify entity counts match"""
        old_count = await self.count_homekit_entities()
        new_count = await self.count_graph_entities()
        
        if abs(old_count - new_count) > 0:
            logger.error(f"Entity count mismatch: {old_count} vs {new_count}")
            return False
        return True
```

#### Transaction Management
```python
# funkygibbon/migrations/transactional.py
from contextlib import asynccontextmanager

@asynccontextmanager
async def migration_transaction():
    """Transactional migration with automatic rollback"""
    async with get_db_connection() as conn:
        trans = await conn.begin()
        try:
            yield conn
            await trans.commit()
        except Exception as e:
            await trans.rollback()
            logger.error(f"Migration failed, rolling back: {e}")
            raise
```

### 2. Performance Monitoring

#### Real-time Metrics
```python
# funkygibbon/monitors/performance.py
class PerformanceMonitor:
    """Monitor performance during migration"""
    
    def __init__(self):
        self.metrics = {
            "query_times": [],
            "memory_usage": [],
            "cpu_usage": [],
            "error_rates": defaultdict(int)
        }
    
    async def check_degradation(self) -> bool:
        """Check for performance degradation"""
        baseline = await self.load_baseline()
        current = await self.collect_metrics()
        
        # Compare against baseline
        if current["avg_query_time"] > baseline["avg_query_time"] * 1.5:
            logger.warning("Query time degradation detected")
            return False
        
        if current["memory_usage"] > baseline["memory_usage"] * 2:
            logger.warning("Memory usage spike detected")
            return False
        
        return True
```

### 3. Gradual Rollout Strategy

#### Canary Deployment
```python
# funkygibbon/deployment/canary.py
class CanaryDeployment:
    """Gradual feature rollout"""
    
    def __init__(self):
        self.rollout_percentage = 0
        self.user_buckets = self._generate_buckets()
    
    def should_enable_feature(self, user_id: str, feature: str) -> bool:
        """Check if feature should be enabled for user"""
        if self.rollout_percentage == 0:
            return False
        if self.rollout_percentage == 100:
            return True
        
        # Consistent hashing for user bucketing
        bucket = hash(f"{user_id}:{feature}") % 100
        return bucket < self.rollout_percentage
    
    async def increase_rollout(self, increment: int = 10):
        """Gradually increase rollout"""
        self.rollout_percentage = min(100, self.rollout_percentage + increment)
        logger.info(f"Rollout increased to {self.rollout_percentage}%")
        
        # Monitor for issues
        if await self.detect_issues():
            await self.emergency_rollback()
```

### 4. Emergency Response Procedures

#### Automated Rollback Triggers
```python
# funkygibbon/emergency/triggers.py
class EmergencyTriggers:
    """Automated rollback triggers"""
    
    def __init__(self):
        self.thresholds = {
            "error_rate": 0.05,  # 5% error rate
            "response_time": 1000,  # 1 second
            "memory_usage": 1024 * 1024 * 512,  # 512MB
            "sync_failures": 10  # consecutive failures
        }
    
    async def monitor(self):
        """Monitor for emergency conditions"""
        while True:
            metrics = await self.collect_metrics()
            
            if metrics["error_rate"] > self.thresholds["error_rate"]:
                await self.trigger_rollback("High error rate")
            
            if metrics["p95_response_time"] > self.thresholds["response_time"]:
                await self.trigger_rollback("High response time")
            
            await asyncio.sleep(60)  # Check every minute
    
    async def trigger_rollback(self, reason: str):
        """Execute emergency rollback"""
        logger.critical(f"Emergency rollback triggered: {reason}")
        
        # 1. Disable new features
        await feature_flags.disable_all()
        
        # 2. Restore from backup
        await restore_latest_backup()
        
        # 3. Notify team
        await send_emergency_notification(reason)
```

## Communication Plan

### Stakeholder Notification
```markdown
# Migration Status Template

## Migration Phase: [Phase Name]
Status: [In Progress | Completed | Rolled Back]
Start Time: [Timestamp]
Expected Duration: [Duration]

### Current Status
- [ ] Pre-migration backup completed
- [ ] Feature flags configured
- [ ] Migration script executed
- [ ] Validation checks passed
- [ ] Performance monitoring active

### Rollback Status
Rollback Available: [Yes/No]
Rollback Window: [Duration]
Rollback Command: `python scripts/rollback_phase[N].py`

### Contact
Primary: [Name] ([email])
Secondary: [Name] ([email])
```

### User Communication
```python
# funkygibbon/notifications/user_notify.py
class UserNotification:
    """User-facing migration notifications"""
    
    async def notify_maintenance(self, duration: int):
        """Notify users of maintenance window"""
        message = {
            "type": "maintenance",
            "title": "Scheduled Maintenance",
            "body": f"Service upgrade in progress. Expected duration: {duration} minutes",
            "severity": "info"
        }
        await self.broadcast(message)
    
    async def notify_rollback(self):
        """Notify users of rollback"""
        message = {
            "type": "rollback",
            "title": "Service Restoration",
            "body": "We've restored the previous version. Your data is safe.",
            "severity": "warning"
        }
        await self.broadcast(message)
```

## Post-Rollback Procedures

### 1. Root Cause Analysis
- Collect all logs and metrics
- Identify failure point
- Document lessons learned
- Update rollback procedures

### 2. Data Reconciliation
- Verify data consistency
- Resolve any conflicts
- Restore user confidence

### 3. Communication
- Inform all stakeholders
- Publish post-mortem
- Update timeline

## Success Criteria for Safe Migration

1. **Backup Verification**: All backups tested and restorable
2. **Rollback Time**: < 15 minutes for any phase
3. **Data Integrity**: Zero data loss during rollback
4. **User Impact**: < 5 minutes of downtime
5. **Communication**: All stakeholders informed within 5 minutes

## Rollback Decision Matrix

| Scenario | Rollback? | Procedure |
|----------|-----------|-----------|
| >5% error rate | Yes | Immediate automated rollback |
| Performance degradation >50% | Yes | Gradual rollback with monitoring |
| Data inconsistency detected | Yes | Stop migration, investigate, rollback |
| Minor UI issues | No | Fix forward with patch |
| Feature adoption <10% | No | Investigate and improve |
| Security vulnerability | Yes | Immediate rollback and patch |