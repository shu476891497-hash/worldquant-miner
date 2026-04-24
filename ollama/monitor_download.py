#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor Ollama Model Download Progress
Shows real-time progress of ongoing downloads
"""

import sys
import requests
import time
import re
import subprocess
import io

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        pass

def format_size(size_bytes):
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def parse_size(size_str, unit):
    """Parse size string to bytes"""
    multipliers = {
        'B': 1,
        'KB': 1024,
        'MB': 1024**2,
        'GB': 1024**3,
        'TB': 1024**4
    }
    return float(size_str) * multipliers.get(unit.upper(), 1)

def monitor_ollama_pull(model_name):
    """Monitor Ollama pull progress"""
    print("=" * 60)
    print(f"Monitoring Download: {model_name}")
    print("=" * 60)
    print()
    
    try:
        # Check if model is already downloaded
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            model_base = model_name.split(":")[0]
            
            if any(model_base in name for name in model_names):
                print(f"✅ Model {model_name} is already downloaded!")
                return 0
        
        # Start monitoring the pull process
        print("Starting download monitor...")
        print("Press Ctrl+C to stop monitoring (download will continue)")
        print()
        
        process = subprocess.Popen(
            ["ollama", "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1
        )
        
        last_percent = -1
        last_size_info = ""
        
        try:
            for raw_line in process.stdout:
                try:
                    line = raw_line.decode('utf-8', errors='replace').strip()
                except:
                    try:
                        line = raw_line.decode('latin-1', errors='replace').strip()
                    except:
                        continue
                
                if not line:
                    continue
                
                # Parse progress
                percent_match = re.search(r'(\d+\.?\d*)\s*%', line)
                size_match = re.search(
                    r'(\d+\.?\d*)\s*([KMGT]?B)\s*/\s*(\d+\.?\d*)\s*([KMGT]?B)', 
                    line
                )
                
                if size_match:
                    # Has both size and percentage
                    downloaded_str, downloaded_unit = size_match.group(1), size_match.group(2)
                    total_str, total_unit = size_match.group(3), size_match.group(4)
                    
                    downloaded_bytes = parse_size(downloaded_str, downloaded_unit)
                    total_bytes = parse_size(total_str, total_unit)
                    
                    if total_bytes > 0:
                        percent = (downloaded_bytes / total_bytes) * 100
                        
                        # Update progress bar
                        bar_length = 50
                        filled = int(bar_length * percent / 100)
                        bar = "█" * filled + "░" * (bar_length - filled)
                        
                        # Format sizes
                        downloaded_fmt = format_size(downloaded_bytes)
                        total_fmt = format_size(total_bytes)
                        
                        # Calculate remaining
                        remaining_bytes = total_bytes - downloaded_bytes
                        remaining_fmt = format_size(remaining_bytes)
                        
                        # Calculate speed (simplified - would need time tracking for accurate speed)
                        size_info = f"{downloaded_fmt} / {total_fmt} (Remaining: {remaining_fmt})"
                        
                        # Clear line and print progress
                        print(f"\r[{bar}] {percent:.1f}% | {size_info}", end="", flush=True)
                        last_percent = percent
                        last_size_info = size_info
                
                elif percent_match:
                    # Just percentage
                    percent = float(percent_match.group(1))
                    if percent != last_percent:
                        bar_length = 50
                        filled = int(bar_length * percent / 100)
                        bar = "█" * filled + "░" * (bar_length - filled)
                        print(f"\r[{bar}] {percent:.1f}%", end="", flush=True)
                        last_percent = percent
                
                elif "pulling manifest" in line.lower():
                    print(f"\n📋 {line}")
                elif "verifying" in line.lower():
                    print(f"\n🔍 {line}")
                elif "writing" in line.lower():
                    print(f"\n💾 {line}")
                elif "success" in line.lower() or "complete" in line.lower():
                    print(f"\n✅ {line}")
                    break
                elif "error" in line.lower() or "failed" in line.lower():
                    print(f"\n❌ {line}")
                    break
            
            # Clear progress line
            print("\r" + " " * 100 + "\r", end="")
            
            process.wait()
            
            if process.returncode == 0:
                print("\n✅ Download completed successfully!")
                return 0
            else:
                print("\n❌ Download failed")
                return 1
                
        except KeyboardInterrupt:
            print("\n\n⚠️ Monitoring stopped (download may continue in background)")
            print("You can check status with: python generation_two/check_ollama_models.py")
            return 0
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama")
        print("Make sure Ollama is running: ollama serve")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

def check_current_download():
    """Check if there's an active download"""
    # This is a simplified check - Ollama doesn't expose active downloads via API
    # We'll just try to monitor the pull
    return True

def main():
    """Main function"""
    if len(sys.argv) > 1:
        model_name = sys.argv[1]
    else:
        # Default to checking what's downloading
        model_name = "qwen2.5-coder:32b"
        print(f"No model specified, monitoring: {model_name}")
        print("Usage: python monitor_download.py <model_name>")
        print()
    
    return monitor_ollama_pull(model_name)

if __name__ == "__main__":
    sys.exit(main())

