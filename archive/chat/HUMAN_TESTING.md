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

## BDD Testing

### What is BDD (Behavior-Driven Development)?

BDD is a testing methodology that focuses on describing the behavior of software from the user's perspective. It bridges the gap between technical and non-technical team members by using natural language to describe test scenarios.

#### Key Concepts:

**Given-When-Then Structure:**
- **GIVEN**: The initial context or state (preconditions)
- **WHEN**: An action or event occurs
- **THEN**: The expected outcome or behavior

**Example BDD Test:**
```python
@pytest.mark.asyncio
async def test_list_all_rooms(self):
    """
    GIVEN a smart home with 6 rooms
    WHEN user asks to list all rooms
    THEN chat should return all room names with their types
    """
```

#### Benefits of BDD Testing:
1. **Clear Communication**: Tests are written in plain language that everyone understands
2. **User-Focused**: Tests describe actual user scenarios and expected behaviors
3. **Living Documentation**: Tests serve as executable documentation of system behavior
4. **Early Bug Detection**: Behavioral issues are caught before they reach production
5. **Regression Prevention**: Ensures new changes don't break existing functionality

#### BDD vs Traditional Testing:

**Traditional Unit Test:**
```python
def test_search_entities():
    result = search_entities("room")
    assert len(result) == 6
    assert result[0]["entity_type"] == "ROOM"
```

**BDD Test:**
```python
"""
GIVEN a smart home with multiple rooms
WHEN user searches for rooms
THEN the system should return all available rooms with their details
"""
```

The BDD approach is more readable and focuses on the **why** and **what** rather than just the **how**.

### BDD Test Organization in This Project

Our BDD tests are organized into logical test classes that represent different aspects of the chat interface:

1. **TestRoomQueries**: Tests related to querying and listing rooms
2. **TestDeviceQueries**: Tests for device discovery and information
3. **TestRoomDeviceRelationships**: Tests for relationships between rooms and devices
4. **TestAutomationQueries**: Tests for automation and scene queries
5. **TestComplexQueries**: Tests for multi-entity and complex queries
6. **TestErrorHandling**: Tests for handling invalid queries and errors
7. **TestNaturalLanguageParsing**: Tests for query interpretation

Each test follows the Given-When-Then pattern and includes:
- **Docstring**: Describes the scenario in natural language
- **Setup (Given)**: Prepares test data and initial state
- **Action (When)**: Executes the user query or action
- **Assertion (Then)**: Verifies the expected behavior

### Running BDD Tests with Mock Data
The default BDD tests use mock data for fast, reliable testing:
```bash
# Run all BDD tests with mock data
pytest chat/test_bdd_chat.py -v

# Run specific test class
pytest chat/test_bdd_chat.py::TestRoomQueries -v

# Run single test
pytest chat/test_bdd_chat.py::TestRoomQueries::test_list_all_rooms -v
```

### Running BDD Tests Against Real Server
You can run the same BDD tests against the actual running chat application:

#### Prerequisites
1. FunkyGibbon server must be running:
```bash
./start_funkygibbon.sh
```

2. Server must have test data loaded:
```bash
cd funkygibbon && python populate_graph_db.py && cd ..
```

#### Integration Test Commands

**Option 1: Dedicated Integration Tests**
```bash
# Run integration tests against real server
pytest chat/test_bdd_integration.py -v -m integration

# Run specific integration test
pytest chat/test_bdd_integration.py::TestRoomQueriesIntegration::test_list_all_rooms -v

# Run with custom server URL
pytest chat/test_bdd_integration.py -v -m integration --server-url http://localhost:8000 --server-password admin
```

**Option 2: Hybrid Tests (Mock or Real)**
```bash
# Run with mock data (default)
pytest chat/test_bdd_hybrid.py -v

# Run against real server with --integration flag
pytest chat/test_bdd_hybrid.py -v --integration

# Run specific test against real server
pytest chat/test_bdd_hybrid.py::TestRoomQueries::test_list_all_rooms -v --integration

# Direct execution with arguments
python chat/test_bdd_hybrid.py --integration --verbose
```

### Writing Your Own BDD Tests

To add new BDD test scenarios for the chat interface:

