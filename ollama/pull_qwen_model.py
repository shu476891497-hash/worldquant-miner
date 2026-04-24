#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pull Qwen Code Model with Progress Display
Shows download progress as percentage
"""

import sys
import os
import io

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        pass  # If already wrapped, ignore

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from .start_ollama import check_ollama_running, pull_model

def main():
    """Pull Qwen code model with progress"""
    print("=" * 60)
    print("Qwen Code Model Download")
    print("=" * 60)
    
    # Check if Ollama is running
    if not check_ollama_running():
        print("❌ Ollama is not running!")
        print("Please start Ollama first:")
        print("  1. Install from https://ollama.ai")
        print("  2. Run: ollama serve")
        print("  3. Then run this script again")
        return 1
    
    print("✅ Ollama is running\n")
    
    # Try models in order (smallest to biggest - user wants smaller)
    models = [
        "qwen2.5-coder:1.5b",  # Smallest, fastest (~1GB) - RECOMMENDED
        "qwen2.5-coder:7b",    # Medium (~4GB)
        "qwen2.5-coder:32b"    # Biggest (~19GB) - Only if needed
    ]
    
    print("Available models (will try in order, starting with smallest):")
    size_info = {
        "qwen2.5-coder:1.5b": "~1GB (Recommended)",
        "qwen2.5-coder:7b": "~4GB",
        "qwen2.5-coder:32b": "~19GB (Large!)"
    }
    for i, model in enumerate(models, 1):
        print(f"  {i}. {model} - {size_info.get(model, 'unknown')}")
    print()
    
    # Try to pull the smallest model first
    model_name = models[0]
    print(f"Attempting to pull: {model_name}")
    print("(Small model ~1GB, quick download)")
    print()
    
    if pull_model(model_name):
        print(f"\n✅ Successfully pulled {model_name}")
        print("\nYou can now use this model with Generation Two!")
        return 0
    else:
        print(f"\n⚠️ Failed to pull {model_name}")
        print("\nTrying smaller model...")
        
        # Try smaller model
        model_name = models[1]
        if pull_model(model_name):
            print(f"\n✅ Successfully pulled {model_name}")
            return 0
        else:
            print(f"\n⚠️ Failed to pull {model_name}")
            print("\nTrying smallest model...")
            
            model_name = models[2]
            if pull_model(model_name):
                print(f"\n✅ Successfully pulled {model_name}")
                return 0
            else:
                print("\n❌ Failed to pull any Qwen code model")
                return 1

if __name__ == "__main__":
    sys.exit(main())

