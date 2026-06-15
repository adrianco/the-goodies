-- The Goodies SQLite Schema
-- Single database file for all smart home data
-- Optimized for local-first operation with denormalized design
-- Last-write-wins strategy using updated_at timestamps

-- Users table (denormalized for quick access)
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT,
    email TEXT,
    settings TEXT DEFAULT '{}', -- JSON: user preferences
    device_ids TEXT DEFAULT '[]', -- JSON array of device IDs
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Houses table (top-level entity)
CREATE TABLE houses (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    address TEXT,
    timezone TEXT DEFAULT 'UTC',
    location_lat REAL,
    location_lng REAL,
    attributes TEXT DEFAULT '{}', -- JSON: flexible attributes
    room_count INTEGER DEFAULT 0, -- Denormalized counter
    device_count INTEGER DEFAULT 0, -- Denormalized counter
    homekit_id TEXT, -- HomeKit UUID if imported
    matter_fabric_id TEXT, -- Matter fabric ID if applicable
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Rooms table (denormalized with house info)
CREATE TABLE rooms (
    id TEXT PRIMARY KEY,
    house_id TEXT NOT NULL,
    house_name TEXT NOT NULL, -- Denormalized from houses
    user_id TEXT NOT NULL, -- Denormalized from houses
    name TEXT NOT NULL,
    room_type TEXT, -- bedroom, kitchen, bathroom, etc.
    floor INTEGER DEFAULT 0,
    attributes TEXT DEFAULT '{}', -- JSON: flexible attributes
    device_count INTEGER DEFAULT 0, -- Denormalized counter
    temperature REAL, -- Latest temperature if available
    humidity REAL, -- Latest humidity if available
    occupancy_status TEXT DEFAULT 'unknown', -- occupied, vacant, unknown
    homekit_id TEXT, -- HomeKit UUID if imported
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Devices table (heavily denormalized for performance)
CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    room_name TEXT NOT NULL, -- Denormalized from rooms
    house_id TEXT NOT NULL, -- Denormalized from rooms
    house_name TEXT NOT NULL, -- Denormalized from houses
    user_id TEXT NOT NULL, -- Denormalized from houses
    name TEXT NOT NULL,
    device_type TEXT NOT NULL, -- light, switch, sensor, thermostat, etc.
    manufacturer TEXT,
    model TEXT,
    serial_number TEXT,
    firmware_version TEXT,
    capabilities TEXT DEFAULT '[]', -- JSON array: ["on_off", "brightness", "color"]
    current_state TEXT DEFAULT '{}', -- JSON: latest state snapshot
    attributes TEXT DEFAULT '{}', -- JSON: flexible attributes
    is_online BOOLEAN DEFAULT 1,
    is_reachable BOOLEAN DEFAULT 1,
    battery_level INTEGER, -- Percentage if battery-powered
    last_seen TIMESTAMP,
    homekit_id TEXT, -- HomeKit accessory UUID
    matter_node_id TEXT, -- Matter node ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Entity states table (time-series data, last-write-wins)
CREATE TABLE entity_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL, -- Can reference any entity (device, room, house)
    entity_type TEXT NOT NULL, -- 'device', 'room', 'house'
    state_key TEXT NOT NULL, -- e.g., 'power', 'brightness', 'temperature'
    state_value TEXT NOT NULL, -- Store as text, parse based on state_key
    attributes TEXT DEFAULT '{}', -- JSON: additional state attributes
    source TEXT, -- 'homekit', 'matter', 'manual', 'automation'
    device_id TEXT, -- If state is from a specific device
    room_id TEXT, -- Denormalized for quick filtering
    house_id TEXT, -- Denormalized for quick filtering
    user_id TEXT NOT NULL, -- Denormalized for access control
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Events table (audit log and automation triggers)
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL, -- 'state_change', 'user_action', 'automation', 'error'
    entity_id TEXT, -- Related entity if applicable
    entity_type TEXT, -- 'device', 'room', 'house', 'user'
    event_data TEXT DEFAULT '{}', -- JSON: event-specific data
    trigger_source TEXT, -- What triggered this event
    device_id TEXT, -- Denormalized if device-related
    room_id TEXT, -- Denormalized if room-related
    house_id TEXT, -- Denormalized if house-related
    user_id TEXT NOT NULL, -- Who/what caused the event
    severity TEXT DEFAULT 'info', -- 'debug', 'info', 'warning', 'error', 'critical'
    processed BOOLEAN DEFAULT 0, -- For event processing queues
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Sync metadata table (for Inbetweenies protocol)
CREATE TABLE sync_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_houses_user_id ON houses(user_id);
CREATE INDEX idx_houses_updated_at ON houses(updated_at);

CREATE INDEX idx_rooms_house_id ON rooms(house_id);
CREATE INDEX idx_rooms_user_id ON rooms(user_id);
CREATE INDEX idx_rooms_updated_at ON rooms(updated_at);

CREATE INDEX idx_devices_room_id ON devices(room_id);
CREATE INDEX idx_devices_house_id ON devices(house_id);
CREATE INDEX idx_devices_user_id ON devices(user_id);
CREATE INDEX idx_devices_type ON devices(device_type);
CREATE INDEX idx_devices_updated_at ON devices(updated_at);
CREATE INDEX idx_devices_online_status ON devices(is_online, is_reachable);

CREATE INDEX idx_entity_states_entity ON entity_states(entity_id, entity_type);
CREATE INDEX idx_entity_states_key ON entity_states(state_key);
CREATE INDEX idx_entity_states_house ON entity_states(house_id, updated_at);
CREATE INDEX idx_entity_states_room ON entity_states(room_id, updated_at);
CREATE INDEX idx_entity_states_device ON entity_states(device_id, updated_at);
CREATE INDEX idx_entity_states_updated ON entity_states(updated_at);

CREATE INDEX idx_events_entity ON events(entity_id, entity_type);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_house ON events(house_id, created_at);
CREATE INDEX idx_events_processed ON events(processed, created_at);
CREATE INDEX idx_events_severity ON events(severity, created_at);

-- Create triggers to maintain updated_at timestamps
CREATE TRIGGER update_users_timestamp 
    AFTER UPDATE ON users
    FOR EACH ROW
    BEGIN
        UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER update_houses_timestamp 
    AFTER UPDATE ON houses
    FOR EACH ROW
    BEGIN
        UPDATE houses SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER update_rooms_timestamp 
    AFTER UPDATE ON rooms
    FOR EACH ROW
    BEGIN
        UPDATE rooms SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER update_devices_timestamp 
    AFTER UPDATE ON devices
    FOR EACH ROW
    BEGIN
        UPDATE devices SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

CREATE TRIGGER update_entity_states_timestamp 
    AFTER UPDATE ON entity_states
    FOR EACH ROW
    BEGIN
        UPDATE entity_states SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

-- Create triggers to maintain denormalized counters
CREATE TRIGGER increment_room_count
    AFTER INSERT ON rooms
    FOR EACH ROW
    BEGIN
        UPDATE houses SET room_count = room_count + 1 WHERE id = NEW.house_id;
    END;

CREATE TRIGGER decrement_room_count
    AFTER DELETE ON rooms
    FOR EACH ROW
    BEGIN
        UPDATE houses SET room_count = room_count - 1 WHERE id = OLD.house_id;
    END;

CREATE TRIGGER increment_device_count
    AFTER INSERT ON devices
    FOR EACH ROW
    BEGIN
        UPDATE rooms SET device_count = device_count + 1 WHERE id = NEW.room_id;
        UPDATE houses SET device_count = device_count + 1 WHERE id = NEW.house_id;
    END;

CREATE TRIGGER decrement_device_count
    AFTER DELETE ON devices
    FOR EACH ROW
    BEGIN
        UPDATE rooms SET device_count = device_count - 1 WHERE id = OLD.room_id;
        UPDATE houses SET device_count = device_count - 1 WHERE id = OLD.house_id;
    END;

-- View for latest device states (convenience)
CREATE VIEW latest_device_states AS
SELECT 
    d.id as device_id,
    d.name as device_name,
    d.device_type,
    d.room_name,
    d.house_name,
    d.current_state,
    d.is_online,
    d.is_reachable,
    d.battery_level,
    d.last_seen,
    d.updated_at
FROM devices d
WHERE d.updated_at = (
    SELECT MAX(updated_at) 
    FROM devices 
    WHERE id = d.id
);

-- View for room summaries (convenience)
CREATE VIEW room_summaries AS
SELECT 
    r.id as room_id,
    r.name as room_name,
    r.room_type,
    r.house_name,
    r.device_count,
    r.temperature,
    r.humidity,
    r.occupancy_status,
    COUNT(CASE WHEN d.is_online = 1 THEN 1 END) as online_devices,
    COUNT(CASE WHEN d.battery_level < 20 THEN 1 END) as low_battery_devices,
    r.updated_at
FROM rooms r
LEFT JOIN devices d ON r.id = d.room_id
GROUP BY r.id;

-- Initial system user and metadata
INSERT INTO sync_metadata (key, value) VALUES 
    ('schema_version', '1.0.0'),
    ('last_sync', ''),
    ('device_id', lower(hex(randomblob(16)))),
    ('vector_clock', '{}');