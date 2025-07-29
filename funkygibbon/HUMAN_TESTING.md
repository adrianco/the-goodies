# 🏠 FunkyGibbon - Human Testing Guide

Welcome to the FunkyGibbon Smart Home API! This guide will help you quickly set up a populated database for manual testing and exploration.

## 🚀 Quick Start (Recommended)

### Option 1: Use the Population Script ✅ FIXED

The simplest and most reliable way to populate your database:

```bash
# From the funkygibbon directory
cd funkygibbon
python populate_db.py

# Start the server to explore the API with test data
python -m funkygibbon
```

This creates:
- 1 House (The Martinez Smart Home)
- 4 Rooms (Living Room, Kitchen, Master Bedroom, Home Office)
- 6 Devices (TV, Thermostat, Fridge, various lights)
- 3 Users (Carlos, Maria, Sofia)
- Device states for testing

### Option 2: Use End-to-End Tests

An alternative way to get a populated database:

```bash
# Run end-to-end tests which create comprehensive test data
python -m pytest tests/integration/test_end_to_end.py -v

# Start the server to explore the API with test data
python -m funkygibbon
```

## 🔧 Recent Fixes

Based on human testing feedback, the following issues have been resolved:

1. **Clear Working Directory Instructions**: The README now explicitly shows to run commands from the `funkygibbon` directory
2. **Working Database Population**: New `populate_db.py` script that reliably creates test data
3. **Duplicate Device/Room Handling**: API now returns proper 409 Conflict errors instead of 500 errors
4. **Improved Error Messages**: All creation endpoints now have descriptive error handling

## 📋 Available Test Scenarios

### 🏡 **Minimal Scenario**
Perfect for basic testing and API exploration.

**Contains:**
- **1 House**: "Test Smart Home" 
- **3 Rooms**: Living Room, Kitchen, Bedroom
- **3 Devices**: Basic lighting setup
- **1 User**: Test User (admin access)

**Use when:** Learning the API, basic functionality testing, quick demos

### 🌟 **Comprehensive Scenario** (Recommended)
Rich, realistic smart home environment for thorough testing.

**Contains:**
- **3 Houses**: 
  - "The Martinez Smart Home" (suburban family)
  - "Downtown Loft - Unit 4B" (urban apartment) 
  - "TechStart Inc. - Floor 12" (smart office)
- **10+ Rooms**: Realistic layouts with proper room types
- **25+ Devices**: Full ecosystem (lights, appliances, entertainment, security, climate)
- **8+ Users**: Different roles and access levels
- **Device States**: Realistic state history and current values
- **Rich Metadata**: Device specifications, room details, user preferences

**Use when:** Full feature testing, sync testing, multi-user scenarios, demonstrations

## 🔧 CLI Management (Advanced)

For more control over the database and server:

```bash
# Database Management
python cli.py seed --scenario comprehensive    # Populate database
python cli.py seed --scenario minimal         # Minimal data set
python cli.py clear-db                        # Clear all data
python cli.py seed --clear-first              # Clear then seed

# Server Management  
python cli.py serve --with-data               # Seed and start server
python cli.py serve --port 8080               # Custom port
python cli.py serve --reload                  # Development mode

# Testing
python cli.py test --with-data                # Seed database then run tests
python cli.py test tests/integration/         # Run specific tests

# Information
python cli.py info                            # Show system configuration
```

## 🌐 API Exploration

Once your server is running, explore these endpoints:

### 📚 **Documentation**
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

### 🏠 **Core Endpoints**

#### Houses
```bash
# List all houses
curl http://localhost:8000/api/v1/houses

# Get specific house with rooms
curl "http://localhost:8000/api/v1/houses/{house_id}?include_rooms=true"

# Create new house
curl -X POST "http://localhost:8000/api/v1/houses/" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Test House", "address": "123 Test St"}'
```

#### Rooms
```bash
# List all rooms
curl http://localhost:8000/api/v1/rooms

# Get rooms by house
curl "http://localhost:8000/api/v1/rooms?house_id={house_id}"

# Create room
curl -X POST "http://localhost:8000/api/v1/rooms/" \
  -H "Content-Type: application/json" \
  -d '{"house_id": "{house_id}", "name": "Test Room", "room_type": "office"}'
```

#### Devices
```bash
# List all devices
curl http://localhost:8000/api/v1/devices

# Get device with states
curl "http://localhost:8000/api/v1/devices/{device_id}?include_states=true"

# Update device state
curl -X PUT "http://localhost:8000/api/v1/devices/{device_id}/state" \
  -H "Content-Type: application/json" \
  -d '{"state_type": "on_off", "state_value": "on", "state_data": {"brightness": 80}}'
```

#### Sync (Advanced)
```bash
# Get changes since timestamp
curl "http://localhost:8000/api/v1/sync/changes?since=2025-01-01T00:00:00Z"

# Sync entities (test conflict resolution)
curl -X POST "http://localhost:8000/api/v1/sync/" \
  -H "Content-Type: application/json" \
  -d '{"houses": [...], "rooms": [...], "devices": [...], "users": [...]}'
```

