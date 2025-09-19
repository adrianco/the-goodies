# Standalone Chat Interface Plan

## Overview
Create a standalone chat interface that uses only blowing-off and inbetweenies as dependencies, without modifying these stable codebases. Focus on model comparison for simple text queries.

## Architecture

### 1. Minimal Dependencies
- **blowing-off**: Use as-is for MCP client functionality
- **inbetweenies**: Use for shared models and types
- **No changes** to funkygibbon, blowing-off, or inbetweenies

### 2. Chat Application Structure

```
chat/
├── models/                 # LLM model files (existing)
├── src/
│   ├── chat_interface.py  # Main chat application
│   ├── model_manager.py   # Handle multiple models
│   ├── query_processor.py # Process and route queries
│   └── response_logger.py # Log for comparison
├── tests/
│   ├── test_queries.json  # Standard test queries
│   ├── model_benchmark.py # Run comparisons
│   └── report_generator.py # Generate reports
├── results/
│   └── comparison_results.json
└── improved_chat.py       # Entry point
```

### 3. Core Components

#### Enhanced Chat Interface
```python
class ImprovedChatInterface:
    """Standalone chat interface using blowing-off client"""
    
    def __init__(self, model_path: str):
        self.model = self.load_model(model_path)
        self.client = BlowingOffClient()  # Use existing client
        self.query_processor = QueryProcessor()
        self.response_logger = ResponseLogger()
    
    async def process_query(self, query: str) -> dict:
        """Process query and return response with metadata"""
        # Parse query to identify intent
        intent = self.query_processor.analyze(query)
        
        # Get relevant data from blowing-off
        data = await self.client.execute_tool(intent.tool, intent.params)
        
        # Generate response
        response = self.model.generate(query, data)
        
        # Log for comparison
        self.response_logger.log(query, response, metadata)
        
        return response
```

#### Model Manager
```python
class ModelManager:
    """Manage multiple LLM models for comparison"""
    
    MODELS = {
        'mistral': 'models/mistral-7b-instruct-v0.2.Q4_K_M.gguf',
        'phi3': 'models/Phi-3-mini-4k-instruct-q4.gguf',
        'tinyllama': 'models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf'
    }
    
    def load_all_models(self):
        """Load all models for comparison"""
        return {name: Llama(path) for name, path in self.MODELS.items()}
    
    def compare_responses(self, query: str) -> dict:
        """Get responses from all models for comparison"""
        results = {}
        for name, model in self.models.items():
            results[name] = self.get_response(model, query)
        return results
```

### 4. Query Processing

#### Simple Query Categories
1. **Device Queries**: "Show me all lights", "Find smart thermostats"
2. **Room Queries**: "What's in the living room?", "List bedroom devices"
3. **Status Queries**: "Which devices are online?", "Show device states"
4. **Relationship Queries**: "What controls the garage door?", "Find connected devices"
5. **Search Queries**: "Find devices with 'smart' in name", "Search for sensors"

#### Query Intent Detection
```python
class QueryProcessor:
    """Process natural language queries to MCP tool calls"""
    
    QUERY_PATTERNS = {
        'list_devices': ['show', 'list', 'find', 'devices'],
        'room_query': ['room', 'in the', 'what\'s in'],
        'device_status': ['status', 'state', 'online', 'offline'],
        'search': ['search', 'find', 'look for']
    }
    
    def analyze(self, query: str) -> QueryIntent:
        """Analyze query and determine MCP tool to use"""
        query_lower = query.lower()
        
        # Match patterns to determine tool
        if 'room' in query_lower:
            return QueryIntent('get_devices_in_room', self.extract_room(query))
        elif 'search' in query_lower:
            return QueryIntent('search_entities', {'query': self.extract_search_term(query)})
        # ... more patterns
```

### 5. Test Framework

#### Test Query Set
```json
{
  "simple_queries": [
    {
      "id": "q1",
      "query": "List all smart lights",
      "expected_tool": "search_entities",
      "expected_params": {"query": "light", "entity_type": "DEVICE"}
    },
    {
      "id": "q2", 
      "query": "What devices are in the living room?",
      "expected_tool": "get_devices_in_room",
      "expected_params": {"room_id": "*living*"}
    },
    {
      "id": "q3",
      "query": "Find all temperature sensors",
      "expected_tool": "search_entities",
      "expected_params": {"query": "temperature sensor"}
    }
  ]
}
```

#### Model Comparison Metrics

1. **Response Quality**
   - Relevance (0-1): Does response answer the query?
   - Completeness (0-1): Are all requested items included?
   - Accuracy (0-1): Is information correct?

2. **Performance Metrics**
   - Response time (ms)
   - Tokens generated
   - Memory usage (MB)

3. **Tool Selection**
   - Correct tool chosen (boolean)
   - Parameters extracted correctly (boolean)
   - Fallback handling (graceful/error)

### 6. Implementation Phases

#### Phase 1: Core Chat Interface (Week 1)
- [ ] Create improved_chat.py with enhanced interface
- [ ] Implement QueryProcessor for intent detection
- [ ] Add ResponseLogger for tracking
- [ ] Test with single model

#### Phase 2: Model Comparison (Week 2)
- [ ] Implement ModelManager for multi-model support
- [ ] Create test query dataset
- [ ] Build comparison framework
- [ ] Generate initial results

#### Phase 3: Testing & Reporting (Week 3)
- [ ] Run comprehensive tests on all models
- [ ] Statistical analysis of results
- [ ] Generate comparison reports
- [ ] Create visualizations

### 7. Expected Outputs

#### Comparison Report Structure
```markdown
# Model Comparison Results

## Executive Summary
- Best overall: [Model]
- Fastest: [Model]  
- Most accurate: [Model]
- Most efficient: [Model]

## Detailed Results

### Query: "List all smart lights"

| Model | Response Time | Accuracy | Memory | Quality Score |
|-------|--------------|----------|--------|---------------|
| Mistral-7B | 1.2s | 95% | 4.1GB | 0.92 |
| Phi-3 | 0.8s | 88% | 2.3GB | 0.85 |
| TinyLlama | 0.3s | 72% | 0.6GB | 0.68 |

### Analysis
- Mistral provides most accurate responses but slower
- Phi-3 offers good balance of speed and accuracy
- TinyLlama fastest but less accurate for complex queries
```

### 8. Key Advantages

1. **No Dependency Changes**: Uses existing stable APIs
2. **Focused Scope**: Simple text queries only
3. **Quantitative Comparison**: Measurable metrics
4. **Reproducible**: Standard test set for consistency
5. **Extensible**: Easy to add new models or queries

### 9. Success Criteria

- [ ] Chat interface works with all three models
- [ ] Can process 20+ different query types
- [ ] Generates quantitative comparison metrics
- [ ] Produces readable comparison report
- [ ] No modifications to existing codebases
- [ ] All tests pass against funkygibbon data