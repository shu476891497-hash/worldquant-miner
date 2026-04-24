#!/usr/bin/env python3
"""
Launch Generation Two Cyberpunk GUI
"""

import sys
import os
import logging
from pathlib import Path

# Configure logging for terminal trace
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

print("=" * 60)
print("🚀 GENERATION TWO GUI - INITIALIZATION TRACE")
print("=" * 60)

# Add project root to path (parent of generation_two)
logger.info("Setting up Python paths...")
current_dir = os.path.dirname(os.path.abspath(__file__))
gui_dir = os.path.dirname(current_dir)  # generation_two/
project_root = os.path.dirname(gui_dir)  # worldquant-miner/
sys.path.insert(0, project_root)
logger.info(f"  Current dir: {current_dir}")
logger.info(f"  GUI dir: {gui_dir}")
logger.info(f"  Project root: {project_root}")
logger.info(f"  Python path updated")

logger.info("Importing CyberpunkGUI...")
try:
    logger.info("  Step 1: Importing main_window module...")
    import generation_two.gui.main_window
    logger.info("  ✅ main_window module imported")
    
    logger.info("  Step 2: Getting CyberpunkGUI class...")
    CyberpunkGUI = generation_two.gui.main_window.CyberpunkGUI
    logger.info("  ✅ CyberpunkGUI class obtained")
except ImportError as e:
    logger.error(f"  ❌ Import error: {e}", exc_info=True)
    logger.error("  This might be due to a missing dependency or circular import")
    sys.exit(1)
except Exception as e:
    logger.error(f"  ❌ Failed to import CyberpunkGUI: {e}", exc_info=True)
    sys.exit(1)

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Starting GUI initialization...")
    
    # Get credential path (optional - will prompt if not found)
    credential_path = None
    logger.info("Searching for credential file...")
    if len(sys.argv) > 1:
        credential_path = sys.argv[1]
        logger.info(f"  Credential path from argument: {credential_path}")
    else:
        # Try to find credential file in common locations
        search_paths = [
            Path(__file__).parent.parent,  # generation_two/
            Path(__file__).parent.parent.parent,  # worldquant-miner/
            Path.cwd(),  # Current directory
        ]
        
        logger.info(f"  Searching in {len(search_paths)} locations...")
        for search_path in search_paths:
            logger.info(f"    Checking: {search_path}")
            for filename in ['credential.txt', 'credentials.txt']:
                cred_file = search_path / filename
                if cred_file.exists():
                    credential_path = str(cred_file)
                    logger.info(f"  ✅ Found credential file: {credential_path}")
                    break
            if credential_path:
                break
        
        if not credential_path:
            logger.warning("  ⚠️  No credential file found - will prompt for login")
    
    # Initialize GUI (will prompt for login if credentials not found)
    logger.info("=" * 60)
    logger.info("Initializing CyberpunkGUI...")
    try:
        app = CyberpunkGUI(credentials_path=credential_path)
        logger.info("  ✅ CyberpunkGUI initialized")
    except Exception as e:
        logger.error(f"  ❌ Failed to initialize CyberpunkGUI: {e}", exc_info=True)
        sys.exit(1)
    
    # Only run if authenticated
    logger.info("=" * 60)
    if app.authenticated:
        logger.info("✅ Authentication successful")
        logger.info("=" * 60)
        logger.info("🚀 Starting GUI main loop...")
        logger.info("=" * 60)
        try:
            app.run()
        except Exception as e:
            logger.error(f"❌ GUI runtime error: {e}", exc_info=True)
            sys.exit(1)
    else:
        logger.error("❌ Authentication failed. Application cannot start without valid credentials.")
        sys.exit(1)
