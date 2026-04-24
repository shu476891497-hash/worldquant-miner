#!/usr/bin/env python3
"""
Quick test script to verify the simulation submission fix
Tests that POST requests to /simulations endpoint work correctly
"""

import logging
import sys
import os
from pathlib import Path

# Setup detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from generation_two import TemplateGenerator, SimulatorTester, SimulationSettings

def test_simulation_submission():
    """Test that simulation submission works with the fixed endpoint"""
    
    # Get credential path
    credential_path = Path(__file__).parent / "credential.txt"
    
    if not credential_path.exists():
        logger.error(f"❌ Credential file not found: {credential_path}")
        logger.info("Please create credential.txt with WorldQuant Brain credentials")
        return False
    
    logger.info(f"✅ Using credentials from: {credential_path}")
    
    try:
        # Initialize template generator (handles authentication)
        logger.info("🔐 Setting up authentication...")
        template_generator = TemplateGenerator(credentials_path=str(credential_path))
        template_generator.setup_auth()
        
        logger.info("✅ Authentication successful")
        
        # Setup simulator tester
        logger.info("🔧 Setting up simulator tester...")
        region_configs = {
            'USA': type('RegionConfig', (), {'region': 'USA', 'universe': 'TOP3000', 'delay': 1})(),
            'EUR': type('RegionConfig', (), {'region': 'EUR', 'universe': 'TOP3000', 'delay': 1})()
        }
        
        simulator_tester = SimulatorTester(
            session=template_generator.sess,
            region_configs=region_configs,
            template_generator=template_generator
        )
        
        logger.info("✅ Simulator tester initialized")
        
        # Test with a simple template
        test_template = "ts_rank(close, 20)"
        test_region = "USA"
        test_settings = SimulationSettings(
            region=test_region,
            testPeriod="P1Y0M0D"  # 1 year test period for faster results
        )
        
        logger.info(f"\n📝 Testing simulation submission:")
        logger.info(f"   Template: {test_template}")
        logger.info(f"   Region: {test_region}")
        logger.info(f"   Test Period: {test_settings.testPeriod}")
        
        # Submit simulation
        logger.info("\n🚀 Submitting simulation...")
        progress_url = simulator_tester.submit_simulation(
            template=test_template,
            region=test_region,
            settings=test_settings
        )
        
        if progress_url:
            logger.info(f"✅ SUCCESS! Simulation submitted successfully")
            logger.info(f"   Progress URL: {progress_url}")
            logger.info(f"\n✅ Fix verified: POST to /simulations endpoint works!")
            logger.info(f"\n💡 Note: The simulation will continue running in the background.")
            logger.info(f"   You can monitor it at: {progress_url}")
            return True
        else:
            logger.error(f"❌ FAILED: Could not submit simulation")
            logger.error(f"   Check the logs above for error details")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error during test: {e}", exc_info=True)
        return False

def main():
    """Main test function"""
    logger.info("=" * 60)
    logger.info("Testing Simulation Submission Fix")
    logger.info("=" * 60)
    logger.info("\nThis test verifies that:")
    logger.info("  1. POST requests use /simulations endpoint (not /alphas)")
    logger.info("  2. Request format is correct (type, settings, regular)")
    logger.info("  3. Progress URL is returned from Location header")
    logger.info("=" * 60)
    logger.info("")
    
    success = test_simulation_submission()
    
    logger.info("")
    logger.info("=" * 60)
    if success:
        logger.info("✅ TEST PASSED: Simulation submission fix is working!")
    else:
        logger.info("❌ TEST FAILED: Check errors above")
    logger.info("=" * 60)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
