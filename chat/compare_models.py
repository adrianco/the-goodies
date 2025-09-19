#!/usr/bin/env python3
"""
TinyLlama vs Phi-3 Comparison Test
===================================

Compares the two smaller models suitable for CPU execution.
"""

import json
import time
from pathlib import Path
from datetime import datetime
from llama_cpp import Llama


def test_model_comprehensive(model_name: str, model_path: str, context_size: int = 256):
    """Run comprehensive tests on a single model"""
    print(f"\n{'='*60}")
    print(f"Testing: {model_name.upper()}")
    print('='*60)

    # Check model exists
    if not Path(model_path).exists():
        print(f"❌ Model not found: {model_path}")
        return None

    model_size_mb = Path(model_path).stat().st_size / (1024 * 1024)
    print(f"📦 Model size: {model_size_mb:.1f} MB")

    try:
        # Load model
        print("⏳ Loading model...")
        start_time = time.time()

        model = Llama(
            model_path=model_path,
            n_ctx=context_size,
            n_threads=2,  # Use 2 threads for consistency
            n_gpu_layers=0,  # CPU only
            verbose=False
        )

        load_time = time.time() - start_time
        print(f"✅ Loaded in {load_time:.2f} seconds")

        # Test queries for smart home context
        test_queries = [
            {
                "query": "What is a smart home?",
                "type": "definition"
            },
            {
                "query": "List three smart home devices",
                "type": "listing"
            },
            {
                "query": "How does a smart thermostat save energy?",
                "type": "explanation"
            },
            {
                "query": "What sensors detect motion?",
                "type": "technical"
            },
            {
                "query": "Compare LED and incandescent bulbs",
                "type": "comparison"
            }
        ]

        results = {
            "model": model_name,
            "model_path": model_path,
            "size_mb": model_size_mb,
            "load_time_seconds": load_time,
            "context_size": context_size,
            "test_results": []
        }

        print(f"\n📝 Running {len(test_queries)} test queries...")

        for i, test in enumerate(test_queries, 1):
            print(f"\nQuery {i}/{len(test_queries)}: {test['query']}")

            # Measure generation time
            start_time = time.time()

            # Generate response
            response = model(
                f"User: {test['query']}\nAssistant:",
                max_tokens=64,  # Reasonable response length
                temperature=0.7,
                top_p=0.9,
                stop=["User:", "\n\n"]
            )

            generation_time = time.time() - start_time
            response_text = response['choices'][0]['text'].strip()
            tokens_generated = response['usage']['completion_tokens']

            # Calculate metrics
            tokens_per_second = tokens_generated / generation_time if generation_time > 0 else 0

            print(f"  Response: {response_text[:100]}...")
            print(f"  Time: {generation_time:.2f}s | Tokens: {tokens_generated} | Speed: {tokens_per_second:.1f} tok/s")

            results["test_results"].append({
                "query": test["query"],
                "query_type": test["type"],
                "response": response_text,
                "generation_time": generation_time,
                "tokens_generated": tokens_generated,
                "tokens_per_second": tokens_per_second
            })

        # Calculate summary statistics
        total_time = sum(r["generation_time"] for r in results["test_results"])
        avg_time = total_time / len(results["test_results"])
        avg_tokens = sum(r["tokens_generated"] for r in results["test_results"]) / len(results["test_results"])
        avg_speed = sum(r["tokens_per_second"] for r in results["test_results"]) / len(results["test_results"])

        results["summary"] = {
            "total_generation_time": total_time,
            "average_generation_time": avg_time,
            "average_tokens_generated": avg_tokens,
            "average_tokens_per_second": avg_speed
        }

        print(f"\n📊 {model_name} Summary:")
        print(f"  Average response time: {avg_time:.2f}s")
        print(f"  Average tokens: {avg_tokens:.1f}")
        print(f"  Average speed: {avg_speed:.1f} tokens/second")

        # Clean up
        del model

        return results

    except Exception as e:
        print(f"❌ Error testing {model_name}: {e}")
        return None


