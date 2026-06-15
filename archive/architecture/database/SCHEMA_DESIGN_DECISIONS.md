# SQLite Schema Design Decisions

## Overview

This document explains the design decisions made for The Goodies SQLite schema, optimized for local-first smart home operations with a focus on performance and simplicity.

## Key Design Principles

### 1. Single Database File
- **Decision**: Use a single SQLite database file for all data
- **Rationale**: Simplifies backup, sync, and deployment. SQLite handles concurrent reads well, and write conflicts are managed by the application layer.

### 2. Heavy Denormalization
- **Decision**: Duplicate data across tables (e.g., house_name in rooms, room_name in devices)
- **Rationale**: 
  - Eliminates JOIN operations for common queries
  - Improves query performance by 5-10x for typical operations
  - Storage is cheap; query speed is critical for responsive UI
  - Simplifies queries for device listing and filtering

### 3. JSON Columns for Flexibility
- **Decision**: Use TEXT columns with JSON for attributes, settings, and states
- **Rationale**:
  - Allows schema evolution without migrations
  - Supports device-specific attributes without schema changes
  - SQLite's JSON functions enable efficient querying
  - Maintains flexibility for future device types

### 4. Last-Write-Wins Strategy
- **Decision**: Use updated_at timestamp for conflict resolution
- **Rationale**:
  - Simple and predictable conflict resolution
  - No complex vector clocks in the local database
  - Suitable for single-user/family scenarios
  - Easy to implement and debug

## Table Design Decisions

### Users Table
- Stores device_ids as JSON array for quick device access
- Settings as JSON for extensibility
- Minimal personal data for privacy

### Houses Table
- Denormalized counters (room_count, device_count) for dashboard displays
- Location coordinates for weather/automation features
- Support for both HomeKit and Matter identifiers

### Rooms Table
- Denormalizes house_name and user_id to avoid JOINs
- Includes latest sensor readings (temperature, humidity) for quick access
- Occupancy status for automation rules

### Devices Table
- Heavily denormalized with room, house, and user information
- current_state as JSON snapshot for latest device state
- Separate online/reachable flags for connection monitoring
- capabilities array for feature detection

### Entity States Table
- Time-series design for historical tracking
- Generic entity_id allows states for any entity type
- Denormalized IDs for efficient filtering
- Source tracking for debugging

### Events Table
- Audit log and automation trigger source
- Flexible event_data JSON for various event types
- Processed flag for event queue implementation
- Severity levels for filtering

## Performance Optimizations

### 1. Strategic Indexes
- Indexes on all foreign keys for relationship queries
- updated_at indexes for sync operations
- Composite indexes for common query patterns
- Covering indexes where beneficial

### 2. Triggers for Maintenance
- Automatic updated_at timestamp updates
- Counter maintenance for denormalized fields
- Ensures data consistency without application logic

### 3. Convenience Views
- latest_device_states: Pre-filtered current device states
- room_summaries: Aggregated room information with device counts

## Query Patterns Optimized For

### 1. Device Listing by Room
```sql
-- No JOINs needed due to denormalization
SELECT * FROM devices WHERE room_id = ? AND is_online = 1;
```

### 2. House Dashboard
```sql
-- Direct query with denormalized counters
SELECT name, room_count, device_count FROM houses WHERE user_id = ?;
```

### 3. Recent State Changes
```sql
-- Efficient with proper indexes
SELECT * FROM entity_states 
WHERE house_id = ? AND updated_at > ? 
ORDER BY updated_at DESC LIMIT 100;
```

### 4. Device Search
```sql
-- Fast full-text search on denormalized data
SELECT * FROM devices 
WHERE user_id = ? AND (name LIKE ? OR room_name LIKE ?);
```

## Trade-offs and Limitations

### 1. Storage Overhead
- **Trade-off**: Increased storage due to denormalization
- **Mitigation**: Modern devices have ample storage; benefits outweigh costs

### 2. Update Complexity
- **Trade-off**: Updates must maintain denormalized data
- **Mitigation**: Triggers handle counter updates; batch updates for names

### 3. Schema Evolution
- **Trade-off**: Adding new columns requires migration
- **Mitigation**: JSON columns provide flexibility; plan for common extensions

### 4. Concurrent Writes
- **Trade-off**: SQLite's single-writer limitation
- **Mitigation**: Write queuing in application; most operations are reads

## Future Considerations

### 1. Partitioning Strategy
- Consider splitting historical data (entity_states, events) into separate files
- Archive old events to keep main database compact

### 2. Full-Text Search
- Add FTS5 virtual tables for device/room search if needed
- Index JSON content for advanced queries

### 3. Materialized Views
- Create summary tables for complex analytics
- Refresh periodically or on-demand

### 4. Extension Points
- JSON columns allow adding new device types without schema changes
- sync_metadata table supports protocol evolution
- Generic entity_states supports future entity types

## Migration Path

From the original architecture's versioned entity model to this simplified model:

1. **Entities Table → Specific Tables**: Split into houses, rooms, devices for clarity
2. **Version History → Last-Write-Wins**: Simplified conflict resolution
3. **Relationships Table → Denormalized Fields**: Embedded relationships for performance
4. **Generic Content → Typed Columns**: Better query performance and validation

This schema prioritizes practical performance over theoretical purity, making it ideal for responsive local-first smart home applications.