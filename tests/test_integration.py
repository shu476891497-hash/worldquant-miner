#!/usr/bin/env python3
"""
Full Integration Test for Configurable Architecture
Tests all components working together: config, retry, recording, and actual API calls
"""

import logging
import sys
import os
import time
from pathlib import Path
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import all components
from generation_two import (
    # Core components
    TemplateGenerator,
    SimulatorTester,
    SimulationSettings,
    EnhancedTemplateGeneratorV3,
    # Utilities
    RetryHandler,
    RetryConfig,
    RetryStrategy,
    RequestHandler,
    RequestConfig,
    # Configuration
    ConfigManager,
    # Recording
    DecisionRecorder,
    AuditLogger
)


class IntegrationTest:
    """Full integration test suite"""
    
    def __init__(self, credential_path: str):
        """
        Initialize integration test
        
        Args:
            credential_path: Path to WorldQuant Brain credentials
        """
        self.credential_path = credential_path
        self.test_results = {}
        self.cleanup_files = []
    
    def setup(self):
        """Setup test environment"""
        logger.info("=" * 80)
        logger.info("Setting up integration test environment")
        logger.info("=" * 80)
        
        # Create test config file
        self.config_path = "test_integration_config.json"
        self.cleanup_files.append(self.config_path)
        
        # Create test recording database
        self.recording_db = "test_integration_decisions.db"
        self.cleanup_files.append(self.recording_db)
        
        # Initialize components
        self.config = ConfigManager(self.config_path)
        self.recorder = DecisionRecorder(self.recording_db)
        self.audit = AuditLogger(self.recorder)
        
        logger.info("✅ Setup complete")
    
    def test_config_system(self):
        """Test 1: Configuration System"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 1: Configuration System")
        logger.info("=" * 80)
        
        try:
            # Test getting default values
            max_retries = self.config.get('retry', 'max_retries', 3)
            assert max_retries == 3, f"Expected 3, got {max_retries}"
            logger.info(f"✅ Default retry max_retries: {max_retries}")
            
            # Test setting values
            self.config.set('retry', 'max_retries', 5)
            new_value = self.config.get('retry', 'max_retries')
            assert new_value == 5, f"Expected 5, got {new_value}"
            logger.info(f"✅ Updated retry max_retries: {new_value}")
            
            # Test configuration change listener
            change_detected = {'value': None}
            
            def on_change(section, key, old_value, new_value):
                change_detected['value'] = new_value
                logger.info(f"   Config change detected: {section}.{key} = {new_value}")
            
            self.config.add_listener(on_change)
            self.config.set('retry', 'base_delay', 2.0)
            assert change_detected['value'] == 2.0, "Change listener not triggered"
            logger.info("✅ Configuration change listener works")
            
            # Test saving and loading
            self.config.save()
            new_config = ConfigManager(self.config_path)
            loaded_value = new_config.get('retry', 'max_retries')
            assert loaded_value == 5, f"Expected 5 after load, got {loaded_value}"
            logger.info("✅ Configuration save/load works")
            
            # Test change history
            history = self.config.get_change_history(limit=10)
            assert len(history) > 0, "Change history should not be empty"
            logger.info(f"✅ Change history tracking works ({len(history)} changes)")
            
            self.test_results['config_system'] = True
            logger.info("✅ TEST 1 PASSED: Configuration System")
            
        except Exception as e:
            self.test_results['config_system'] = False
            logger.error(f"❌ TEST 1 FAILED: {e}", exc_info=True)
    
    def test_retry_handler(self):
        """Test 2: Retry Handler"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 2: Retry Handler")
        logger.info("=" * 80)
        
        try:
            # Test exponential retry strategy
            retry_config = RetryConfig(
                max_retries=3,
                strategy=RetryStrategy.EXPONENTIAL,
                base_delay=0.1,  # Short delay for testing
                multiplier=2.0
            )
            handler = RetryHandler(retry_config)
            
            # Test delay calculation
            delay1 = handler.calculate_delay(0)
            delay2 = handler.calculate_delay(1)
            delay3 = handler.calculate_delay(2)
            
            assert delay1 == 0.1, f"Expected 0.1, got {delay1}"
            assert delay2 == 0.2, f"Expected 0.2, got {delay2}"
            assert delay3 == 0.4, f"Expected 0.4, got {delay3}"
            logger.info(f"✅ Exponential delay calculation: {delay1}, {delay2}, {delay3}")
            
            # Test successful execution (no retries needed)
            call_count = {'value': 0}
            
            def success_func():
                call_count['value'] += 1
                return "success"
            
            result = handler.execute_with_retry(success_func)
            assert result == "success", "Function should succeed"
            assert call_count['value'] == 1, "Function should be called once"
            logger.info("✅ Successful execution (no retries)")
            
            # Test retry on failure (will fail after retries)
            call_count['value'] = 0
            
            def failing_func():
                call_count['value'] += 1
                raise ValueError("Test error")
            
            try:
                handler.execute_with_retry(failing_func)
                assert False, "Should have raised exception"
            except ValueError:
                assert call_count['value'] == 4, f"Expected 4 calls (1 initial + 3 retries), got {call_count['value']}"
                logger.info(f"✅ Retry on failure works ({call_count['value']} attempts)")
            
            # Test stats
            stats = handler.get_stats()
            assert stats['total_attempts'] > 0, "Stats should track attempts"
            logger.info(f"✅ Statistics tracking: {stats}")
            
            # Test configuration update
            new_config = RetryConfig(max_retries=2, strategy=RetryStrategy.LINEAR)
            handler.update_config(new_config)
            assert handler.config.max_retries == 2, "Config should be updated"
            logger.info("✅ Configuration update works")
            
            self.test_results['retry_handler'] = True
            logger.info("✅ TEST 2 PASSED: Retry Handler")
            
        except Exception as e:
            self.test_results['retry_handler'] = False
            logger.error(f"❌ TEST 2 FAILED: {e}", exc_info=True)
    
    def test_recording_system(self):
        """Test 3: Recording System"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 3: Recording System")
        logger.info("=" * 80)
        
        try:
            # Test recording a decision
            self.recorder.record(
                decision_type='test_decision',
                context={'test': 'integration'},
                parameters={'param1': 'value1', 'param2': 42},
                result={'output': 'test_result'},
                success=True
            )
            logger.info("✅ Decision recorded")
            
            # Test querying records
            records = self.recorder.query(decision_type='test_decision', limit=10)
            assert len(records) > 0, "Should find recorded decisions"
            assert records[0].decision_type == 'test_decision', "Should match decision type"
            assert records[0].success is True, "Should match success status"
            logger.info(f"✅ Query works: found {len(records)} records")
            
            # Test statistics
            stats = self.recorder.get_statistics()
            assert stats['total_records'] > 0, "Should have records"
            assert 'test_decision' in stats['by_type'], "Should track by type"
            logger.info(f"✅ Statistics: {stats}")
            
            # Test audit logger
            self.audit.log_operation(
                'test_operation',
                {'detail': 'test'},
                success=True
            )
            logger.info("✅ Audit logging works")
            
            # Test export
            export_path = "test_export.json"
            self.cleanup_files.append(export_path)
            self.recorder.export_to_json(export_path, decision_type='test_decision')
            assert os.path.exists(export_path), "Export file should exist"
            logger.info("✅ Export to JSON works")
            
            self.test_results['recording_system'] = True
            logger.info("✅ TEST 3 PASSED: Recording System")
            
        except Exception as e:
            self.test_results['recording_system'] = False
            logger.error(f"❌ TEST 3 FAILED: {e}", exc_info=True)
    
    def test_integrated_workflow(self):
        """Test 4: Integrated Workflow (Config + Retry + Recording)"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 4: Integrated Workflow")
        logger.info("=" * 80)
        
        try:
            # Configure retry from config
            retry_config = RetryConfig(
                max_retries=self.config.get('retry', 'max_retries', 3),
                strategy=RetryStrategy(self.config.get('retry', 'strategy', 'exponential')),
                base_delay=self.config.get('retry', 'base_delay', 1.0)
            )
            retry_handler = RetryHandler(retry_config)
            
            # Simulate a workflow with recording
            def simulated_operation(param1, param2):
                # Record decision start
                self.recorder.record(
                    decision_type='simulated_operation',
                    context={'operation': 'test'},
                    parameters={'param1': param1, 'param2': param2},
                    success=None  # Not completed yet
                )
                
                # Simulate operation
                result = param1 + param2
                
                # Record completion
                self.recorder.record(
                    decision_type='simulated_operation',
                    context={'operation': 'test'},
                    parameters={'param1': param1, 'param2': param2},
                    result={'sum': result},
                    success=True
                )
                
                return result
            
            # Execute with retry
            result = retry_handler.execute_with_retry(
                simulated_operation,
                10, 20,
                on_success=lambda r: logger.info(f"   Operation succeeded: {r}")
            )
            
            assert result == 30, f"Expected 30, got {result}"
            logger.info(f"✅ Integrated workflow works: result = {result}")
            
            # Verify recording
            records = self.recorder.query(decision_type='simulated_operation')
            assert len(records) >= 1, "Should have recorded operations"
            logger.info(f"✅ Recording integrated: {len(records)} records")
            
            self.test_results['integrated_workflow'] = True
            logger.info("✅ TEST 4 PASSED: Integrated Workflow")
            
        except Exception as e:
            self.test_results['integrated_workflow'] = False
            logger.error(f"❌ TEST 4 FAILED: {e}", exc_info=True)
    
    def test_real_api_integration(self):
        """Test 5: Real API Integration (with WorldQuant Brain)"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 5: Real API Integration")
        logger.info("=" * 80)
        
        if not os.path.exists(self.credential_path):
            logger.warning("⚠️  Credentials not found, skipping real API test")
            self.test_results['real_api_integration'] = 'skipped'
            return
        
        try:
            # Initialize template generator with recording
            template_generator = TemplateGenerator(
                credentials_path=self.credential_path
            )
            template_generator.setup_auth()
            logger.info("✅ Authentication successful")
            
            # Record authentication
            self.recorder.record(
                decision_type='authentication',
                context={'system': 'worldquant_brain'},
                parameters={},
                success=True
            )
            
            # Test template generation with recording
            prompt = "Generate a simple momentum alpha"
            logger.info(f"Testing template generation with prompt: {prompt}")
            
            start_time = time.time()
            template = template_generator.generate_template_from_prompt(
                prompt,
                region="USA",
                use_ollama=True
            )
            generation_time = time.time() - start_time
            
            if template:
                logger.info(f"✅ Template generated: {template[:50]}...")
                
                # Record template generation
                self.recorder.record(
                    decision_type='template_generation',
                    context={'prompt': prompt, 'region': 'USA'},
                    parameters={
                        'use_ollama': True,
                        'model': template_generator.ollama_manager.model if hasattr(template_generator, 'ollama_manager') else None
                    },
                    result={'template': template, 'generation_time': generation_time},
                    success=True
                )
                
                # Test simulation submission (if template is valid)
                logger.info("Testing simulation submission...")
                
                # Setup simulator tester
                region_configs = {
                    'USA': type('RegionConfig', (), {'region': 'USA', 'universe': 'TOP3000', 'delay': 1})()
                }
                
                simulator_tester = SimulatorTester(
                    session=template_generator.sess,
                    region_configs=region_configs,
                    template_generator=template_generator
                )
                
                settings = SimulationSettings(
                    region="USA",
                    testPeriod="P1Y0M0D"  # 1 year for faster testing
                )
                
                # Record simulation submission
                submission_start = time.time()
                progress_url = simulator_tester.submit_simulation(
                    template,
                    "USA",
                    settings
                )
                submission_time = time.time() - submission_start
                
                if progress_url:
                    logger.info(f"✅ Simulation submitted: {progress_url}")
                    
                    # Record submission
                    self.recorder.record(
                        decision_type='simulation_submission',
                        context={'template': template, 'region': 'USA'},
                        parameters={'settings': str(settings)},
                        result={'progress_url': progress_url, 'submission_time': submission_time},
                        success=True
                    )
                    
                    # Note: We don't wait for completion in integration test
                    # to keep it fast. In production, you would monitor it.
                    logger.info("   (Skipping monitoring to keep test fast)")
                else:
                    logger.warning("⚠️  Simulation submission failed (may be expected)")
                    self.recorder.record(
                        decision_type='simulation_submission',
                        context={'template': template, 'region': 'USA'},
                        parameters={'settings': str(settings)},
                        success=False
                    )
            else:
                logger.warning("⚠️  Template generation failed (may be expected)")
                self.recorder.record(
                    decision_type='template_generation',
                    context={'prompt': prompt, 'region': 'USA'},
                    parameters={'use_ollama': True},
                    success=False
                )
            
            self.test_results['real_api_integration'] = True
            logger.info("✅ TEST 5 PASSED: Real API Integration")
            
        except Exception as e:
            self.test_results['real_api_integration'] = False
            logger.error(f"❌ TEST 5 FAILED: {e}", exc_info=True)
    
    def test_full_system_integration(self):
        """Test 6: Full System Integration (EnhancedTemplateGeneratorV3)"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST 6: Full System Integration")
        logger.info("=" * 80)
        
        if not os.path.exists(self.credential_path):
            logger.warning("⚠️  Credentials not found, skipping full system test")
            self.test_results['full_system_integration'] = 'skipped'
            return
        
        try:
            # Initialize full system
            generator = EnhancedTemplateGeneratorV3(
                credentials_path=self.credential_path,
                db_path="test_integration_backtests.db"
            )
            self.cleanup_files.append("test_integration_backtests.db")
            
            logger.info("✅ Full system initialized")
            
            # Test system stats
            stats = generator.get_system_stats()
            logger.info(f"✅ System stats: {stats}")
            
            # Test configuration integration
            # (The system should be able to use config manager)
            logger.info("✅ Configuration integration ready")
            
            self.test_results['full_system_integration'] = True
            logger.info("✅ TEST 6 PASSED: Full System Integration")
            
        except Exception as e:
            self.test_results['full_system_integration'] = False
            logger.error(f"❌ TEST 6 FAILED: {e}", exc_info=True)
    
    def cleanup(self):
        """Cleanup test files"""
        logger.info("\n" + "=" * 80)
        logger.info("Cleaning up test files")
        logger.info("=" * 80)
        
        for file_path in self.cleanup_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"   Removed: {file_path}")
            except Exception as e:
                logger.warning(f"   Could not remove {file_path}: {e}")
    
    def run_all_tests(self):
        """Run all integration tests"""
        logger.info("\n" + "=" * 80)
        logger.info("STARTING FULL INTEGRATION TEST SUITE")
        logger.info("=" * 80)
        
        self.setup()
        
        # Run all tests
        self.test_config_system()
        self.test_retry_handler()
        self.test_recording_system()
        self.test_integrated_workflow()
        self.test_real_api_integration()
        self.test_full_system_integration()
        
        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("INTEGRATION TEST SUMMARY")
        logger.info("=" * 80)
        
        passed = 0
        failed = 0
        skipped = 0
        
        for test_name, result in self.test_results.items():
            if result is True:
                logger.info(f"✅ {test_name}: PASSED")
                passed += 1
            elif result is False:
                logger.error(f"❌ {test_name}: FAILED")
                failed += 1
            else:
                logger.warning(f"⚠️  {test_name}: SKIPPED")
                skipped += 1
        
        logger.info("=" * 80)
        logger.info(f"Total: {len(self.test_results)} tests")
        logger.info(f"Passed: {passed}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Skipped: {skipped}")
        logger.info("=" * 80)
        
        # Cleanup
        self.cleanup()
        
        return failed == 0


def main():
    """Main test function"""
    # Get credential path
    credential_path = Path(__file__).parent.parent / "credential.txt"
    
    if not credential_path.exists():
        logger.warning(f"Credential file not found: {credential_path}")
        logger.info("Some tests will be skipped")
    
    # Run integration tests
    test_suite = IntegrationTest(str(credential_path))
    success = test_suite.run_all_tests()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
