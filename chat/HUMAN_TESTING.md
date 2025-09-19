# TinyLlama MCP Chat - Human Testing Guide

This guide will walk you through setting up and testing the TinyLlama chat interface with MCP (Model Context Protocol) tools for smart home knowledge graph queries.

## Prerequisites

### System Requirements
- Python 3.9+
- At least 4GB RAM (TinyLlama model uses ~700MB when loaded)
- 2GB disk space for models
- CPU-based inference (no GPU required)

### Required Models
The TinyLlama model should be downloaded to the `chat/models/` directory:
```
chat/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
```

If you don't have the model, download it from:
https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF

## Installation Steps

### 1. Install Dependencies

First, ensure you're in the project root directory:
```bash
cd /workspaces/the-goodies
```

Install the required packages:
```bash
# Install llama-cpp-python for model loading
pip install llama-cpp-python==0.2.90

# Install The Goodies packages
pip install -e inbetweenies/
pip install -e blowing-off/
```

### 2. Start the FunkyGibbon Server

The chat interface needs the FunkyGibbon server running to sync data:

```bash
# Use the provided start script
./start_funkygibbon.sh
```

Expected output:
```
🚀 Starting FunkyGibbon MCP Server...
📂 Creating database directory if needed...
🔑 Using development mode (empty password)...
🌐 Starting server on http://localhost:8000...
INFO:     Started server process [19753]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Keep this running in a separate terminal.

### 3. Run the Chat Interface

In a new terminal, start the TinyLlama MCP chat:

```bash
cd /workspaces/the-goodies
python -m chat.tinyllama_mcp_chat
```

## Expected Output

### Initialization Phase
```
🚀 Initializing TinyLlama MCP Chat...
📦 Loading TinyLlama model...
✅ Model loaded
🔌 Connecting to blowing-off client...
✅ Connected to server
🔄 Syncing data from funkygibbon...
DEBUG: Applying change for entity 16a120d7-166c-4dfe-9ff6-1e36ce1926e2: ...
DEBUG: Applying change for entity debe9463-55a8-4dab-a147-923a074541b7: ...
[... more sync messages ...]
✅ Data synced successfully
🛠️ 9 MCP tools available

==================================================
🏠 Smart Home Chat with MCP Tools
==================================================
Using TinyLlama model with blowing-off MCP integration
Type 'quit' to exit, 'tools' to list available tools

You:
```

### Available Commands

Type these commands in the chat interface:

#### `tools` - List Available MCP Tools
```
You: tools

🛠️ Available MCP Tools:
  - search_entities: Search for entities by query
  - list_entities: List all entities
  - get_devices_in_room: Get devices in a specific room
  - find_device_controls: Find what controls a device
  - find_similar_entities: Find entities similar to a given one
  - get_automations_in_room: Get automations for a room
  - get_procedures_for_device: Get procedures for a device
  - get_room_connections: Get connections between rooms
  - find_path: Find path between locations
```

#### `help` - Show Example Queries
```
You: help

📖 Example queries:
  - List all devices
  - Search for lights
  - What devices are in the living room?
  - Find temperature sensors
  - Show all rooms
```

## Example Test Queries

### Query 1: List All Devices
```
You: List all devices

💭 Processing: List all devices
  🔧 Executing: search_entities({'query': 'device'})
Assistant: I found several smart devices in the system including the TV, Thermostat, Smart Fridge, Smart Oven, Lights, and other connected devices that help automate your home.
```

### Query 2: Search for Lights
```
You: Search for lights

💭 Processing: Search for lights
  🔧 Executing: search_entities({'query': 'lights'})
Assistant: I found Living Room Lights in the system. They are Philips Hue Go smart lights with capabilities for power control, brightness adjustment, color changing, and scene settings.
```

### Query 3: List Rooms
```
You: list rooms

💭 Processing: list rooms
  🔧 Executing: search_entities({'query': 'room'})
Assistant: The smart home has several rooms including Living Room, Kitchen, Dining Room, Master Bedroom, Office, and Garage areas for smart device control.
```

## Available Entity Types

The system contains these entity types that can be queried:
- **HOME** - The main home entity
- **ROOM** - Living Room, Kitchen, Dining Room, Master Bedroom, Office, Garage
- **DEVICE** - TV, Thermostat, Smart Fridge, Smart Oven, Lights, Doorbell, HVAC
- **PROCEDURE** - Setup and configuration procedures
- **MANUAL** - Device manuals and documentation
- **AUTOMATION** - Morning routine, Movie time
- **SCHEDULE** - Vacation mode settings
- **NOTE** - WiFi passwords, maintenance notes
- **APP** - HomeKit, Mitsubishi Comfort

## Troubleshooting

### Issue: Model not found
```
❌ Model not found: chat/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
```
**Solution**: Download the model from HuggingFace and place it in the `chat/models/` directory.

### Issue: Connection refused
```
❌ Error: Cannot connect to server at http://localhost:8000
```
**Solution**: Make sure the FunkyGibbon server is running with `./start_funkygibbon.sh`.

### Issue: Import errors
```
ModuleNotFoundError: No module named 'blowingoff'
```
**Solution**: Install the packages with pip:
```bash
pip install -e inbetweenies/
pip install -e blowing-off/
```

### Issue: Slow responses
The TinyLlama model runs on CPU and may take 1-3 seconds per response depending on your system. This is normal for CPU inference.

## Performance Notes

- **Model Load Time**: ~2-3 seconds
- **Response Time**: 1-3 seconds per query
- **Memory Usage**: ~700MB when model is loaded
- **Token Generation**: ~10-20 tokens/second on CPU

## Advanced Testing

### Test Script
Run the automated test script to verify everything works:
```bash
python chat/test_mcp_chat.py
```

### Demo Script
Run the demo script for sample queries:
```bash
python chat/demo_test.py
```

### Model Comparison
Compare TinyLlama with Phi-3 (if available):
```bash
python chat/compare_models.py
```

## API Integration

The chat interface uses the blowing-off client to execute MCP tools. The flow is:

1. Natural language query → Pattern matching
2. Pattern → MCP tool selection
3. Tool execution via `execute_mcp_tool()`
4. Results → Context for TinyLlama
5. TinyLlama generates natural response

## Data Synced from FunkyGibbon

The system syncs 33 entities including:
- 1 HOME entity (Martinez Residence)
- 6 ROOM entities
- 8 DEVICE entities
- 2 PROCEDURE entities
- 1 MANUAL entity
- 2 AUTOMATION entities
- 1 SCHEDULE entity
- 2 NOTE entities
- 2 APP entities
- Additional relationships and documentation

## Future Enhancements

- [ ] Add support for Phi-3 model comparison
- [ ] Implement voice input/output
- [ ] Add web interface
- [ ] Support for more MCP tools
- [ ] Better context management for longer conversations
- [ ] Swift implementation for iPhone deployment

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the main README.md in the project root
3. Check the funkygibbon and blowing-off test suites
4. File an issue on GitHub

---

Happy testing! 🚀