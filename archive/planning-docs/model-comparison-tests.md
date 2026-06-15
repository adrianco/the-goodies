# Model Comparison Test Design

## Test Categories for LLM Evaluation

### 1. Query Understanding Tests

#### Simple Entity Queries
```python
SIMPLE_QUERIES = [
    "Show all devices",
    "List rooms",
    "Find lights",
    "Show thermostats",
    "List smart locks"
]
```

#### Room-Based Queries  
```python
ROOM_QUERIES = [
    "What's in the living room?",
    "Show bedroom devices",
    "List kitchen appliances",
    "Find garage equipment",
    "What's in the master bedroom?"
]
```

#### Search Queries
```python
SEARCH_QUERIES = [
    "Find devices with 'smart' in the name",
    "Search for temperature sensors",
    "Look for motion detectors",
    "Find all Philips devices",
    "Search for devices installed in 2024"
]
```

#### Relationship Queries
```python
RELATIONSHIP_QUERIES = [
    "What controls the garage door?",
    "Which hub manages the lights?",
    "Find devices connected to the router",
    "What's controlled by the smart hub?",
    "Show device dependencies"
]
```

### 2. Evaluation Metrics

#### A. Response Quality Metrics

```python
class ResponseQualityMetrics:
    """Evaluate response quality across models"""
    
    def evaluate_relevance(self, query: str, response: str) -> float:
        """Score 0-1: Does response address the query?"""
        keywords = self.extract_keywords(query)
        matches = sum(1 for k in keywords if k in response.lower())
        return matches / len(keywords) if keywords else 0
    
    def evaluate_completeness(self, expected_items: list, response: str) -> float:
        """Score 0-1: Are all expected items mentioned?"""
        found = sum(1 for item in expected_items if item in response)
        return found / len(expected_items) if expected_items else 0
    
    def evaluate_accuracy(self, ground_truth: dict, response: str) -> float:
        """Score 0-1: Is the information factually correct?"""
        # Check against known data from funkygibbon
        correct_facts = 0
        total_facts = 0
        
        for fact, value in ground_truth.items():
            total_facts += 1
            if str(value) in response:
                correct_facts += 1
        
        return correct_facts / total_facts if total_facts else 0
```

#### B. Performance Metrics

```python
class PerformanceMetrics:
    """Measure model performance characteristics"""
    
    def measure_response_time(self, model, query: str) -> dict:
        """Measure timing metrics"""
        start = time.time()
        
        # Time to first token
        first_token_time = None
        tokens = []
        
        for token in model.generate_stream(query):
            if first_token_time is None:
                first_token_time = time.time() - start
            tokens.append(token)
        
        total_time = time.time() - start
        
        return {
            'first_token_ms': first_token_time * 1000,
            'total_time_ms': total_time * 1000,
            'tokens_per_second': len(tokens) / total_time,
            'total_tokens': len(tokens)
        }
    
    def measure_memory_usage(self, model) -> dict:
        """Track memory consumption"""
        import psutil
        process = psutil.Process()
        
        return {
            'memory_mb': process.memory_info().rss / 1024 / 1024,
            'cpu_percent': process.cpu_percent()
        }
```

### 3. Test Execution Framework

```python
class ModelComparisonTest:
    """Run comparison tests across all models"""
    
    def __init__(self):
        self.models = {
            'mistral-7b': 'models/mistral-7b-instruct-v0.2.Q4_K_M.gguf',
            'phi-3': 'models/Phi-3-mini-4k-instruct-q4.gguf',
            'tinyllama': 'models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf'
        }
        self.results = {}
        
    async def run_test_suite(self):
        """Execute all tests on all models"""
        
        for model_name, model_path in self.models.items():
            print(f"\n=== Testing {model_name} ===")
            model = self.load_model(model_path)
            
            self.results[model_name] = {
                'simple_queries': await self.test_simple_queries(model),
                'room_queries': await self.test_room_queries(model),
                'search_queries': await self.test_search_queries(model),
                'relationship_queries': await self.test_relationship_queries(model),
                'performance': self.test_performance(model),
                'resource_usage': self.test_resource_usage(model)
            }
    
    async def test_simple_queries(self, model) -> dict:
        """Test simple entity queries"""
        results = []
        
        for query in SIMPLE_QUERIES:
            response = await self.get_response(model, query)
            
            results.append({
                'query': query,
                'response': response.text,
                'relevance': self.evaluate_relevance(query, response.text),
                'time_ms': response.time_ms,
                'tokens': response.token_count
            })
        
        return {
            'queries': results,
            'avg_relevance': sum(r['relevance'] for r in results) / len(results),
            'avg_time_ms': sum(r['time_ms'] for r in results) / len(results)
        }
```

### 4. Test Data Generation

```python
class TestDataGenerator:
    """Generate test data from funkygibbon database"""
    
    def __init__(self, db_path='funkygibbon.db'):
        self.db_path = db_path
        self.test_data = self.load_test_data()
    
    def generate_ground_truth(self) -> dict:
        """Create ground truth for validation"""
        return {
            'total_devices': 47,
            'total_rooms': 12,
            'device_types': ['light', 'thermostat', 'lock', 'camera', 'sensor'],
            'rooms': {
                'living_room': ['smart_tv', 'ceiling_light', 'thermostat'],
                'master_bedroom': ['bedside_lamp', 'ceiling_fan', 'smart_blinds'],
                'kitchen': ['smart_fridge', 'dishwasher', 'coffee_maker']
            },
            'relationships': {
                'zigbee_hub': ['bedroom_light', 'kitchen_light', 'bathroom_light'],
                'security_system': ['front_door_lock', 'garage_door', 'motion_sensors']
            }
        }
```

