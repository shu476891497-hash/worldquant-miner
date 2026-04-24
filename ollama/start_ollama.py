#!/usr/bin/env python3
"""
Start or Test Ollama Service
Checks if Ollama is running and starts it if needed
"""

import subprocess
import sys
import time
import requests
import logging
import re
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_ollama_running(url: str = "http://localhost:11434") -> bool:
    """Check if Ollama is already running"""
    try:
        response = requests.get(f"{url}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def start_ollama_service():
    """Start Ollama service"""
    logger.info("Attempting to start Ollama service...")
    
    # Try different methods to start Ollama
    methods = [
        # Method 1: Direct ollama serve command
        ["ollama", "serve"],
        # Method 2: Check if ollama is in PATH
        ["where", "ollama"] if sys.platform == "win32" else ["which", "ollama"],
    ]
    
    # On Windows, try to find Ollama executable
    if sys.platform == "win32":
        possible_paths = [
            Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
            Path("C:/Program Files/Ollama/ollama.exe"),
        ]
        
        for ollama_path in possible_paths:
            if ollama_path.exists():
                logger.info(f"Found Ollama at: {ollama_path}")
                try:
                    # Start Ollama in background
                    subprocess.Popen(
                        [str(ollama_path), "serve"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    logger.info("Started Ollama service")
                    return True
                except Exception as e:
                    logger.error(f"Failed to start Ollama: {e}")
    
    # Try to run ollama serve directly
    try:
        result = subprocess.run(
            ["ollama", "serve"],
            capture_output=True,
            timeout=2,
            check=False
        )
        logger.info("Ollama service command executed")
        return True
    except FileNotFoundError:
        logger.warning("Ollama not found in PATH")
        logger.info("Please install Ollama from https://ollama.ai")
        logger.info("Or start Ollama manually: ollama serve")
        return False
    except Exception as e:
        logger.error(f"Error starting Ollama: {e}")
        return False


def pull_model(model_name: str = "qwen2.5-coder:32b"):
    """Pull a model if not already available with progress display"""
    logger.info(f"Checking if model {model_name} is available...")
    
    try:
        # Check available models
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            # Check if model exists (with or without tag)
            model_base = model_name.split(":")[0]
            if any(model_base in name for name in model_names):
                logger.info(f"✅ Model {model_name} is already available")
                return True
            
            logger.info(f"📥 Model {model_name} not found, pulling...")
            logger.info("This may take a while depending on model size...")
            logger.info("=" * 60)
            
            # Pull the model with progress tracking
            # Use binary mode to avoid encoding issues
            process = subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1
            )
            
            # Parse and display progress
            total_size = None
            downloaded = 0
            last_percent = -1
            
            for raw_line in process.stdout:
                # Decode with error handling
                try:
                    line = raw_line.decode('utf-8', errors='replace').strip()
                except:
                    try:
                        line = raw_line.decode('latin-1', errors='replace').strip()
                    except:
                        continue
                
                if not line:
                    continue
                
                # Parse different progress formats from Ollama
                # Format examples:
                # "pulling manifest" 
                # "pulling 45a4a2c3... 100%"
                # "pulling 45a4a2c3... 50% | 1.2GB / 2.4GB"
                # "verifying sha256 digest"
                # "writing manifest"
                # "success"
                
                if "pulling" in line.lower():
                    # Look for percentage: "50%" or "50.5%"
                    percent_match = re.search(r'(\d+\.?\d*)\s*%', line)
                    if percent_match:
                        percent = float(percent_match.group(1))
                        if percent != last_percent:
                            # Create progress bar
                            bar_length = 40
                            filled = int(bar_length * percent / 100)
                            bar = "█" * filled + "░" * (bar_length - filled)
                            print(f"\r[{bar}] {percent:.1f}%", end="", flush=True)
                            last_percent = percent
                    
                    # Look for size info: "1.2GB / 2.4GB"
                    size_match = re.search(r'(\d+\.?\d*)\s*([KMGT]?B)\s*/\s*(\d+\.?\d*)\s*([KMGT]?B)', line)
                    if size_match:
                        downloaded_str, downloaded_unit = size_match.group(1), size_match.group(2)
                        total_str, total_unit = size_match.group(3), size_match.group(4)
                        
                        # Convert to bytes for calculation
                        def to_bytes(value, unit):
                            multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
                            return float(value) * multipliers.get(unit.upper(), 1)
                        
                        downloaded_bytes = to_bytes(downloaded_str, downloaded_unit)
                        total_bytes = to_bytes(total_str, total_unit)
                        
                        if total_bytes > 0:
                            percent = (downloaded_bytes / total_bytes) * 100
                            bar_length = 40
                            filled = int(bar_length * percent / 100)
                            bar = "█" * filled + "░" * (bar_length - filled)
                            print(f"\r[{bar}] {percent:.1f}% ({downloaded_str}{downloaded_unit} / {total_str}{total_unit})", 
                                  end="", flush=True)
                            last_percent = percent
                    
                    # If just percentage without size
                    elif percent_match and not size_match:
                        percent = float(percent_match.group(1))
                        bar_length = 40
                        filled = int(bar_length * percent / 100)
                        bar = "█" * filled + "░" * (bar_length - filled)
                        print(f"\r[{bar}] {percent:.1f}%", end="", flush=True)
                        last_percent = percent
                    else:
                        # Just show the line for other messages
                        print(f"\n{line}")
                
                elif "verifying" in line.lower() or "writing" in line.lower():
                    print(f"\n{line}")
                elif "success" in line.lower() or "complete" in line.lower():
                    print(f"\n✅ {line}")
            
            # Clear progress line and add newline
            print("\r" + " " * 80 + "\r", end="")
            
            process.wait()
            
            if process.returncode == 0:
                logger.info(f"✅ Successfully pulled model {model_name}")
                logger.info("=" * 60)
                return True
            else:
                logger.error(f"❌ Failed to pull model")
                return False
                
    except Exception as e:
        logger.error(f"❌ Error pulling model: {e}")
        return False


def test_ollama_connection(model_name: str = "qwen2.5-coder:32b"):
    """Test Ollama connection and model"""
    logger.info(f"Testing Ollama connection with model {model_name}...")
    
    try:
        # Test simple generation
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model_name,
                "prompt": "Write a simple Python function to add two numbers.",
                "stream": False
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            generated = result.get("response", "").strip()
            logger.info("✅ Ollama is working!")
            logger.info(f"Generated response (first 100 chars): {generated[:100]}...")
            return True
        else:
            logger.error(f"Ollama test failed: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to Ollama. Is it running?")
        return False
    except Exception as e:
        logger.error(f"❌ Error testing Ollama: {e}")
        return False


def main():
    """Main function"""
    ollama_url = "http://localhost:11434"
    model_name = "qwen2.5-coder:32b"  # Reasonably big Qwen code model
    
    logger.info("=== Ollama Setup and Test ===")
    
    # Check if Ollama is running
    if check_ollama_running(ollama_url):
        logger.info("✅ Ollama is already running")
    else:
        logger.info("⚠️ Ollama is not running")
        logger.info("Attempting to start Ollama...")
        
        if not start_ollama_service():
            logger.error("❌ Could not start Ollama automatically")
            logger.info("\nPlease start Ollama manually:")
            logger.info("  1. Install from https://ollama.ai")
            logger.info("  2. Run: ollama serve")
            logger.info("  3. Then run this script again")
            sys.exit(1)
        
        # Wait for Ollama to start
        logger.info("Waiting for Ollama to start...")
        for i in range(10):
            time.sleep(2)
            if check_ollama_running(ollama_url):
                logger.info("✅ Ollama started successfully")
                break
        else:
            logger.error("❌ Ollama did not start in time")
            sys.exit(1)
    
    # Pull model if needed
    logger.info(f"\n=== Checking Model: {model_name} ===")
    if not pull_model(model_name):
        logger.warning(f"⚠️ Could not pull {model_name}, trying smaller model...")
        # Try smaller model as fallback
        model_name = "qwen2.5-coder:7b"
        if not pull_model(model_name):
            logger.error("❌ Could not pull any Qwen code model")
            sys.exit(1)
    
    # Test connection
    logger.info(f"\n=== Testing Ollama with {model_name} ===")
    if test_ollama_connection(model_name):
        logger.info("\n✅ All tests passed! Ollama is ready to use.")
        logger.info(f"Model: {model_name}")
        logger.info(f"URL: {ollama_url}")
        return 0
    else:
        logger.error("\n❌ Ollama test failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

