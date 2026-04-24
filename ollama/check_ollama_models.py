#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check Ollama Models
Lists all downloaded models, especially Qwen models
"""

import sys
import requests
import json
import io

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        pass  # If already wrapped, ignore

def check_ollama_models():
    """Check what models are available in Ollama"""
    print("=" * 60)
    print("Checking Ollama Models")
    print("=" * 60)
    print()
    
    try:
        # Check if Ollama is running
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        
        if response.status_code != 200:
            print("❌ Cannot connect to Ollama")
            print("Make sure Ollama is running: ollama serve")
            return 1
        
        models = response.json().get("models", [])
        
        if not models:
            print("⚠️ No models found in Ollama")
            print("You need to pull a model first:")
            print("  python generation_two/pull_qwen_model.py")
            return 1
        
        print(f"✅ Found {len(models)} model(s) in Ollama\n")
        print("=" * 60)
        print("All Available Models:")
        print("=" * 60)
        
        qwen_models = []
        other_models = []
        
        for model in models:
            name = model.get("name", "")
            size = model.get("size", 0)
            modified = model.get("modified_at", "")
            
            # Format size
            if size > 0:
                size_gb = size / (1024**3)
                size_str = f"{size_gb:.2f} GB"
            else:
                size_str = "unknown"
            
            if "qwen" in name.lower():
                qwen_models.append((name, size_str, modified))
            else:
                other_models.append((name, size_str, modified))
        
        # Show Qwen models first
        if qwen_models:
            print("\n🎯 Qwen Models:")
            print("-" * 60)
            for name, size, modified in qwen_models:
                print(f"  ✅ {name}")
                print(f"     Size: {size}")
                if modified:
                    print(f"     Modified: {modified}")
                print()
        else:
            print("\n⚠️ No Qwen models found")
            print("   Run: python generation_two/pull_qwen_model.py")
            print()
        
        # Show other models
        if other_models:
            print("\n📦 Other Models:")
            print("-" * 60)
            for name, size, modified in other_models:
                print(f"  • {name}")
                print(f"    Size: {size}")
                if modified:
                    print(f"    Modified: {modified}")
                print()
        
        # Check specifically for Qwen code models
        print("=" * 60)
        print("Qwen Code Model Status:")
        print("=" * 60)
        
        qwen_code_models = {
            "qwen2.5-coder:32b": False,
            "qwen2.5-coder:7b": False,
            "qwen2.5-coder:1.5b": False
        }
        
        all_model_names = [m.get("name", "") for m in models]
        
        for model_name in qwen_code_models.keys():
            # Check if exact match or base name match
            found = False
            for available_name in all_model_names:
                if model_name == available_name or model_name.split(":")[0] in available_name:
                    qwen_code_models[model_name] = True
                    found = True
                    # Find the actual model info
                    for model in models:
                        if model.get("name", "") == available_name:
                            size = model.get("size", 0)
                            if size > 0:
                                size_gb = size / (1024**3)
                                print(f"  ✅ {model_name} - {size_gb:.2f} GB")
                            else:
                                print(f"  ✅ {model_name}")
                            break
                    break
            
            if not found:
                print(f"  ❌ {model_name} - Not downloaded")
        
        print()
        
        # Summary
        downloaded = sum(1 for v in qwen_code_models.values() if v)
        total = len(qwen_code_models)
        
        if downloaded > 0:
            print(f"✅ {downloaded}/{total} Qwen code models are available")
            if downloaded < total:
                print("💡 You can download more models with: python generation_two/pull_qwen_model.py")
        else:
            print("❌ No Qwen code models downloaded")
            print("💡 Download one with: python generation_two/pull_qwen_model.py")
        
        return 0
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama")
        print("Make sure Ollama is running:")
        print("  1. Install from https://ollama.ai")
        print("  2. Run: ollama serve")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(check_ollama_models())