```python
import pytest
from unittest.mock import AsyncMock

class TestYourFeature:
    """Test class for your feature area"""

    @pytest.mark.asyncio
    async def test_your_scenario(self, chat_instance):
        """
        GIVEN [initial context/state]
        WHEN [action occurs]
        THEN [expected outcome]
        """
        # Given - Setup test data
        chat = chat_instance
        mock_data = {
            'success': True,
            'result': {'results': [...]}
        }
        chat.client.execute_mcp_tool.return_value = mock_data

        # When - Execute the action
        response = await chat.process_query("your test query")

        # Then - Verify the outcome
        assert response is not None
        assert "expected text" in response.lower()
        chat.client.execute_mcp_tool.assert_called_with(
            "expected_tool",
            expected_param="value"
        )
```

**Best Practices for BDD Tests:**
1. Keep scenarios focused on one behavior
2. Use descriptive test names that explain the scenario
3. Make assertions clear and specific
4. Test both happy paths and error cases
5. Group related tests in the same class

#### Test Coverage

The BDD test suites cover:
- **Room Queries**: List rooms, search specific rooms, room connections
- **Device Queries**: List devices, search lights, device capabilities
- **Room-Device Relationships**: Devices in specific rooms
- **Automation Queries**: List automations, room automations
- **MCP Tool Testing**: Direct tool execution validation
- **Natural Language Parsing**: Query interpretation
- **Error Handling**: Invalid queries and tool errors

#### Integration Test Features

1. **Server Health Check**: Tests skip if server is unavailable
2. **Real Data Validation**: Tests adapt to actual database content
3. **MCP Tool Verification**: Validates all 12 MCP tools work correctly
4. **Flexible Configuration**: Supports custom server URLs and passwords
5. **Hybrid Mode**: Same tests can run with mock or real data

#### Expected Integration Test Output

```
$ pytest chat/test_bdd_integration.py -v --integration
============================= test session starts ==============================
collecting ... collected 17 items

chat/test_bdd_integration.py::TestRoomQueriesIntegration::test_list_all_rooms PASSED
chat/test_bdd_integration.py::TestRoomQueriesIntegration::test_search_specific_room PASSED
chat/test_bdd_integration.py::TestRoomQueriesIntegration::test_get_room_connections PASSED
chat/test_bdd_integration.py::TestDeviceQueriesIntegration::test_list_all_devices PASSED
chat/test_bdd_integration.py::TestDeviceQueriesIntegration::test_search_lights PASSED
chat/test_bdd_integration.py::TestDeviceQueriesIntegration::test_find_device_controls PASSED
...
============================== 17 passed in 3.45s ==============================
```

### Understanding BDD Test Results

#### Successful Test Output:
```
chat/test_bdd_chat.py::TestRoomQueries::test_list_all_rooms PASSED       [  5%]
```
- **Test File**: `test_bdd_chat.py`
- **Test Class**: `TestRoomQueries` (grouping related tests)
- **Test Method**: `test_list_all_rooms` (specific scenario)
- **Result**: `PASSED` (behavior matches expectation)
- **Progress**: `[5%]` (percentage of tests completed)

#### Failed Test Output:
```
FAILED chat/test_bdd_chat.py::TestRoomQueries::test_list_all_rooms
    assert 'living' in response.lower()
    AssertionError: assert 'living' in 'no rooms found'
```
This tells you:
- The test scenario that failed
- The specific assertion that didn't pass
- The actual vs expected values

#### Test Summary:
```
============================== 19 passed in 1.20s ==============================
```
- Total tests run: 19
- All passed (green)
- Execution time: 1.20 seconds

#### Troubleshooting Integration Tests

**Issue: Tests skipped with "FunkyGibbon server not available"**
- Ensure server is running: `./start_funkygibbon.sh`
- Check server health: `curl http://localhost:8000/health`
- Verify password: Default is "admin" in dev mode

**Issue: Tests fail with empty results**
- Load test data: `cd funkygibbon && python populate_graph_db.py`
- Verify data exists: `oook stats`

**Issue: Connection refused errors**
- Check server port: Default is 8000
- Verify no firewall blocking localhost connections
- Try explicit URL: `--server-url http://127.0.0.1:8000`

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