## 🧪 Testing Scenarios

### 1. **Basic CRUD Operations**
- Create, read, update, delete houses, rooms, and devices
- Test validation and error handling
- Verify relationships between entities

### 2. **Device State Management**
- Update device states (lights on/off, thermostat temperature)
- View state history
- Test different device types and state formats

### 3. **Multi-User Testing**
- Test different user roles (admin, member, guest)
- Verify access controls and permissions
- Test user-specific operations

### 4. **Sync Functionality**
- Test bidirectional sync operations
- Create conflicts and verify resolution
- Test incremental sync with timestamps

### 5. **Real-World Scenarios**
- Family moving into new smart home
- Office building automation setup
- Apartment dweller adding smart devices
- Technician troubleshooting device issues

## 📊 Test Data Details & Layouts

### **Minimal Scenario Layout**

```
🏠 Test Smart Home (123 Developer Lane)
├── 👤 Users: Test User (admin)
└── 🏠 Floor Plan:
    ├── 🛏️ Bedroom (Floor 2)
    │   └── 💡 Bedside Lamp (light)
    ├── 🍳 Kitchen (Floor 1) 
    │   └── 💡 Kitchen Light (light)
    └── 🛋️ Living Room (Floor 1)
        └── 💡 Main Light (light)
```

### **Comprehensive Scenario Layouts**

#### 🏠 The Martinez Family Smart Home
**Location**: 456 Innovation Drive, Smart City, SC 90210  
**Timezone**: America/Los_Angeles

```
🏠 The Martinez Smart Home
├── 👤 Users:
│   ├── Carlos Martinez (admin) - carlos@martinez-family.com
│   ├── Maria Martinez (admin) - maria@martinez-family.com  
│   ├── Sofia Martinez (member) - sofia@martinez-family.com
│   └── Guest User (guest) - guest@martinez-family.com
│
└── 🏠 Floor Plan:
    ├── 🌳 Backyard (Floor 1) - 800 sq ft
    │   ├── 💡 Patio Lights (string lights, 50ft, weatherproof)
    │   ├── 💧 Garden Sprinklers (4 zones, weather sensor)
    │   └── 🔒 Security Floodlights (motion activated, 3000 lumens)
    │
    ├── 🚗 Garage (Floor 1) - 400 sq ft
    │   └── [Smart garage door opener - future expansion]
    │
    ├── 🛋️ Living Room (Floor 1) - 320 sq ft, 9ft ceiling
    │   ├── 📺 65" Smart TV (Samsung QN65Q90T, 4K, streaming apps)
    │   ├── 🔊 Sound System (Sonos Arc Soundbar, surround sound)
    │   ├── 💡 Main Ceiling Lights (LED, dimmable, color temp, 3 zones)
    │   ├── 💡 Table Lamps (smart bulbs, color changing, x2)
    │   ├── 🌡️ Smart Thermostat (Ecobee SmartThermostat, 3 sensors)
    │   └── 📹 Security Camera (indoor, 1080p, night vision)
    │
    ├── 🍳 Kitchen (Floor 1) - 200 sq ft, 9ft ceiling
    │   ├── ❄️ Smart Refrigerator (Samsung RF28R7351SG, Family Hub, 28 cu ft)
    │   ├── 🔥 Induction Cooktop (Bosch, 4 zones, power boost)
    │   ├── 💡 Under-Cabinet Lighting (LED strip, 8ft, dimmable)
    │   ├── 💡 Pendant Lights (smart bulbs x3, industrial style)
    │   └── 🔥 Smart Oven (GE Profile, convection, wifi)
    │
    ├── 🍽️ Dining Room (Floor 1) - 180 sq ft, 9ft ceiling
    │   └── [Chandelier - future expansion]
    │
    ├── 🛏️ Master Bedroom (Floor 2) - 250 sq ft, 8ft ceiling
    │   ├── 💡 Bedside Lamps (smart table lamps x2, touch control)
    │   ├── 🌀 Ceiling Fan (Hunter, smart control, light kit)
    │   ├── 🪟 Blackout Shades (Lutron motorized, light sensor)
    │   └── 🌬️ Air Purifier (Dyson Pure Cool, HEPA filter)
    │
    ├── 🚿 Master Bathroom (Floor 2) - 120 sq ft, 8ft ceiling
    │   └── [Smart mirror - future expansion]
    │
    ├── 🛏️ Guest Bedroom (Floor 2) - 180 sq ft, 8ft ceiling
    │   └── [Smart blinds - future expansion]
    │
    ├── 🚿 Guest Bathroom (Floor 2) - 60 sq ft, 8ft ceiling
    │   └── [Motion sensor lights - future expansion]
    │
    └── 💼 Home Office (Floor 2) - 150 sq ft, 8ft ceiling
        ├── 💡 Desk Lamp (LED, 10 brightness levels, color temp)
        ├── 🖥️ Smart Monitor (Dell 32", 4K, USB-C)
        └── 🌬️ Air Quality Monitor (Awair, CO2/VOC/PM2.5/humidity)
```

