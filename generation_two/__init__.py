"""
Generation Two: Self-Optimization and Genetic Evolution
Modular implementation with organized tool structure
"""

# Core components
from .core import (
    TemplateGenerator,
    SimulatorTester,
    SimulationSettings,
    SimulationResult,
    EnhancedTemplateGeneratorV3
)

# Evolution components
from .evolution import (
    SelfOptimizer,
    AlphaQualityMonitor,
    AlphaEvolutionEngine,
    AlphaResult,
    OnTheFlyTester
)

# Storage components
from .storage import (
    BacktestStorage,
    BacktestRecord,
    AlphaRegrouper,
    AlphaRetrospect,
    ClusterAnalyzer,
    Cluster
)

# Ollama components
from .ollama import (
    OllamaManager,
    RegionThemeManager,
    DuplicateDetector,
    ExpressionSignature
)

# Core utilities
from .core.utils import (
    RetryHandler,
    RetryConfig,
    RetryStrategy,
    RequestHandler,
    RequestConfig
)

# Configuration system
from .core.config import (
    ConfigManager,
    ConfigSection,
    load_config,
    save_config
)

# Recording system
from .core.recorder import (
    DecisionRecorder,
    DecisionRecord,
    AuditLogger
)

# Self-evolution system
from .self_evolution import (
    CodeGenerator,
    ModuleTemplate,
    CodeEvaluator,
    EvaluationResult,
    EvolutionExecutor
)

# GUI (optional, requires tkinter)
try:
    from .gui import CyberpunkGUI
    HAS_GUI = True
except ImportError:
    HAS_GUI = False
    CyberpunkGUI = None

# Data fetcher
from .data_fetcher import (
    OperatorFetcher,
    DataFieldFetcher,
    SmartSearchEngine
)

__all__ = [
    # Core
    'TemplateGenerator',
    'SimulatorTester',
    'SimulationSettings',
    'SimulationResult',
    'EnhancedTemplateGeneratorV3',
    # Evolution
    'SelfOptimizer',
    'AlphaQualityMonitor',
    'AlphaEvolutionEngine',
    'AlphaResult',
    'OnTheFlyTester',
    # Storage
    'BacktestStorage',
    'BacktestRecord',
    'AlphaRegrouper',
    'AlphaRetrospect',
    'ClusterAnalyzer',
    'Cluster',
    # Ollama
    'OllamaManager',
    'RegionThemeManager',
    'DuplicateDetector',
    'ExpressionSignature',
    # Utilities
    'RetryHandler',
    'RetryConfig',
    'RetryStrategy',
    'RequestHandler',
    'RequestConfig',
    # Configuration
    'ConfigManager',
    'ConfigSection',
    'load_config',
    'save_config',
    # Recording
    'DecisionRecorder',
    'DecisionRecord',
    'AuditLogger',
    # Self-Evolution
    'CodeGenerator',
    'ModuleTemplate',
    'CodeEvaluator',
    'EvaluationResult',
    'EvolutionExecutor',
    # GUI
    'CyberpunkGUI',
    'HAS_GUI',
    # Data Fetcher
    'OperatorFetcher',
    'DataFieldFetcher',
    'SmartSearchEngine'
]
