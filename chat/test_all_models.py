#!/usr/bin/env python3
"""Test all three models individually"""

import json
import time
from pathlib import Path
from llama_cpp import Llama

def test_single_model(model_name: str, model_path: str, context_size: int = 512):
    """Test a single model with minimal settings"""
    print(f"\n{'='*50}")
    print(f"Testing: {model_name}")

    if not Path(model_path).exists():
        print(f"❌ Model not found: {model_path}")
        return {'error': 'Model not found'}

    size_mb = Path(model_path).stat().st_size / (1024*1024)
    print(f"Model size: {size_mb:.1f} MB")

    try:
        # Load model
        print("Loading...")
        start = time.time()

        model = Llama(
            model_path=model_path,
            n_ctx=context_size,
            n_threads=2,
            n_gpu_layers=0,
            verbose=False
        )

        load_time = time.time() - start
        print(f"✅ Loaded in {load_time:.1f}s")

        # Test queries
        queries = [
            "What is a smart home?",
            "Name three smart devices",
            "What is home automation?"
        ]

        results = {
            'model': model_name,
            'size_mb': size_mb,
            'load_time': load_time,
            'queries': []
        }

        for query in queries:
            print(f"\nQuery: {query}")
            start = time.time()

            response = model(
                f"User: {query}\nAssistant:",
                max_tokens=50,
                temperature=0.7,
                stop=["User:", "\n\n"]
            )

            response_time = (time.time() - start) * 1000
            text = response['choices'][0]['text'].strip()

            print(f"Response: {text[:80]}...")
            print(f"Time: {response_time:.1f}ms")

            results['queries'].append({
                'query': query,
                'response': text,
                'time_ms': response_time
            })

        # Clean up
        del model

        # Calculate average
        avg_time = sum(q['time_ms'] for q in results['queries']) / len(results['queries'])
        results['avg_time_ms'] = avg_time

        print(f"\n✅ {model_name} - Avg response: {avg_time:.1f}ms")

        return results

    except Exception as e:
        print(f"❌ Error: {e}")
        return {'error': str(e)}

def main():
    """Test all models"""
    print("🚀 Testing All Three Models")

    # Models in order of size (smallest first)
    models = [
        ('tinyllama', 'chat/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf', 512),
        ('phi3', 'chat/models/Phi-3-mini-4k-instruct-q4.gguf', 1024),
        ('mistral', 'chat/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf', 1024)
    ]

    results = {}

    for model_name, model_path, context_size in models:
        result = test_single_model(model_name, model_path, context_size)
        results[model_name] = result

        # Wait between models to free resources
        time.sleep(3)

    # Save results
    results_dir = Path('chat/results')
    results_dir.mkdir(exist_ok=True)

    with open(results_dir / 'model_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    # Print summary
    print(f"\n\n{'='*60}")
    print("📊 FINAL RESULTS")
    print('='*60)

    print("\n| Model      | Size (MB) | Load Time | Avg Response | Status |")
    print("|------------|-----------|-----------|--------------|--------|")

    for name, result in results.items():
        if 'error' in result:
            print(f"| {name:10} | -         | -         | -            | ❌     |")
        else:
            print(f"| {name:10} | {result['size_mb']:9.1f} | {result['load_time']:8.1f}s | "
                  f"{result['avg_time_ms']:10.1f}ms | ✅     |")

    # Find winners
    successful = {k: v for k, v in results.items() if 'error' not in v}

    if successful:
        print("\n🏆 Best Performance:")

        # Fastest response
        fastest = min(successful.items(), key=lambda x: x[1]['avg_time_ms'])
        print(f"  Fastest: {fastest[0]} ({fastest[1]['avg_time_ms']:.1f}ms avg)")

        # Most efficient (speed per MB)
        efficiency = {
            k: v['avg_time_ms'] / v['size_mb']
            for k, v in successful.items()
        }
        most_efficient = min(efficiency.items(), key=lambda x: x[1])
        print(f"  Most efficient: {most_efficient[0]} ({most_efficient[1]:.2f}ms/MB)")

    print(f"\n✅ Results saved to chat/results/model_test_results.json")

if __name__ == "__main__":
    main()