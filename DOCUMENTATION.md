# Generation Two: Complete Documentation

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Architecture](#architecture)
4. [Core Components](#core-components)
5. [Features](#features)
6. [Installation](#installation)
7. [Usage](#usage)
8. [Configuration](#configuration)
9. [Building & Release](#building--release)
10. [Troubleshooting](#troubleshooting)

---

## Overview

Generation Two is a self-optimizing, modular alpha mining system designed for WorldQuant Brain. It extends Generation One with advanced capabilities including:

- **Self-Optimization**: Adaptive parameter tuning based on performance
- **Genetic Evolution**: Genetic algorithm-based alpha evolution
- **On-the-Fly Testing**: Immediate validation of evolved alphas
- **Quality Monitoring**: Performance tracking and degradation detection
- **Modular Architecture**: Separated concerns for maintainability
- **Smart Ollama Integration**: Local LLM with automatic fallback
- **Cyberpunk GUI**: Modern graphical interface for system control
- **Continuous Mining**: Automated 24/7 alpha discovery
- **Template Validation**: Self-correcting AST with error learning
- **Expression Compiler**: Multi-stage compilation pipeline

---

## Quick Start

### Prerequisites

- Python 3.8 or higher
- WorldQuant Brain credentials
- (Optional) Ollama for local LLM generation

### Basic Setup

1. **Install Dependencies**
```bash
cd generation_two
pip install -r requirements.txt
```

2. **Configure Credentials**
Create `credential.txt` in the project root:
```json
["your.email@worldquant.com", "your_password"]
```

3. **Launch GUI**
```bash
python gui/run_gui.py [credential_path]
```

### Ollama Setup (Optional)

1. **Install Ollama**: https://ollama.ai
2. **Pull Model**:
```bash
ollama pull qwen2.5-coder:1.5b
```
3. **Start Ollama**:
```bash
ollama serve
```

---

## Architecture

### Modular Structure

```
generation_two/
├── core/                    # Core generation components
│   ├── template_generator.py      # Alpha expression generation
│   ├── simulator_tester.py        # Simulation submission & monitoring
│   ├── template_validator.py      # Template validation & error correction
│   ├── expression_compiler.py      # Multi-stage compilation pipeline
│   ├── enhanced_template_generator_v3.py  # Main orchestrator
│   ├── mining/                    # Mining coordination
│   ├── config/                    # Configuration management
│   ├── utils/                     # Reusable utilities
│   └── recorder/                  # Decision recording
│
├── evolution/               # Evolution and optimization
│   ├── self_optimizer.py          # Adaptive parameter tuning
│   ├── alpha_evolution_engine.py  # Genetic algorithm evolution
│   ├── alpha_quality_monitor.py   # Performance tracking
│   └── on_the_fly_tester.py      # Immediate testing
│
├── storage/                 # Storage and analysis
│   ├── backtest_storage.py        # SQLite-based storage
│   ├── regroup.py                 # Result grouping
│   └── retrospect.py              # Historical analysis
│
├── ollama/                  # Ollama integration
│   ├── ollama_manager.py          # Smart Ollama management
│   └── region_theme_manager.py     # Theme support
│
├── data_fetcher/            # Data fetching
│   ├── operator_fetcher.py         # Operator loading
│   ├── data_field_fetcher.py      # Field fetching
│   └── smart_search.py            # Smart search engine
│
├── gui/                     # Cyberpunk GUI
│   ├── main_window.py              # Main window
│   ├── run_gui.py                  # GUI launcher
│   └── components/                 # GUI components
│
└── tests/                   # Test files
```

### Module Dependencies

```
EnhancedTemplateGeneratorV3 (Orchestrator)
├── TemplateGenerator
│   ├── OllamaManager
│   ├── DataFieldFetcher
│   └── SmartSearchEngine
├── SimulatorTester
│   └── ThreadPoolExecutor (concurrent)
├── Evolution Components
│   ├── SelfOptimizer
│   ├── AlphaEvolutionEngine
│   └── OnTheFlyTester
├── Storage Components
│   ├── BacktestStorage
│   └── DecisionRecorder
└── GUI (CyberpunkGUI)
    ├── DashboardPanel
    ├── EvolutionPanel
    ├── ConfigPanel
    ├── MonitorPanel
    └── DatabasePanel
```

---

## Core Components

### TemplateGenerator

Generates alpha expressions using AI/LLM (Ollama, DeepSeek, or fallback).

**Features:**
- Ollama integration with smart fallback
- DeepSeek API support
- Theme-aware generation
- Duplicate detection
- Field placeholder replacement

**Usage:**
```python
from generation_two.core.template_generator import TemplateGenerator

generator = TemplateGenerator(credentials_path="credential.txt")
template = generator.generate_template_from_prompt("momentum-based alpha")
```

### SimulatorTester

Submits templates for simulation and monitors results with concurrent execution.

**Features:**
- Concurrent simulation execution (ThreadPoolExecutor)
- Result monitoring with progress callbacks
- Future-based async operations
- Rate limiting
- Automatic retry logic

**Usage:**
```python
from generation_two.core.simulator_tester import SimulatorTester, SimulationSettings

tester = SimulatorTester(session, region_configs)
settings = SimulationSettings(region="USA", delay=1)
future = tester.simulate_template_concurrent(template, "USA", settings)
result = future.result()
```

### TemplateValidator

Validates and corrects templates using self-correcting AST and prompt engineering.

**Features:**
- AST-based validation
- Self-correcting error handling
- Prompt engineering for fixes
- Error learning and storage
- Database knowledge integration

**Usage:**
```python
from generation_two.core.template_validator import TemplateValidator

validator = TemplateValidator(operators=operators, data_fields=fields)
is_valid, error_msg, warnings = validator.validate_template(template, region="USA")
```

### ExpressionCompiler

Multi-stage compilation pipeline: Lexical Analysis → Parsing → Semantic Analysis → IR → Code Generation → Optimization.

**Stages:**
1. **Lexical Analysis**: Tokenizes source code
2. **Parsing**: Builds Abstract Syntax Tree (AST)
3. **Semantic Analysis**: Validates operators, fields, types
4. **IR Generation**: Creates intermediate representation
5. **Code Generation**: Generates final FASTEXPR
6. **Optimization**: Applies optimizations (optional)

**Usage:**
```python
from generation_two.core.expression_compiler import ExpressionCompiler

compiler = ExpressionCompiler(parser)
result = compiler.compile("ts_rank(field_id, 20)", optimize=True)
if result.success:
    print(result.final_expression)
```

### MiningCoordinator

Coordinates continuous alpha mining with search strategies and duplicate detection.

**Features:**
- Multiple search strategies (BFS, DFS, Random)
- Duplicate detection
- Correlation tracking
- Slot-based concurrent execution
- Daily simulation limits

---

## Features

### Self-Optimization

Adaptive parameter tuning based on performance metrics:
- Optimizes every 100 simulations
- Adjusts exploration/exploitation balance
- Performance-based optimization
- Dynamic parameter adjustment

### Genetic Algorithm Evolution

Evolves successful alphas through:
- **Tournament Selection**: Selects best parents
- **Crossover**: Combines successful expressions
- **Mutation**: Multiple mutation types
- **Elitism**: Preserves top 10% of population

### On-the-Fly Testing

Immediate validation of evolved alphas:
- Fast validation (1 year vs 5 years)
- Queue management
- Asynchronous processing
- Real-time feedback

### Quality Monitoring

Tracks alpha performance over time:
- Performance tracking
- Degradation detection (20% drop threshold)
- Health scores (0-1 scale)
- Stability metrics

### Smart Ollama Integration

Local LLM with intelligent fallback:
- Health monitoring
- Rate limiting
- Automatic fallback chain (Ollama → DeepSeek → Simple)
- Connection pooling
- Smart retry logic

### Template Validation & Correction

Self-correcting system that learns from errors:
- **AST-based correction**: Structural fixes
- **Prompt engineering**: AI-powered fixes
- **Database knowledge**: Learned compatibility rules
- **Error learning**: Stores patterns for future prevention

**Error Types Handled:**
- Event input incompatibility
- Missing lookback parameters
- Missing commas
- Unknown variables
- Unknown operators
- Invalid input counts

### Continuous Mining

Automated 24/7 alpha discovery:
- Multi-region support (USA, EUR, CHN, ASI, GLB, IND)
- Concurrent slot-based execution
- Daily simulation limits (5,000/day)
- Duplicate detection
- Automatic refeed correction
- Real-time progress monitoring

---

## Installation

### Standard Installation

```bash
cd generation_two
pip install -r requirements.txt
```

### Development Installation

```bash
pip install -r requirements.txt
pip install pytest black flake8
```

### Build Executables

See [BUILD.md](BUILD.md) for detailed build instructions.

**Windows (EXE):**
```bash
python build.py --exe
```

**Linux (DEB):**
```bash
python build.py --deb
```

**macOS (DMG):**
```bash
python build.py --dmg
```

---

## Usage

### Basic Usage

```python
from generation_two import EnhancedTemplateGeneratorV3

# Initialize
generator = EnhancedTemplateGeneratorV3(
    credentials_path="credential.txt",
    ollama_url="http://localhost:11434",
    ollama_model="qwen2.5-coder:1.5b"
)

# Generate and evolve alphas
results = generator.generate_and_evolve(
    regions=["USA", "EUR"],
    templates_per_region=5,
    max_iterations=10
)

# Get statistics
stats = generator.get_system_stats()
print(f"Total results: {stats['total_results']}")
```

### GUI Usage

```bash
# Launch GUI
python gui/run_gui.py [credential_path]

# GUI Features:
# - Dashboard: Real-time statistics
# - Evolution: Control self-evolution
# - Config: Edit configuration live
# - Monitor: System logs
# - Database: Browse backtest results
```

### Continuous Mining

```python
from generation_two.gui.components.workflow_steps.step6_mining_modules import MiningEngine

engine = MiningEngine(generator, simulator_tester, ...)
engine.start()  # Starts continuous mining
# ... mining runs indefinitely ...
engine.stop()   # Stops mining
```

---

## Configuration

### Credential Management

Credentials are loaded from:
1. Command-line argument: `python run_gui.py credential.txt`
2. Standard locations: `credential.txt`, `credentials.txt`
3. User home directory
4. Interactive login dialog (if not found)

**Security:**
- Credentials never embedded in code
- Stored only in memory
- Never logged
- External file or user input only

### Ollama Configuration

```python
generator = EnhancedTemplateGeneratorV3(
    ollama_url="http://localhost:11434",
    ollama_model="qwen2.5-coder:1.5b",  # or 7b, 32b
    rate_limit=2.0  # seconds between requests
)
```

### Database Configuration

Supports multiple database backends:
- **SQLite**: Default, file-based (`generation_two_backtests.db`)
- **JSON**: File-based JSON storage
- **Remote URL**: HTTP/HTTPS endpoint

Configure via GUI Database Panel or code:
```python
from generation_two.storage.backtest_storage import BacktestStorage

storage = BacktestStorage(db_path="backtests.db")
```

---

## Building & Release

### Pre-Release Checklist

1. **Security Verification**
   ```bash
   python verify_secrets.py
   ```

2. **Build All Formats**
   ```bash
   python build.py --all
   ```

3. **Test Executables**
   - Test on clean system (no Python)
   - Verify GUI launches
   - Test authentication
   - Verify no credentials bundled

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for complete checklist.

### Release Process

1. Update version in `setup.py` and `pyproject.toml`
2. Create git tag: `git tag -a v1.0.0 -m "Release v1.0.0"`
3. Build all formats
4. Create GitHub release with artifacts
5. Push tag: `git push origin v1.0.0`

---

## Troubleshooting

### Common Issues

**Ollama Connection Failed**
- Check if Ollama is running: `ollama list`
- Verify URL: `http://localhost:11434`
- Check firewall settings

**Authentication Failed**
- Verify credentials file format: `["username", "password"]`
- Check credentials are valid
- Try interactive login dialog

**Template Generation Fails**
- Check Ollama model is available: `ollama list`
- Verify operators loaded: Check `constants/operatorRAW.json`
- Check data fields available for region

**Simulation Errors**
- Check template syntax
- Verify field IDs are valid for region
- Check operator compatibility
- Review error logs for details

**Database Errors**
- Check database file permissions
- Verify SQLite is available
- Check disk space

### Debug Mode

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Additional Resources

- **Specification**: `spec/main.tex` - Complete LaTeX specification
- **Architecture**: `spec/architecture.tex` - Architecture documentation
- **Expression Compiler**: `spec/expression_compiler.tex` - Compiler specification
- **Smart Search**: `spec/smart_search.tex` - Search engine specification

---

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

---

## Contributing

See the main [README.md](../README.md) for contribution guidelines.

---

*Last Updated: 2025-01-XX*
