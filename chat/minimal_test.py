#!/usr/bin/env python3
"""Minimal test to verify both models work"""

import json
import time
from pathlib import Path
from llama_cpp import Llama

def quick_test(model_name, model_path, max_tokens=30):
    """Quick test with minimal settings"""
    print(f"\n{'='*40}")
    print(f"Testing: {model_name}")
    print('='*40)

    if not Path(model_path).exists():
        return {"error": f"Model not found: {model_path}"}

    size_mb = Path(model_path).stat().st_size / (1024*1024)
    print(f"Size: {size_mb:.1f} MB")

    try:
        # Load with minimal settings
        print("Loading...")
        start = time.time()
        model = Llama(
            model_path=model_path,
            n_ctx=128,  # Very small context
            n_threads=1,  # Single thread
            n_gpu_layers=0,
            verbose=False
        )
        load_time = time.time() - start
        print(f"Loaded in {load_time:.1f}s")

        # Single test
        query = "What is a smart home?"
        print(f"\nQuery: {query}")
        start = time.time()

        response = model(
            f"Q: {query}\nA:",
            max_tokens=max_tokens,
            temperature=0.7,
            stop=["\n", "Q:"]
        )

        gen_time = time.time() - start
        text = response['choices'][0]['text'].strip()
        tokens = response['usage']['completion_tokens']

        print(f"Response: {text[:100]}...")
        print(f"Time: {gen_time:.1f}s ({tokens} tokens)")

        del model

        return {
            "model": model_name,
            "size_mb": size_mb,
            "load_time": load_time,
            "generation_time": gen_time,
            "tokens": tokens,
            "tokens_per_second": tokens/gen_time,
            "response": text
        }

    except Exception as e:
        return {"error": str(e)}

# Test both models
print("🚀 Minimal Model Test\n")

results = {}

# TinyLlama
results["TinyLlama"] = quick_test(
    "TinyLlama",
    "chat/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
    max_tokens=30
)

print("\nWaiting 3 seconds...")
time.sleep(3)

# Phi-3
results["Phi-3"] = quick_test(
    "Phi-3",
    "chat/models/Phi-3-mini-4k-instruct-q4.gguf",
    max_tokens=30
)

# Save results
Path("chat/results").mkdir(exist_ok=True)
with open("chat/results/minimal_test.json", 'w') as f:
    json.dump(results, f, indent=2)

# Summary
print(f"\n{'='*40}")
print("📊 SUMMARY")
print('='*40)

for name, result in results.items():
    if "error" in result:
        print(f"{name}: ❌ {result['error']}")
    else:
        print(f"{name}: ✅ {result['generation_time']:.1f}s @ {result['tokens_per_second']:.1f} tok/s")

print("\n✅ Test complete! Results saved to chat/results/minimal_test.json")