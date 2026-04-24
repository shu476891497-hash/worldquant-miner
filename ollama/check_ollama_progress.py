#!/usr/bin/env python3
"""
Check Ollama Model Download Progress
Shows real-time progress when pulling models
"""

import subprocess
import sys
import re
import time

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

def show_progress(model_name: str):
    """Show progress while pulling model"""
    print(f"📥 Pulling {model_name}...")
    print("=" * 60)
    
    process = subprocess.Popen(
        ["ollama", "pull", model_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    last_percent = -1
    last_line = ""
    
    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            
            # Check for percentage
            percent_match = re.search(r'(\d+\.?\d*)\s*%', line)
            
            # Check for size info: "1.2GB / 2.4GB"
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
                    
                    # Clear line and print progress
                    print(f"\r[{bar}] {percent:.1f}% | {downloaded_fmt} / {total_fmt}", 
                          end="", flush=True)
                    last_percent = percent
                    last_line = line
            
            elif percent_match:
                # Just percentage
                percent = float(percent_match.group(1))
                if percent != last_percent:
                    bar_length = 50
                    filled = int(bar_length * percent / 100)
                    bar = "█" * filled + "░" * (bar_length - filled)
                    print(f"\r[{bar}] {percent:.1f}%", end="", flush=True)
                    last_percent = percent
                    last_line = line
            
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
        
        # Clear progress line
        print("\r" + " " * 100 + "\r", end="")
        
        process.wait()
        
        if process.returncode == 0:
            print("\n✅ Model pull completed successfully!")
            return True
        else:
            print("\n❌ Model pull failed")
            return False
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        process.terminate()
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python check_ollama_progress.py <model_name>")
        print("\nExamples:")
        print("  python check_ollama_progress.py qwen2.5-coder:32b")
        print("  python check_ollama_progress.py qwen2.5-coder:7b")
        sys.exit(1)
    
    model_name = sys.argv[1]
    
    print("=" * 60)
    print("Ollama Model Download Progress")
    print("=" * 60)
    
    success = show_progress(model_name)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

