#!/usr/bin/env python3
"""Quick test of TinyLlama - the smallest model"""

import time
from pathlib import Path
from llama_cpp import Llama

def test_tinyllama():
    model_path = "chat/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

    if not Path(model_path).exists():
        print(f"❌ Model not found: {model_path}")
        return False

    print(f"✅ Found model: {Path(model_path).stat().st_size / (1024*1024):.1f} MB")

    try:
        print("Loading TinyLlama...")
        start = time.time()

        model = Llama(
            model_path=model_path,
            n_ctx=512,  # Very small context
            n_threads=2,  # Minimal threads
            n_gpu_layers=0,
            verbose=False
        )

        print(f"✅ Loaded in {time.time() - start:.1f}s")

        # Single quick test
        print("\nTesting query: 'What is a smart home?'")
        start = time.time()

        response = model(
            "User: What is a smart home in one sentence?\nAssistant:",
            max_tokens=50,
            temperature=0.7,
            stop=["User:", "\n"]
        )

        text = response['choices'][0]['text'].strip()
        print(f"Response: {text}")
        print(f"Time: {(time.time() - start)*1000:.1f}ms")

        del model
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Quick TinyLlama Test")
    success = test_tinyllama()
    print(f"\n{'✅ Test passed!' if success else '❌ Test failed!'}")