#### 🏢 Downtown Loft - Unit 4B
**Location**: 789 Urban Street, Apt 4B, Metro City, MC 12345  
**Timezone**: America/New_York

```
🏢 Downtown Loft - Unit 4B
├── 👤 Users:
│   └── Alex Chen (admin) - alex@example.com
│
└── 🏠 Compact Layout:
    ├── 🛋️ Living Area (Floor 1)
    │   ├── 📺 Smart TV (Samsung QN65Q80T, 4K streaming)
    │   └── 💡 Ceiling Light (LED, color temp control)
    │
    ├── 🍳 Kitchen (Floor 1)
    │   ├── 💡 Under-Cabinet Lights (LED strip, dimmable)
    │   └── ❄️ Smart Fridge (LG, smart features enabled)
    │
    ├── 🛏️ Bedroom (Floor 1)
    │   ├── 💡 Bedside Lamp (smart bulb, color changing)
    │   └── 🌡️ Smart Thermostat (Nest 3rd Gen)
    │
    └── 🚿 Bathroom (Floor 1)
        └── 💡 Vanity Light (LED, motion sensor)
```

#### 🏢 TechStart Inc. - Floor 12  
**Location**: 321 Business Plaza, Suite 1200, Corp City, CC 54321  
**Timezone**: America/Chicago

```
🏢 TechStart Inc. - Floor 12
├── 👤 Users:
│   ├── Sarah Johnson (admin) - sarah@techstart.com
│   ├── Mike Rodriguez (member) - mike@techstart.com
│   └── Facilities Manager (admin) - facilities@techstart.com
│
└── 🏢 Office Layout:
    ├── 🎯 Reception (Floor 1)
    │   └── 💡 Reception Lights (entrance zone)
    │
    ├── 📊 Conference Room A (Floor 1)
    │   ├── 📺 Presentation Display (4K monitor)
    │   └── 📹 Conference Camera (PTZ camera)
    │
    ├── 📊 Conference Room B (Floor 1)
    │   └── [AV equipment - future expansion]
    │
    ├── 💻 Open Workspace (Floor 1)
    │   └── 💡 Workspace Lighting (smart panels)
    │
    ├── 👔 CEO Office (Floor 1)
    │   └── [Executive desk setup - future expansion]
    │
    ├── ☕ Break Room (Floor 1)
    │   └── ☕ Coffee Machine (Jura, smart features)
    │
    └── 🖥️ Server Room (Floor 1)
        └── 🌡️ Temperature Monitor (environmental sensor)
```

### **Device State Examples**

Each device in the comprehensive scenarios includes realistic states and metadata:

```json
// Example: Living Room Smart TV
{
  "name": "65\" Smart TV",
  "device_type": "entertainment",
  "metadata": {
    "brand": "Samsung",
    "model": "QN65Q90T", 
    "resolution": "4K",
    "smart_features": ["Netflix", "Prime Video", "Disney+"]
  },
  "current_state": {
    "power": "on",
    "volume": 25,
    "input": "Netflix",
    "brightness": 80
  }
}

// Example: Smart Thermostat
{
  "name": "Smart Thermostat",
  "device_type": "climate",
  "metadata": {
    "brand": "Ecobee", 
    "model": "SmartThermostat",
    "sensors": 3
  },
  "current_state": {
    "target_temp": 72,
    "current_temp": 71,
    "mode": "heat",
    "humidity": 45
  }
}
```

## 🔍 Troubleshooting

### Database Issues
```bash
# Check system info
python cli.py info

# Clear and reseed if corrupted
python cli.py clear-db --confirm
python cli.py seed --scenario comprehensive

# Check database file (SQLite)
ls -la *.db
```

### Server Issues
```bash
# Test with different port
python cli.py serve --port 8080

# Check if port is busy
lsof -i :8000

# Restart with fresh data
python start.py comprehensive
```

### API Issues
```bash
# Test health endpoint
curl http://localhost:8000/health

# Check server logs for errors
# (Server outputs detailed logs to console)

# Verify data exists
curl http://localhost:8000/api/v1/houses | jq '.[0]'
```

## 💡 Pro Tips

1. **Use Swagger UI** at `/docs` for interactive API testing
2. **Check server logs** for detailed error information  
3. **Start with minimal scenario** to learn the API structure
4. **Use comprehensive scenario** for realistic testing
5. **Test sync functionality** with multiple "clients" using different timestamps
6. **Explore device metadata** for rich device information
7. **Test error conditions** with invalid data to verify API robustness

## 🤝 Feedback

Found issues or have suggestions for the test data? 
- The test scenarios are designed to be realistic and comprehensive
- Device states and metadata reflect real smart home setups
- User roles and permissions mirror typical smart home access patterns

Happy testing! 🎉