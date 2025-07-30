# 🏠 FunkyGibbon - Human Testing Guide

A step-by-step guide to get FunkyGibbon running with test data for manual testing and API exploration.

## 📋 Prerequisites

- Python 3.11 or higher
- pip package manager
- curl (for testing API endpoints)

## 🚀 Quick Start Guide

Follow these steps in order:

### Step 1: Navigate to Project Root
```bash
cd /workspaces/the-goodies
pwd
# Should output: /workspaces/the-goodies
```

### Step 2: Set Up Virtual Environment (Recommended)
```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
source venv/bin/activate  # On Linux/Mac
# OR
venv\Scripts\activate     # On Windows

# You should see (venv) in your terminal prompt

# Set Python path to include project root (IMPORTANT!)
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH
```

### Step 3: Install Dependencies
```bash
cd funkygibbon
pip install -r requirements.txt
cd ..

# Also install blowing-off dependencies if testing the client
cd blowing-off
pip install -e .
cd ..
```

### Step 4: Populate the Database
```bash
# Run from project root - this is important!
python funkygibbon/populate_db.py
```

Expected output:
```
🏠 Creating test data for FunkyGibbon...
✅ Database populated successfully!

📊 Created:
  • 1 House (The Martinez Smart Home)
  • 4 Rooms (Living Room, Kitchen, Master Bedroom, Home Office)
  • 6 Devices (TV, Thermostat, Fridge, Lights)
  • 3 Users (Carlos, Maria, Sofia)
  • 3 Device States
```

### Step 5: Start the Server
```bash
# Also from project root
python -m funkygibbon
```

Expected output:
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
Database initialized
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Step 6: Test the API

Open a new terminal and run these commands:

#### Test Health Endpoint
```bash
curl http://localhost:8000/health
# Output: {"status":"healthy"}
```

#### List Homes (note the trailing slash!)
```bash
curl http://localhost:8000/api/v1/homes/
```

Expected output (formatted):
```json
[
    {
        "id": "home-xxxxx",
        "name": "The Martinez Smart Home",
        "is_primary": true,
        "created_at": "2025-07-29T12:00:00",
        "updated_at": "2025-07-29T12:00:00",
        "sync_id": "sync-xxxxx"
    }
]
```

#### List Rooms
```bash
curl http://localhost:8000/api/v1/rooms/
```

#### List Accessories
```bash
curl http://localhost:8000/api/v1/accessories/
```

#### List Users
```bash
curl http://localhost:8000/api/v1/users/
```

Expected output shows the three Martinez family members:
- Carlos Martinez (admin)
- Maria Martinez (admin)  
- Sofia Martinez (member)

### Step 7: Explore API Documentation

Visit http://localhost:8000/docs in your browser for interactive API documentation.

## ⚠️ Important Notes

1. **Working Directory**: Always run commands from `/workspaces/the-goodies` (project root)
2. **Python Path**: You MUST set `export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH` before running any commands
3. **Trailing Slashes**: Collection endpoints require trailing slashes (`/houses/` not `/houses`)
4. **Database Location**: The SQLite database file `funkygibbon.db` is created in the project root
5. **Room IDs**: Note that pre-populated rooms have IDs like `room-home-{home_id}-{index}` while newly created rooms have IDs like `room-{timestamp}`

## 🧪 Test Data Overview

The populate script creates:

### House
- **Name**: The Martinez Smart Home
- **Address**: 456 Innovation Drive, Smart City, SC 90210
- **Timezone**: America/Los_Angeles

### Rooms (4 total)
1. Living Room (Floor 1) - 2 devices
2. Kitchen (Floor 1) - 2 devices
3. Master Bedroom (Floor 2) - 1 device
4. Home Office (Floor 2) - 1 device

### Devices (6 total)
1. 65" Smart TV (Living Room)
2. Smart Thermostat (Living Room)
3. Smart Refrigerator (Kitchen)
4. Under-Cabinet Lights (Kitchen)
5. Bedside Lamps (Master Bedroom)
6. Desk Lamp (Home Office)

### Users (3 total)
1. Carlos Martinez (admin) - carlos@martinez-family.com
2. Maria Martinez (admin) - maria@martinez-family.com
3. Sofia Martinez (member) - sofia@martinez-family.com

