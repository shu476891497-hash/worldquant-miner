#!/usr/bin/env python3
"""
Test Ollama Integration with Generation Two
Tests Ollama with Qwen code model for alpha generation
"""

import sys
import os
import logging
from pathlib import Path

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from generation_two import OllamaManager, RegionThemeManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_ollama_basic():
    """Test basic Ollama functionality"""
    logger.info("=== Test 1: Basic Ollama Connection ===")
    
    # Try models in order: 1.5b -> 7b -> 32b (smallest first for faster response)
    models_to_try = ["qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:32b"]
    manager = None
    
    for model_name in models_to_try:
        logger.info(f"Trying model: {model_name}")
        manager = OllamaManager(
            base_url="http://localhost:11434",
            model=model_name,
            timeout=120
        )
        
        if manager.is_available:
            logger.info(f"✅ Using model: {model_name}")
            break
        else:
            logger.warning(f"⚠️ {model_name} not available")
    
    if not manager or not manager.is_available:
        logger.error("❌ Ollama is not available")
        logger.info("Run: python start_ollama.py")
        return False
    
    logger.info("✅ Ollama is available")
    
    # Test simple generation
    logger.info("Testing simple code generation...")
    result = manager.generate(
        "Write a Python function to calculate Sharpe ratio",
        system_prompt="You are a Python programming assistant.",
        temperature=0.7,
        max_tokens=200
    )
    
    if result:
        logger.info(f"✅ Generated: {result[:150]}...")
        return True
    else:
        logger.error("❌ Generation failed")
        return False


def test_ollama_alpha_generation():
    """Test alpha template generation"""
    logger.info("\n=== Test 2: Alpha Template Generation ===")
    
    # Try models in order: 1.5b -> 7b -> 32b (smallest first for faster response)
    models_to_try = ["qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:32b"]
    manager = None
    
    for model_name in models_to_try:
        manager = OllamaManager(
            base_url="http://localhost:11434",
            model=model_name,
            timeout=120
        )
        if manager.is_available:
            break
    
    if not manager or not manager.is_available:
        logger.error("❌ Ollama not available")
        return False
    
    logger.info("✅ Ollama is available")
    
    # Test with different regions and themes
    test_cases = [
        {
            "hypothesis": "Momentum-based trading strategy using price and volume",
            "region": "USA",
            "categories": None
        },
        {
            "hypothesis": "Mean reversion strategy for Indian markets",
            "region": "IND",
            "categories": ["Macro", "Model"]  # Week 4 categories
        },
        {
            "hypothesis": "Cross-asset correlation signal",
            "region": "EUR",
            "categories": None
        }
    ]
    
    success_count = 0
    for i, test_case in enumerate(test_cases, 1):
        logger.info(f"\nTest case {i}: {test_case['region']} - {test_case['hypothesis'][:50]}...")
        
        template = manager.generate_template(
            hypothesis=test_case['hypothesis'],
            region=test_case['region'],
            dataset_categories=test_case['categories']
        )
        
        if template:
            logger.info(f"✅ Generated template: {template[:100]}...")
            success_count += 1
        else:
            logger.warning(f"⚠️ Failed to generate template")
    
    logger.info(f"\n✅ Successfully generated {success_count}/{len(test_cases)} templates")
    return success_count > 0


def test_theme_integration():
    """Test theme manager integration"""
    logger.info("\n=== Test 3: Theme Manager Integration ===")
    
    theme_manager = RegionThemeManager()
    
    # Test IND theme
    logger.info("Testing IND Region Theme...")
    if theme_manager.is_theme_active('IND'):
        logger.info("✅ IND theme is active")
        current_week = theme_manager.get_current_ind_week()
        if current_week:
            logger.info(f"  Week: {current_week['week']}")
            logger.info(f"  Categories: {', '.join(current_week['categories'])}")
            logger.info(f"  Dates: {current_week['start_date']} to {current_week['end_date']}")
        
        requirements = theme_manager.get_theme_requirements('IND')
        logger.info(f"  Multiplier: {requirements.get('multiplier', 1.0)}x")
        logger.info(f"  Excluded datasets: {', '.join(requirements.get('excluded_datasets', []))}")
    else:
        logger.info("⚠️ IND theme is not currently active")
    
    # Test ATOM theme
    logger.info("\nTesting ATOM Theme...")
    if theme_manager.is_theme_active('ATOM'):
        logger.info("✅ ATOM theme is active")
        requirements = theme_manager.get_theme_requirements('ATOM')
        logger.info(f"  Multiplier: {requirements.get('multiplier', 1.0)}x")
        logger.info(f"  Requires MaxTrade: {requirements.get('requires_max_trade', False)}")
        logger.info(f"  Requires Single Dataset: {requirements.get('requires_single_dataset', False)}")
    else:
        logger.info("⚠️ ATOM theme is not currently active")
    
    return True


def test_full_integration():
    """Test full integration with template generator"""
    logger.info("\n=== Test 4: Full Integration Test ===")
    
    try:
        from generation_two import TemplateGenerator
        
        # Initialize with Ollama
        # Try models in order: 1.5b -> 7b -> 32b (smallest first for faster response)
        models_to_try = ["qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "qwen2.5-coder:32b"]
        generator = None
        
        for model_name in models_to_try:
            generator = TemplateGenerator(
                credentials_path=None,  # Not needed for this test
                deepseek_api_key=None,
                ollama_url="http://localhost:11434",
                ollama_model=model_name
            )
            if generator.ollama_manager.is_available:
                logger.info(f"Using model: {model_name}")
                break
        
        if not generator.ollama_manager.is_available:
            logger.error("❌ Ollama not available for integration test")
            return False
        
        logger.info("✅ Template generator initialized with Ollama")
        
        # Test generation with theme awareness
        logger.info("Testing template generation with IND theme...")
        template = generator.generate_template_from_prompt(
            "Generate a momentum alpha for Indian markets",
            region="IND",
            use_ollama=True
        )
        
        if template:
            logger.info(f"✅ Generated: {template[:150]}...")
            
            # Get Ollama stats
            stats = generator.ollama_manager.get_stats()
            logger.info(f"\nOllama Statistics:")
            logger.info(f"  Total requests: {stats['total_requests']}")
            logger.info(f"  Success rate: {stats['success_rate']:.2%}")
            logger.info(f"  Available: {stats['is_available']}")
            
            return True
        else:
            logger.error("❌ Template generation failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Integration test failed: {e}", exc_info=True)
        return False


def main():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("Ollama Integration Test Suite")
    logger.info("=" * 60)
    
    results = []
    
    # Test 1: Basic connection
    results.append(("Basic Connection", test_ollama_basic()))
    
    # Test 2: Alpha generation
    results.append(("Alpha Generation", test_ollama_alpha_generation()))
    
    # Test 3: Theme integration
    results.append(("Theme Integration", test_theme_integration()))
    
    # Test 4: Full integration
    results.append(("Full Integration", test_full_integration()))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n🎉 All tests passed! Ollama is ready for Generation Two.")
        return 0
    else:
        logger.warning(f"\n⚠️ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

