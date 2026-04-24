#!/usr/bin/env python3
"""
Test script for Generation Two
Tests the system with credential.txt
"""

import logging
import sys
import os
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import modules directly
from generation_two import (
    SelfOptimizer,
    AlphaQualityMonitor,
    AlphaEvolutionEngine,
    AlphaResult,
    OnTheFlyTester,
    TemplateGenerator,
    SimulatorTester,
    SimulationSettings,
    SimulationResult,
    BacktestStorage,
    AlphaRegrouper,
    AlphaRetrospect,
    EnhancedTemplateGeneratorV3
)

def main():
    """Main test function"""
    # Get credential path
    credential_path = Path(__file__).parent / "credential.txt"
    
    if not credential_path.exists():
        logger.error(f"Credential file not found: {credential_path}")
        logger.info("Please create credential.txt with WorldQuant Brain credentials")
        return
    
    logger.info(f"Using credentials from: {credential_path}")
    
    # Initialize Generation Two with Ollama support (Qwen code model)
    logger.info("Initializing Generation Two with Ollama support...")
    generator = EnhancedTemplateGeneratorV3(
        credentials_path=str(credential_path),
        deepseek_api_key=None,  # Optional - can be set via environment variable
        db_path="generation_two_backtests.db",
        ollama_url="http://localhost:11434",  # Default Ollama URL
        ollama_model="qwen2.5-coder:1.5b"  # Qwen code model (small, fast)
    )
    
    # Check Ollama status
    ollama_stats = generator.template_generator.ollama_manager.get_stats()
    if ollama_stats['is_available']:
        logger.info("✅ Ollama is available and will be used for template generation")
    else:
        logger.info("⚠️ Ollama not available, will use fallback methods")
    
    # Run generation and evolution
    logger.info("Starting generation and evolution...")
    try:
        results = generator.generate_and_evolve(
            regions=['USA', 'EUR'],
            templates_per_region=3,
            max_iterations=5
        )
        
        logger.info(f"Completed: {len(results)} total results")
        
        # Get system statistics
        stats = generator.get_system_stats()
        logger.info("\n=== System Statistics ===")
        logger.info(f"Total results: {stats['total_results']}")
        logger.info(f"Successful alphas: {stats['successful_alphas']}")
        logger.info(f"Evolution cycles: {stats['evolution_cycles']}")
        logger.info(f"Storage stats: {stats['storage_stats']}")
        
        # Ollama statistics
        ollama_stats = stats.get('ollama_stats', {})
        logger.info(f"\n=== Ollama Statistics ===")
        logger.info(f"Available: {ollama_stats.get('is_available', False)}")
        logger.info(f"Total requests: {ollama_stats.get('total_requests', 0)}")
        logger.info(f"Success rate: {ollama_stats.get('success_rate', 0):.2%}")
        logger.info(f"Fallback used: {ollama_stats.get('fallback_used', 0)} times")
        
        # Theme information
        logger.info(f"\n=== Active Themes ===")
        for region, active in stats.get('active_themes', {}).items():
            if active:
                theme_info = generator.theme_manager.get_theme_requirements(region)
                logger.info(f"{region}: Active (Multiplier: {theme_info.get('multiplier', 1.0)}x)")
                if 'required_categories' in theme_info:
                    logger.info(f"  Required categories: {', '.join(theme_info['required_categories'])}")
        
        # Regroup results
        logger.info("\n=== Regrouping Results ===")
        regrouped = generator.regroup_results(by='region')
        for region, results in regrouped.items():
            logger.info(f"{region}: {len(results)} results")
        
        # Retrospective analysis
        logger.info("\n=== Retrospective Analysis ===")
        insights = generator.analyze_retrospect()
        logger.info(f"Total results analyzed: {insights.get('total_results', 0)}")
        logger.info(f"Success rate: {insights.get('success_rate', 0):.2%}")
        logger.info(f"Average Sharpe: {insights.get('avg_sharpe', 0):.3f}")
        
        if 'top_performers' in insights:
            logger.info(f"\nTop Performers:")
            for i, performer in enumerate(insights['top_performers'][:3], 1):
                logger.info(
                    f"  {i}. Sharpe={performer['sharpe']:.3f}, "
                    f"Fitness={performer['fitness']:.3f}, "
                    f"Region={performer['region']}"
                )
        
        logger.info("\n=== Test Completed Successfully ===")
        
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)

if __name__ == "__main__":
    main()