## 🔧 Troubleshooting

### Virtual Environment Issues
```bash
# If commands are not found, ensure venv is activated:
which python
# Should show: /workspaces/the-goodies/venv/bin/python

# If not, activate it:
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate     # Windows
```

### Server won't start
```bash
# Check if port 8000 is already in use
lsof -i :8000

# Kill any existing FunkyGibbon processes
pkill -f "python -m funkygibbon"
```

### API returns 500 errors
```bash
# Delete and recreate the database
rm funkygibbon.db*
python funkygibbon/populate_db.py
python -m funkygibbon
```

### No data returned from API
- Make sure you're using trailing slashes on collection endpoints
- Verify the database was created in the project root: `ls -la funkygibbon.db`
- Add inbetweenies to Python path: `export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH`

## 📝 Additional Testing

All examples below have been tested and verified to work correctly.

### Create a New Room
```bash
# Get the home ID first
HOME_ID=$(curl -s http://localhost:8000/api/v1/homes/ | jq -r '.[0].id')

# Create a new room (using query parameters)
curl -X POST "http://localhost:8000/api/v1/rooms/?home_id=$HOME_ID&name=Guest%20Room"
```

### Create a New Accessory
```bash
# Get the home ID
HOME_ID=$(curl -s http://localhost:8000/api/v1/homes/ | jq -r '.[0].id')

# Create a new accessory (using JSON body)
curl -X POST "http://localhost:8000/api/v1/accessories/" \
  -H "Content-Type: application/json" \
  -d "{\"home_id\": \"$HOME_ID\", \"name\": \"Smart Speaker\", \"manufacturer\": \"Amazon\", \"model\": \"Echo\"}"
```

### Test Duplicate Handling (Should return 409)
```bash
# Try to create a room with the same name (will fail with 409)
curl -X POST "http://localhost:8000/api/v1/rooms/?home_id=$HOME_ID&name=Living%20Room"
```

## 🎯 Next Steps

- Explore the Swagger UI at http://localhost:8000/docs
- Test the sync endpoints at `/api/v1/sync/`
- Try the Blowing-Off client for testing synchronization
- Review the API implementation in `funkygibbon/api/routers/`

## 🌬️ Blowing-Off Client Testing

The Blowing-Off client provides a command-line interface for testing synchronization with FunkyGibbon.

### Prerequisites

- FunkyGibbon server running (see above)
- Python 3.11 or higher
- pip package manager

### Typical Workflow

1. **Set Python Path**: `export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH`
2. **Connect** to an existing FunkyGibbon server
3. **Sync** to download existing data from the server
4. **Work** with the synced data (view, create, update)
5. **Sync** again to push any local changes back to the server

### Installation

```bash
# Make sure virtual environment is activated
# If not: source venv/bin/activate  # On Windows: venv\Scripts\activate

# IMPORTANT: Set Python path first!
export PYTHONPATH=/workspaces/the-goodies:$PYTHONPATH

# From project root
cd blowing-off
pip install -e .
cd ..
```

### Basic Usage

#### 1. Connect to FunkyGibbon Server

```bash
# Configure connection to the server
blowing-off connect --server-url http://localhost:8000 --auth-token test-token
```

Expected output:
```
✅ Connected to FunkyGibbon server at http://localhost:8000
✅ Authentication successful
```

#### 2. Perform Initial Sync

```bash
# Sync to get existing data from the server
blowing-off sync
```

Expected output:
```
🔄 Starting sync with FunkyGibbon server...
📥 Fetching server changes...
✅ Received 1 house, 4 rooms, 6 devices from server
✅ Sync completed successfully!
```

#### 3. View Synchronized Data

```bash
# Show all homes (synced from server)
blowing-off home show
```

Expected output:
```
🏠 Home: The Martinez Smart Home
   ID: home-xxxxx
   Primary: Yes
```

```bash
# List all devices
blowing-off device list
```