def main():
    """Main comparison function"""
    print("🚀 TinyLlama vs Phi-3 Model Comparison")
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🖥️  Running on CPU with 2 threads\n")

    # Model configurations
    models = [
        {
            "name": "TinyLlama",
            "path": "chat/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
            "context_size": 256
        },
        {
            "name": "Phi-3",
            "path": "chat/models/Phi-3-mini-4k-instruct-q4.gguf",
            "context_size": 512  # Phi-3 can handle more context
        }
    ]

    # Run tests
    all_results = {}

    for model_config in models:
        result = test_model_comprehensive(
            model_config["name"],
            model_config["path"],
            model_config["context_size"]
        )

        if result:
            all_results[model_config["name"]] = result

        # Wait between models
        print("\n⏳ Waiting 5 seconds before next model...")
        time.sleep(5)

    # Save results
    output_dir = Path("chat/results")
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\n💾 Results saved to: {output_file}")

    # Generate comparison report
    print("\n" + "="*60)
    print("📋 FINAL COMPARISON REPORT")
    print("="*60)

    if len(all_results) == 2:
        # Comparison table
        print("\n| Metric                    | TinyLlama      | Phi-3          |")
        print("|---------------------------|----------------|----------------|")

        tinyllama = all_results.get("TinyLlama", {})
        phi3 = all_results.get("Phi-3", {})

        # Model size
        print(f"| Model Size                | {tinyllama.get('size_mb', 0):.1f} MB      | {phi3.get('size_mb', 0):.1f} MB     |")

        # Load time
        print(f"| Load Time                 | {tinyllama.get('load_time_seconds', 0):.2f}s          | {phi3.get('load_time_seconds', 0):.2f}s         |")

        # Average response time
        tl_avg = tinyllama.get('summary', {}).get('average_generation_time', 0)
        p3_avg = phi3.get('summary', {}).get('average_generation_time', 0)
        print(f"| Avg Response Time         | {tl_avg:.2f}s          | {p3_avg:.2f}s         |")

        # Average tokens per second
        tl_speed = tinyllama.get('summary', {}).get('average_tokens_per_second', 0)
        p3_speed = phi3.get('summary', {}).get('average_tokens_per_second', 0)
        print(f"| Avg Speed (tokens/s)      | {tl_speed:.1f}           | {p3_speed:.1f}           |")

        # Determine winner for each category
        print("\n🏆 Winners by Category:")

        # Size efficiency
        if tinyllama.get('size_mb', float('inf')) < phi3.get('size_mb', float('inf')):
            print("  📦 Smallest Size: TinyLlama")
        else:
            print("  📦 Smallest Size: Phi-3")

        # Load speed
        if tinyllama.get('load_time_seconds', float('inf')) < phi3.get('load_time_seconds', float('inf')):
            print("  ⚡ Fastest Load: TinyLlama")
        else:
            print("  ⚡ Fastest Load: Phi-3")

        # Response speed
        if tl_avg < p3_avg and tl_avg > 0:
            print("  🚀 Fastest Response: TinyLlama")
        else:
            print("  🚀 Fastest Response: Phi-3")

        # Token generation speed
        if tl_speed > p3_speed:
            print("  💨 Highest Throughput: TinyLlama")
        else:
            print("  💨 Highest Throughput: Phi-3")

        # Overall recommendation
        print("\n📌 Recommendations:")
        print("  • For fastest responses on limited hardware: TinyLlama")
        print("  • For better quality responses with more context: Phi-3")
        print("  • For mobile/embedded systems: TinyLlama (smaller size)")
        print("  • For desktop applications: Phi-3 (better capabilities)")

    else:
        print("⚠️  Not all models were tested successfully")

    print("\n✅ Comparison test complete!")

    # Create markdown report
    create_markdown_report(all_results)

    return all_results


def create_markdown_report(results):
    """Create a markdown report of the comparison"""
    report_path = Path("chat/results/comparison_report.md")

    with open(report_path, 'w') as f:
        f.write("# TinyLlama vs Phi-3 Model Comparison Report\n\n")
        f.write(f"**Test Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Executive Summary\n\n")
        f.write("This report compares TinyLlama (1.1B) and Phi-3 Mini (4K) models for smart home chat applications on CPU.\n\n")

        if len(results) == 2:
            tinyllama = results.get("TinyLlama", {})
            phi3 = results.get("Phi-3", {})

            f.write("## Performance Metrics\n\n")
            f.write("| Metric | TinyLlama | Phi-3 |\n")
            f.write("|--------|-----------|-------|\n")
            f.write(f"| Model Size | {tinyllama.get('size_mb', 0):.1f} MB | {phi3.get('size_mb', 0):.1f} MB |\n")
            f.write(f"| Load Time | {tinyllama.get('load_time_seconds', 0):.2f}s | {phi3.get('load_time_seconds', 0):.2f}s |\n")
            f.write(f"| Avg Response Time | {tinyllama.get('summary', {}).get('average_generation_time', 0):.2f}s | {phi3.get('summary', {}).get('average_generation_time', 0):.2f}s |\n")
            f.write(f"| Tokens per Second | {tinyllama.get('summary', {}).get('average_tokens_per_second', 0):.1f} | {phi3.get('summary', {}).get('average_tokens_per_second', 0):.1f} |\n")

            f.write("\n## Sample Responses\n\n")
            f.write("### Query: \"What is a smart home?\"\n\n")

            if tinyllama.get('test_results'):
                f.write(f"**TinyLlama:** {tinyllama['test_results'][0]['response']}\n\n")

            if phi3.get('test_results'):
                f.write(f"**Phi-3:** {phi3['test_results'][0]['response']}\n\n")

            f.write("## Recommendations\n\n")
            f.write("- **TinyLlama**: Best for resource-constrained environments, mobile devices, and real-time applications\n")
            f.write("- **Phi-3**: Better for applications requiring higher quality responses and more context understanding\n")

    print(f"📄 Markdown report saved to: {report_path}")


if __name__ == "__main__":
    results = main()