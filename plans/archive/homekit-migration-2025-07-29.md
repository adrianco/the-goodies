# HomeKit Model Migration Summary

## Overview

The Goodies system has been fully migrated to use Apple HomeKit-compatible models. This migration simplifies the data model and ensures compatibility with iOS/macOS HomeKit frameworks.

## Model Changes

### Primary Models (Migrated)

| Old Model | New Model | HomeKit Equivalent | Changes |
|-----------|-----------|-------------------|---------|
| House | Home | HMHome | Removed: address, timezone, latitude, longitude |
| Device | Accessory | HMAccessory | Added: manufacturer, model, serial_number, firmware_version |
| - | Service | HMService | New model for accessory capabilities |
| - | Characteristic | HMCharacteristic | New model for service properties |
| Room | Room | HMRoom | Removed: floor, room_type |
| User | User | HMUser | Removed: email, role; Added: is_administrator, is_owner |

### Removed Models

- **EntityState**: Functionality merged into Service/Characteristic models
- **Event**: Not part of HomeKit model; logging handled separately

### Shared Models Package

All models now live in the `inbetweenies` package, shared between server and client:
- `/workspaces/the-goodies/inbetweenies/models/`
- Ensures consistency between FunkyGibbon server and Blowing-Off client
- No duplicate model definitions

## API Endpoint Changes

| Old Endpoint | New Endpoint |
|--------------|--------------|
| /api/v1/houses/ | /api/v1/homes/ |
| /api/v1/devices/ | /api/v1/accessories/ |
| /api/v1/entity_states/ | (Removed - use characteristics) |
| /api/v1/events/ | (Removed) |

New endpoints added:
- /api/v1/services/
- /api/v1/characteristics/
- /api/v1/sync/request
- /api/v1/sync/push
- /api/v1/sync/ack

## Database Schema Changes

### Table Renames
- `houses` → `homes`
- `devices` → `accessories`
- `entity_states` → (removed)
- `events` → (removed)

### Column Changes
- `house_id` → `home_id` (in all tables)
- `device_id` → `accessory_id` (in relationships)
- Removed `version` and `is_deleted` columns (no soft delete)

### New Tables
- `services` - Accessory capabilities
- `characteristics` - Service properties
- `accessory_rooms` - Many-to-many relationship

## CLI Command Changes

### Blowing-Off Client
- `blowing-off house` → `blowing-off home`
- Device commands still use `device` (not changed to `accessory` for user familiarity)

### Examples
```bash
# Old
blowing-off house create --name "My House" --address "123 Main St"

# New
blowing-off home create --name "My Home" --primary
```

## Sync Protocol Updates

The Inbetweenies sync protocol now uses:
- Entity type: `home` (singular) instead of `house`
- Entity type: `accessory` (singular) instead of `device`
- Simplified conflict resolution without version numbers

## Testing Updates

All tests have been updated to:
- Use new model names and imports
- Remove references to deleted fields
- Test with HomeKit-compatible data structures
- Handle lazy loading issues in async contexts

## Migration Notes

1. **No Backward Compatibility**: This is a breaking change. Old databases must be recreated.
2. **Import Changes**: All imports changed from `funkygibbon.models` to `inbetweenies.models`
3. **Repository Renames**: `HouseRepository` → `HomeRepository`, `DeviceRepository` → `AccessoryRepository`
4. **Field Removals**: Code relying on removed fields (address, timezone, email, etc.) must be updated

## Benefits

1. **iOS/macOS Compatibility**: Direct mapping to HomeKit framework classes
2. **Simplified Model**: Fewer fields, clearer purpose
3. **Shared Code**: Single source of truth for models
4. **Better Organization**: Service/Characteristic pattern matches HomeKit
5. **Reduced Complexity**: No soft delete, no version tracking

## Future Considerations

When implementing the Swift WildThing package:
- Models will map directly to HomeKit classes (HMHome, HMAccessory, etc.)
- No translation layer needed
- Sync protocol already uses correct entity types