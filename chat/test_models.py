#!/usr/bin/env python3
"""
Simple test script to verify all three models work
==================================================

Tests Mistral-7B, Phi-3, and TinyLlama models.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any
from llama_cpp import Llama


def test_model(model_name: str, model_path: str, test_queries: list) -> Dict[str, Any]:
    """Test a single model with sample queries"""
    print(f"\n{'='*50}")
    print(f"Testing: {model_name}")
    print(f"Model: {model_path}")
    print('='*50)

    # Check if model exists
    if not Path(model_path).exists():
        print(f"❌ Model file not found: {model_path}")
        return {'error': 'Model file not found'}

    model_size_mb = Path(model_path).stat().st_size / (1024 * 1024)
    print(f"Model size: {model_size_mb:.1f} MB")

    try:
        # Load model
        print("Loading model...")
        start_load = time.time()

        model = Llama(
            model_path=model_path,
            n_ctx=2048,  # Smaller context for testing
            n_threads=4,  # Use 4 threads
            n_gpu_layers=0,  # CPU only
            verbose=False
        )

        load_time = time.time() - start_load
        print(f"✅ Model loaded in {load_time:.2f} seconds")

        results = {
            'model': model_name,
            'load_time': load_time,
            'size_mb': model_size_mb,
            'queries': []
        }

        # Test each query
        for i, query in enumerate(test_queries, 1):
            print(f"\nQuery {i}: {query}")

            start_time = time.time()

            # Generate response
            response = model(
                f"User: {query}\nAssistant:",
                max_tokens=128,
                temperature=0.7,
                top_p=0.9,
                stop=["User:", "\n\n"]
            )

            response_time = (time.time() - start_time) * 1000  # Convert to ms
            response_text = response['choices'][0]['text'].strip()

            print(f"Response: {response_text[:100]}...")
            print(f"Time: {response_time:.1f}ms")
            print(f"Tokens: {response['usage']['completion_tokens']}")

            results['queries'].append({
                'query': query,
                'response': response_text,
                'time_ms': response_time,
                'tokens': response['usage']['completion_tokens']
            })

        # Calculate averages
        avg_time = sum(q['time_ms'] for q in results['queries']) / len(results['queries'])
        avg_tokens = sum(q['tokens'] for q in results['queries']) / len(results['queries'])

        results['avg_time_ms'] = avg_time
        results['avg_tokens'] = avg_tokens

        print(f"\n📊 Summary for {model_name}:")
        print(f"  Average response time: {avg_time:.1f}ms")
        print(f"  Average tokens: {avg_tokens:.1f}")

        # Clean up
        del model

        return results

    except Exception as e:
        print(f"❌ Error testing {model_name}: {e}")
        return {'error': str(e)}


def main():
    """Main test function"""
    print("🚀 LLM Model Testing Suite")
    print("Testing three models on CPU")

    # Define models
    models = {
        'tinyllama': 'chat/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf',
        'phi3': 'chat/models/Phi-3-mini-4k-instruct-q4.gguf',
        'mistral': 'chat/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf'
    }

    # Test queries
    test_queries = [
        "What is a smart home?",
        "List three benefits of home automation",
        "How do motion sensors work?",
        "What devices can control lights?",
        "Explain what a smart thermostat does"
    ]

    # Test each model
    all_results = {}

    for model_name, model_path in models.items():
        results = test_model(model_name, model_path, test_queries)
        all_results[model_name] = results

        # Small delay between models
        time.sleep(2)

    # Save results
    results_file = Path('chat/results/test_results.json')
    results_file.parent.mkdir(exist_ok=True)

    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\n\n{'='*50}")
    print("📋 FINAL COMPARISON")
    print('='*50)

    # Print comparison table
    print("\n| Model      | Load Time | Avg Response | Avg Tokens | Status |")
    print("|------------|-----------|--------------|------------|--------|")

    for model_name, results in all_results.items():
        if 'error' in results:
            print(f"| {model_name:10} | ERROR     | ERROR        | ERROR      | ❌     |")
        else:
            print(f"| {model_name:10} | {results['load_time']:6.2f}s   | "
                  f"{results['avg_time_ms']:9.1f}ms | {results['avg_tokens']:10.1f} | ✅     |")

    print(f"\n✅ Results saved to: {results_file}")

    # Determine best model for each metric
    successful_models = {k: v for k, v in all_results.items() if 'error' not in v}

    if successful_models:
        print("\n🏆 Winners:")

        # Fastest loading
        fastest_load = min(successful_models.items(), key=lambda x: x[1]['load_time'])
        print(f"  Fastest to load: {fastest_load[0]} ({fastest_load[1]['load_time']:.2f}s)")

        # Fastest response
        fastest_response = min(successful_models.items(), key=lambda x: x[1]['avg_time_ms'])
        print(f"  Fastest response: {fastest_response[0]} ({fastest_response[1]['avg_time_ms']:.1f}ms)")

        # Most efficient (smallest model that works)
        smallest = min(successful_models.items(), key=lambda x: x[1]['size_mb'])
        print(f"  Most efficient: {smallest[0]} ({smallest[1]['size_mb']:.1f}MB)")

    return all_results


if __name__ == "__main__":
    results = main()