Expected output:
```
📱 Devices:
┌──────────────┬─────────────────┬──────────────┬──────────────┐
│ Name         │ Type            │ Room         │ House        │
├──────────────┼─────────────────┼──────────────┼──────────────┤
│ 65" Smart TV │ entertainment   │ Living Room  │ The Marti... │
│ Smart Therm..│ climate         │ Living Room  │ The Marti... │
│ Smart Refr.. │ appliance       │ Kitchen      │ The Marti... │
│ Under-Cabi.. │ light           │ Kitchen      │ The Marti... │
│ Bedside La.. │ light           │ Master Bed.. │ The Marti... │
│ Desk Lamp    │ light           │ Home Office  │ The Marti... │
└──────────────┴─────────────────┴──────────────┴──────────────┘
```

### Advanced Testing

#### Working with Existing Server Data

When connected to a pre-populated server, you'll work with the existing house data:

```bash
# First, get the house ID from the synced data
blowing-off house show
# Note the house ID (e.g., house-1753811634.34222)

# Create a new room in the existing house
HOUSE_ID="house-xxxxx"  # Replace with actual ID from above
blowing-off room create --house-id $HOUSE_ID --name "Test Room" --floor 1

# Sync to push the new room to the server
blowing-off sync

# Verify the room exists on both client and server
blowing-off room list
```

#### Creating a New Local House (Separate from Server Data)

If you want to test with a completely new house:

```bash
# Create a new house locally
blowing-off house create --name "My Test House" --address "789 Local St" --timezone "America/New_York"

# This house will be synced to the server on next sync
blowing-off sync

# Now you'll see both houses
blowing-off house show
```

#### Test Device Creation and Control

```bash
# Get a room ID from existing data
blowing-off room list
# Note a room ID (e.g., living-room-xxxxx)

# Create a device in an existing room
ROOM_ID="room-xxxxx"  # Replace with actual ID
blowing-off device create --room-id $ROOM_ID --name "Test Light" --type light

# Control the device
blowing-off device show  # Get the new device ID
DEVICE_ID="device-xxxxx"  # Replace with actual ID
blowing-off device control $DEVICE_ID --state '{"power": "on", "brightness": 80}'

# Sync changes to server
blowing-off sync
```

### Troubleshooting Blowing-Off

#### Connection Issues
```bash
# Check current connection status
blowing-off status

# Reset connection
blowing-off disconnect
blowing-off connect --server-url http://localhost:8000 --auth-token test-token
```

#### Database Location
The client database is stored at: `blowingoff.db` (in the current directory)

```bash
# To reset the client database and start fresh
rm -f blowingoff.db*

# Then reconnect to the server
blowing-off connect --server-url http://localhost:8000 --auth-token test-token

# Sync to download existing data from the server
blowing-off sync
```

#### Sync Conflicts
The system uses last-write-wins conflict resolution. If you see unexpected data after sync:
1. Check the timestamps on both client and server
2. The most recent change wins
3. Use `--force` flag to override: `blowing-off sync --force`

### CLI Command Reference

```bash
# House commands
blowing-off house create --name NAME [--address ADDR] [--timezone TZ]
blowing-off house show
blowing-off house update HOUSE_ID --name NEW_NAME

# Room commands
blowing-off room create --house-id ID --name NAME [--floor N] [--type TYPE]
blowing-off room list [--house-id ID]
blowing-off room update ROOM_ID --name NEW_NAME

# Device commands
blowing-off device create --room-id ID --name NAME --type TYPE
blowing-off device list [--room-id ID]
blowing-off device show DEVICE_ID
blowing-off device control DEVICE_ID --state JSON
blowing-off device delete DEVICE_ID

# User commands
blowing-off user create --house-id ID --name NAME --email EMAIL [--role ROLE]
blowing-off user list

# Sync commands
blowing-off sync [--force]
blowing-off status

# Connection commands
blowing-off connect --server-url URL --auth-token TOKEN
blowing-off disconnect
```

## 🔄 Cleaning Up

When you're done testing:

```bash
# Stop the FunkyGibbon server
# Press Ctrl+C in the terminal running the server

# Deactivate the virtual environment
deactivate

# Optional: Remove the virtual environment
rm -rf venv

# Optional: Clean up databases
rm -f funkygibbon.db*
rm -f blowingoff.db*
rm -f .blowingoff.json
```

Happy testing! 🎉