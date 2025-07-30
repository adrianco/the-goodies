# Inbetweenies - Shared Models and Sync Protocol

## Overview

Inbetweenies is the shared package containing HomeKit-compatible models and synchronization utilities used by both the FunkyGibbon server and Blowing-Off client. It ensures consistency across the system.

## Structure

```
inbetweenies/
├── models/          # HomeKit-compatible SQLAlchemy models
│   ├── __init__.py  # Model exports
│   ├── base.py      # Base model with timestamps and sync fields
│   ├── home.py      # Home model (HMHome)
│   ├── room.py      # Room model (HMRoom)
│   ├── accessory.py # Accessory model (HMAccessory)
│   ├── service.py   # Service model (HMService)
│   ├── characteristic.py # Characteristic model (HMCharacteristic)
│   └── user.py      # User model (HMUser)
├── sync/            # Synchronization utilities
│   ├── __init__.py
│   └── conflict.py  # Conflict resolution logic
└── __init__.py
```

## Models

All models inherit from `InbetweeniesTimestampMixin` which provides:
- `created_at` - UTC timestamp of creation
- `updated_at` - UTC timestamp of last update
- `sync_id` - UUID for sync tracking

### Home (HMHome)
```python
- id: str (UUID)
- name: str
- is_primary: bool
- sync_id: str
- created_at: datetime
- updated_at: datetime
```

### Room (HMRoom)
```python
- id: str (UUID)
- home_id: str (foreign key)
- name: str
- sync_id: str
- created_at: datetime
- updated_at: datetime
```

### Accessory (HMAccessory)
```python
- id: str (UUID)
- home_id: str (foreign key)
- name: str
- manufacturer: str
- model: str
- serial_number: str (optional)
- firmware_version: str (optional)
- is_reachable: bool
- is_blocked: bool
- is_bridge: bool
- bridge_id: str (optional)
- sync_id: str
- created_at: datetime
- updated_at: datetime
```

### Service (HMService)
```python
- id: str (UUID)
- accessory_id: str (foreign key)
- service_type: str
- name: str
- is_primary: bool
- is_hidden: bool
- linked_services: List[str]
- sync_id: str
- created_at: datetime
- updated_at: datetime
```

### Characteristic (HMCharacteristic)
```python
- id: str (UUID)
- service_id: str (foreign key)
- characteristic_type: str
- value: str (JSON)
- metadata: dict
- is_notification_enabled: bool
- sync_id: str
- created_at: datetime
- updated_at: datetime
```

### User (HMUser)
```python
- id: str (UUID)
- home_id: str (foreign key)
- name: str
- is_administrator: bool
- is_owner: bool
- remote_access_allowed: bool
- sync_id: str
- created_at: datetime
- updated_at: datetime
```

## Sync Protocol

The sync package provides conflict resolution using a last-write-wins strategy:

```python
from inbetweenies.sync import ConflictResolver

resolver = ConflictResolver()
resolution = resolver.resolve(local_data, remote_data)

if resolution.winner == remote_data:
    # Apply remote changes
else:
    # Keep local changes
```

### Conflict Resolution Rules

1. Compare `updated_at` timestamps
2. If within 1 second, compare `sync_id` values
3. Higher value wins (lexicographic comparison)
4. All conflicts are tracked for reporting

## Usage

### Server (FunkyGibbon)
```python
from inbetweenies.models import Home, Room, Accessory

# Models are used directly with SQLAlchemy
home = Home(name="My Home", is_primary=True)
session.add(home)
await session.commit()
```

### Client (Blowing-Off)
```python
from inbetweenies.models import Home
from inbetweenies.sync import ConflictResolver

# Same models, same sync logic
resolver = ConflictResolver()
# ... sync implementation
```

## Benefits

1. **Single Source of Truth**: No duplicate model definitions
2. **Consistency**: Server and client use identical models
3. **HomeKit Compatibility**: Direct mapping to Apple's HomeKit framework
4. **Type Safety**: Full type hints for all models
5. **Sync Support**: Built-in fields for synchronization

## Future Enhancements

- Add model validation
- Implement model serialization helpers
- Add HomeKit-specific constraints
- Support for model migrations