### 5. Scoring System

```python
class ScoringSystem:
    """Score and rank models based on test results"""
    
    WEIGHTS = {
        'relevance': 0.30,
        'accuracy': 0.25,
        'speed': 0.20,
        'completeness': 0.15,
        'efficiency': 0.10
    }
    
    def calculate_overall_score(self, model_results: dict) -> float:
        """Calculate weighted overall score for a model"""
        scores = {
            'relevance': model_results['avg_relevance'],
            'accuracy': model_results['avg_accuracy'],
            'speed': self.normalize_speed(model_results['avg_time_ms']),
            'completeness': model_results['avg_completeness'],
            'efficiency': self.calculate_efficiency(model_results)
        }
        
        overall = sum(score * self.WEIGHTS[metric] 
                     for metric, score in scores.items())
        return overall
    
    def normalize_speed(self, time_ms: float) -> float:
        """Normalize speed score (faster is better)"""
        # Assume 5000ms is slow, 500ms is fast
        if time_ms <= 500:
            return 1.0
        elif time_ms >= 5000:
            return 0.0
        else:
            return 1.0 - ((time_ms - 500) / 4500)
    
    def calculate_efficiency(self, results: dict) -> float:
        """Calculate efficiency (accuracy per resource)"""
        accuracy = results['avg_accuracy']
        memory_gb = results['memory_usage'] / 1024
        return accuracy / (1 + memory_gb)  # Higher accuracy with less memory
```

### 6. Test Report Template

```markdown
# LLM Model Comparison Report

## Test Configuration
- Date: [DATE]
- Test Dataset: FunkyGibbon Smart Home Data
- Query Count: 50 queries across 5 categories
- Models Tested: Mistral-7B, Phi-3, TinyLlama

## Summary Results

| Model | Overall Score | Best Category | Weakest Category | Avg Response Time |
|-------|--------------|---------------|------------------|-------------------|
| Mistral-7B | 0.89 | Relationships | Speed | 1823ms |
| Phi-3 | 0.82 | Room Queries | Search | 967ms |
| TinyLlama | 0.71 | Speed | Accuracy | 412ms |

## Detailed Analysis

### Query Understanding
- **Mistral-7B**: Excellent comprehension, handles complex queries well
- **Phi-3**: Good balance, occasionally misses nuanced requests  
- **TinyLlama**: Basic understanding, struggles with multi-part queries

### Response Quality
[Charts showing relevance, completeness, accuracy scores]

### Performance Characteristics
[Charts showing response time, memory usage, tokens/second]

### Recommendations
- **For Production**: Mistral-7B (highest accuracy)
- **For Development**: Phi-3 (good balance)
- **For Edge Devices**: TinyLlama (lowest resource usage)

## Raw Test Results
[Detailed table with all test queries and responses]
```

### 7. Implementation Code Structure

```python
# chat/tests/model_benchmark.py

import asyncio
import json
from typing import Dict, List
from pathlib import Path

from llama_cpp import Llama
import sys
sys.path.append('../')
from blowing_off import BlowingOffClient

class ModelBenchmark:
    """Complete model comparison benchmark suite"""
    
    def __init__(self, output_dir: Path = Path('results')):
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
        
        # Initialize components
        self.models = self.load_models()
        self.test_queries = self.load_test_queries()
        self.client = BlowingOffClient()
        self.metrics = ResponseQualityMetrics()
        self.performance = PerformanceMetrics()
        self.scorer = ScoringSystem()
        
    async def run_complete_benchmark(self):
        """Run full benchmark suite"""
        print("🚀 Starting Model Comparison Benchmark")
        print("=" * 50)
        
        results = {}
        
        for model_name, model in self.models.items():
            print(f"\n📊 Testing {model_name}...")
            results[model_name] = await self.benchmark_model(model, model_name)
            
        # Calculate scores
        for model_name in results:
            results[model_name]['overall_score'] = \
                self.scorer.calculate_overall_score(results[model_name])
        
        # Save results
        self.save_results(results)
        
        # Generate report
        self.generate_report(results)
        
        print("\n✅ Benchmark Complete!")
        return results
        
    async def benchmark_model(self, model, model_name: str) -> dict:
        """Benchmark a single model"""
        results = {
            'model': model_name,
            'test_results': [],
            'performance_metrics': {},
            'quality_scores': {}
        }
        
        for category, queries in self.test_queries.items():
            print(f"  Testing {category}...")
            category_results = []
            
            for query in queries:
                # Get model response
                response = await self.get_model_response(model, query['query'])
                
                # Evaluate response
                evaluation = self.evaluate_response(
                    query, 
                    response,
                    model_name
                )
                
                category_results.append(evaluation)
            
            results['test_results'].append({
                'category': category,
                'queries': category_results
            })
        
        # Calculate aggregates
        results['quality_scores'] = self.calculate_quality_scores(results)
        results['performance_metrics'] = self.calculate_performance_metrics(results)
        
        return results

if __name__ == "__main__":
    benchmark = ModelBenchmark()
    results = asyncio.run(benchmark.run_complete_benchmark())
    print(f"\n📈 Results saved to {benchmark.output_dir}")
```