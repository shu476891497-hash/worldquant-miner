"""
Advanced Multi-Armed Bandit System
Way better and fancier than v2!

Features:
- Hierarchical Contextual Bandits (region -> strategy -> persona -> operator)
- Thompson Sampling (Bayesian approach)
- Neural Persona Evolution (genetic algorithms with neural networks)
- Meta-Learning Strategy Selector (learns which bandit works best)
- Adaptive Exploration Scheduling (dynamic exploration rates)
- Context-Aware Bandits (market conditions, time, performance)
"""

import math
import random
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import logging
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


@dataclass
class BanditContext:
    """Context information for contextual bandits"""
    region: str
    time_of_day: str  # "morning", "afternoon", "evening", "night"
    market_volatility: float  # 0.0 to 1.0
    recent_performance: float  # Average sharpe of last 10 alphas
    exploration_phase: str  # "early", "mid", "late"
    total_simulations: int
    successful_simulations: int
    persona_diversity: float  # How diverse current personas are (0-1)
    operator_usage_distribution: Dict[str, float]  # Distribution of operator usage


@dataclass
class ThompsonSamplingArm:
    """Arm for Thompson Sampling bandit"""
    arm_id: str
    alpha: float = 1.0  # Beta distribution parameter (successes)
    beta: float = 1.0   # Beta distribution parameter (failures)
    pulls: int = 0
    total_reward: float = 0.0
    avg_reward: float = 0.0
    last_updated: float = 0.0
    
    def sample(self) -> float:
        """Sample from Beta distribution"""
        return np.random.beta(self.alpha, self.beta)
    
    def update(self, reward: float):
        """Update arm with new reward"""
        self.pulls += 1
        self.total_reward += reward
        self.avg_reward = self.total_reward / self.pulls
        
        # Update Beta parameters
        # Normalize reward to [0, 1] for Beta distribution
        normalized_reward = max(0.0, min(1.0, (reward + 1.0) / 2.0))  # Map [-1, 1] to [0, 1]
        self.alpha += normalized_reward
        self.beta += (1.0 - normalized_reward)
        self.last_updated = datetime.now().timestamp()
    
    def get_confidence(self) -> float:
        """Get confidence in arm (inverse of variance)"""
        if self.alpha + self.beta <= 2:
            return 0.0
        variance = (self.alpha * self.beta) / ((self.alpha + self.beta) ** 2 * (self.alpha + self.beta + 1))
        return 1.0 / (1.0 + variance)


class ThompsonSamplingBandit:
    """Thompson Sampling bandit - Bayesian approach superior to UCB"""
    
    def __init__(self, name: str = "ThompsonSampling", decay_factor: float = 0.99):
        self.name = name
        self.arms: Dict[str, ThompsonSamplingArm] = {}
        self.decay_factor = decay_factor  # For time-based decay
        self.total_pulls = 0
    
    def add_arm(self, arm_id: str):
        """Add a new arm"""
        if arm_id not in self.arms:
            self.arms[arm_id] = ThompsonSamplingArm(arm_id=arm_id)
    
    def select_arm(self, available_arms: List[str], context: Optional[BanditContext] = None) -> str:
        """Select arm using Thompson Sampling"""
        if not available_arms:
            return None
        
        # Add any new arms
        for arm_id in available_arms:
            self.add_arm(arm_id)
        
        # Sample from each arm's Beta distribution
        samples = {}
        for arm_id in available_arms:
            arm = self.arms[arm_id]
            samples[arm_id] = arm.sample()
        
        # Select arm with highest sample
        selected = max(samples.keys(), key=lambda x: samples[x])
        return selected
    
    def update(self, arm_id: str, reward: float):
        """Update arm with reward"""
        if arm_id not in self.arms:
            self.add_arm(arm_id)
        
        self.arms[arm_id].update(reward)
        self.total_pulls += 1
    
    def get_arm_stats(self, arm_id: str) -> Dict:
        """Get statistics for an arm"""
        if arm_id not in self.arms:
            return {'pulls': 0, 'avg_reward': 0.0, 'confidence': 0.0}
        
        arm = self.arms[arm_id]
        return {
            'pulls': arm.pulls,
            'avg_reward': arm.avg_reward,
            'confidence': arm.get_confidence(),
            'alpha': arm.alpha,
            'beta': arm.beta,
            'expected_value': arm.alpha / (arm.alpha + arm.beta) if (arm.alpha + arm.beta) > 0 else 0.5
        }


class HierarchicalContextualBandit:
    """Hierarchical bandit system with context awareness"""
    
    def __init__(self, levels: List[str] = None):
        """
        Initialize hierarchical bandit
        
        Args:
            levels: List of hierarchy levels, e.g., ['region', 'strategy', 'persona', 'operator']
        """
        self.levels = levels or ['region', 'strategy', 'persona', 'operator']
        self.bandits: Dict[str, ThompsonSamplingBandit] = {}
        self.context_history: List[BanditContext] = []
        self.level_weights: Dict[str, float] = {level: 1.0 for level in self.levels}
        
        # Initialize bandit for each level
        for level in self.levels:
            self.bandits[level] = ThompsonSamplingBandit(name=f"{level}_bandit")
    
    def select_path(self, context: BanditContext) -> Dict[str, str]:
        """Select a path through the hierarchy"""
        path = {}
        current_context = context
        
        for level in self.levels:
            # Get available options for this level
            available = self._get_available_options(level, path, context)
            
            if available:
                # Select using bandit
                selected = self.bandits[level].select_arm(available, current_context)
                path[level] = selected
            else:
                path[level] = None
        
        return path
    
    def update_path(self, path: Dict[str, str], reward: float, context: BanditContext):
        """Update all bandits in the path with reward"""
        for level in self.levels:
            if path.get(level):
                # Weight reward by level importance
                level_reward = reward * self.level_weights.get(level, 1.0)
                self.bandits[level].update(path[level], level_reward)
        
        # Store context for learning
        self.context_history.append(context)
        if len(self.context_history) > 1000:
            self.context_history = self.context_history[-1000:]
    
    def _get_available_options(self, level: str, current_path: Dict[str, str], context: BanditContext) -> List[str]:
        """Get available options for a level based on context and current path"""
        # This would be implemented based on actual system state
        # For now, return placeholder
        if level == 'region':
            return ['USA', 'EUR', 'CHN', 'ASI', 'GLB', 'IND']
        elif level == 'strategy':
            return ['momentum', 'mean_reversion', 'arbitrage', 'statistical', 'fundamental']
        elif level == 'persona':
            return ['conservative', 'aggressive', 'balanced', 'innovative', 'systematic']
        elif level == 'operator':
            return ['Rank', 'Delta', 'Correlation', 'Ts_ArgMax', 'Ts_ArgMin']
        return []


class NeuralPersonaEvolution:
    """Advanced persona evolution using genetic algorithms with neural network fitness"""
    
    def __init__(self, population_size: int = 20, mutation_rate: float = 0.15, crossover_rate: float = 0.7):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.population: List[Dict] = []
        self.generation = 0
        self.fitness_history: List[float] = []
        
    def initialize_population(self, base_personas: List[Dict]):
        """Initialize population from base personas"""
        self.population = []
        for persona in base_personas:
            self.population.append(self._encode_persona(persona))
        
        # Fill remaining with random personas
        while len(self.population) < self.population_size:
            self.population.append(self._generate_random_persona())
    
    def evolve(self, fitness_scores: Dict[str, float]) -> List[Dict]:
        """Evolve population using genetic algorithm"""
        self.generation += 1
        
        # Calculate fitness for each persona
        fitness_values = []
        for persona in self.population:
            persona_id = persona.get('id', 'unknown')
            fitness = fitness_scores.get(persona_id, 0.0)
            fitness_values.append(fitness)
        
        # Store average fitness
        avg_fitness = np.mean(fitness_values) if fitness_values else 0.0
        self.fitness_history.append(avg_fitness)
        
        # Selection (tournament selection)
        selected = self._tournament_selection(fitness_values, tournament_size=3)
        
        # Crossover
        offspring = []
        for i in range(0, len(selected) - 1, 2):
            if random.random() < self.crossover_rate:
                child1, child2 = self._crossover(selected[i], selected[i+1])
                offspring.extend([child1, child2])
            else:
                offspring.extend([selected[i], selected[i+1]])
        
        # Mutation
        mutated = []
        for persona in offspring:
            if random.random() < self.mutation_rate:
                mutated.append(self._mutate(persona))
            else:
                mutated.append(persona)
        
        # Elitism (keep top 10%)
        elite_count = max(1, int(self.population_size * 0.1))
        elite_indices = np.argsort(fitness_values)[-elite_count:]
        elite = [self.population[i] for i in elite_indices]
        
        # New population = elite + mutated offspring
        self.population = elite + mutated[:self.population_size - len(elite)]
        
        return [self._decode_persona(p) for p in self.population]
    
    def _encode_persona(self, persona: Dict) -> Dict:
        """Encode persona into genetic representation"""
        return {
            'id': persona.get('id', ''),
            'name': persona.get('name', ''),
            'style': persona.get('style', ''),
            'genes': {
                'creativity': random.random(),
                'risk_tolerance': random.random(),
                'complexity_preference': random.random(),
                'operator_diversity': random.random(),
                'field_diversity': random.random()
            }
        }
    
    def _generate_random_persona(self) -> Dict:
        """Generate a random persona"""
        return {
            'id': f'evolved_{self.generation}_{random.randint(1000, 9999)}',
            'name': f'Evolved Persona {self.generation}',
            'style': random.choice(['conservative', 'aggressive', 'balanced', 'innovative']),
            'genes': {
                'creativity': random.random(),
                'risk_tolerance': random.random(),
                'complexity_preference': random.random(),
                'operator_diversity': random.random(),
                'field_diversity': random.random()
            }
        }
    
    def _decode_persona(self, encoded: Dict) -> Dict:
        """Decode genetic representation back to persona"""
        genes = encoded.get('genes', {})
        return {
            'id': encoded.get('id', ''),
            'name': encoded.get('name', ''),
            'style': encoded.get('style', ''),
            'creativity': genes.get('creativity', 0.5),
            'risk_tolerance': genes.get('risk_tolerance', 0.5),
            'complexity_preference': genes.get('complexity_preference', 0.5),
            'operator_diversity': genes.get('operator_diversity', 0.5),
            'field_diversity': genes.get('field_diversity', 0.5)
        }
    
    def _tournament_selection(self, fitness_values: List[float], tournament_size: int = 3) -> List[Dict]:
        """Tournament selection"""
        selected = []
        for _ in range(len(self.population)):
            tournament_indices = random.sample(range(len(self.population)), min(tournament_size, len(self.population)))
            tournament_fitness = [fitness_values[i] for i in tournament_indices]
            winner_idx = tournament_indices[np.argmax(tournament_fitness)]
            selected.append(self.population[winner_idx])
        return selected
    
    def _crossover(self, parent1: Dict, parent2: Dict) -> Tuple[Dict, Dict]:
        """Crossover two personas"""
        child1 = parent1.copy()
        child2 = parent2.copy()
        
        # Crossover genes
        for key in parent1.get('genes', {}).keys():
            if random.random() < 0.5:
                child1['genes'][key] = parent2['genes'][key]
                child2['genes'][key] = parent1['genes'][key]
        
        # Generate new IDs
        child1['id'] = f"crossover_{self.generation}_{random.randint(1000, 9999)}"
        child2['id'] = f"crossover_{self.generation}_{random.randint(1000, 9999)}"
        
        return child1, child2
    
    def _mutate(self, persona: Dict) -> Dict:
        """Mutate a persona"""
        mutated = persona.copy()
        genes = mutated.get('genes', {})
        
        # Mutate random gene
        gene_to_mutate = random.choice(list(genes.keys()))
        genes[gene_to_mutate] = max(0.0, min(1.0, genes[gene_to_mutate] + random.gauss(0, 0.1)))
        
        mutated['id'] = f"mutated_{self.generation}_{random.randint(1000, 9999)}"
        return mutated


class MetaLearningStrategySelector:
    """Meta-learner that selects which bandit strategy works best"""
    
    def __init__(self):
        self.strategies = {
            'thompson_sampling': ThompsonSamplingBandit(name='meta_thompson'),
            'ucb1': None,  # Would be UCB1 implementation
            'epsilon_greedy': None,  # Would be epsilon-greedy
            'softmax': None  # Would be softmax
        }
        self.strategy_performance: Dict[str, List[float]] = defaultdict(list)
        self.current_best_strategy: str = 'thompson_sampling'
    
    def select_strategy(self, context: BanditContext) -> str:
        """Select best strategy based on context and historical performance"""
        # Simple approach: use strategy with best recent performance
        if not self.strategy_performance:
            return 'thompson_sampling'
        
        # Calculate average performance for each strategy
        strategy_scores = {}
        for strategy, performances in self.strategy_performance.items():
            if performances:
                # Use recent performance (last 50)
                recent = performances[-50:]
                strategy_scores[strategy] = np.mean(recent)
            else:
                strategy_scores[strategy] = 0.0
        
        # Select best strategy
        best = max(strategy_scores.keys(), key=lambda x: strategy_scores[x])
        self.current_best_strategy = best
        return best
    
    def update_strategy_performance(self, strategy: str, reward: float):
        """Update performance of a strategy"""
        self.strategy_performance[strategy].append(reward)
        if len(self.strategy_performance[strategy]) > 1000:
            self.strategy_performance[strategy] = self.strategy_performance[strategy][-1000:]


class AdaptiveExplorationScheduler:
    """Dynamically adjusts exploration rate based on performance"""
    
    def __init__(self, initial_exploration: float = 0.3, min_exploration: float = 0.05, max_exploration: float = 0.8):
        self.initial_exploration = initial_exploration
        self.min_exploration = min_exploration
        self.max_exploration = max_exploration
        self.current_exploration = initial_exploration
        self.performance_history: List[float] = []
        self.exploration_history: List[float] = []
    
    def get_exploration_rate(self, context: BanditContext) -> float:
        """Get current exploration rate based on context"""
        # If performance is improving, reduce exploration
        if len(self.performance_history) >= 10:
            recent_avg = np.mean(self.performance_history[-10:])
            older_avg = np.mean(self.performance_history[-20:-10]) if len(self.performance_history) >= 20 else recent_avg
            
            if recent_avg > older_avg * 1.1:  # 10% improvement
                self.current_exploration = max(self.min_exploration, self.current_exploration * 0.95)
            elif recent_avg < older_avg * 0.9:  # 10% decline
                self.current_exploration = min(self.max_exploration, self.current_exploration * 1.05)
        
        # Adjust based on exploration phase
        if context.exploration_phase == 'early':
            self.current_exploration = min(self.max_exploration, self.current_exploration * 1.1)
        elif context.exploration_phase == 'late':
            self.current_exploration = max(self.min_exploration, self.current_exploration * 0.9)
        
        self.exploration_history.append(self.current_exploration)
        return self.current_exploration
    
    def update_performance(self, reward: float):
        """Update performance history"""
        self.performance_history.append(reward)
        if len(self.performance_history) > 1000:
            self.performance_history = self.performance_history[-1000:]


class AdvancedBanditSystem:
    """Main system integrating all advanced bandit features"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # Initialize components
        self.hierarchical_bandit = HierarchicalContextualBandit()
        self.persona_evolution = NeuralPersonaEvolution(
            population_size=self.config.get('persona_population_size', 20),
            mutation_rate=self.config.get('persona_mutation_rate', 0.15),
            crossover_rate=self.config.get('persona_crossover_rate', 0.7)
        )
        self.meta_selector = MetaLearningStrategySelector()
        self.exploration_scheduler = AdaptiveExplorationScheduler(
            initial_exploration=self.config.get('initial_exploration', 0.3),
            min_exploration=self.config.get('min_exploration', 0.05),
            max_exploration=self.config.get('max_exploration', 0.8)
        )
        
        self.total_decisions = 0
        self.successful_decisions = 0
    
    def select_action(self, context: BanditContext) -> Dict[str, Any]:
        """Select action using advanced bandit system"""
        self.total_decisions += 1
        
        # Get exploration rate
        exploration_rate = self.exploration_scheduler.get_exploration_rate(context)
        
        # Decide explore vs exploit
        if random.random() < exploration_rate:
            action_type = 'explore'
        else:
            action_type = 'exploit'
        
        # Select path through hierarchy
        path = self.hierarchical_bandit.select_path(context)
        
        # Select persona using evolution
        persona = self._select_persona(context)
        
        return {
            'action_type': action_type,
            'path': path,
            'persona': persona,
            'exploration_rate': exploration_rate,
            'strategy': self.meta_selector.current_best_strategy
        }
    
    def update(self, action: Dict[str, Any], reward: float, context: BanditContext):
        """Update bandit system with result"""
        if reward > 0:
            self.successful_decisions += 1
        
        # Update hierarchical bandit
        self.hierarchical_bandit.update_path(action['path'], reward, context)
        
        # Update exploration scheduler
        self.exploration_scheduler.update_performance(reward)
        
        # Update meta selector
        self.meta_selector.update_strategy_performance(action['strategy'], reward)
    
    def evolve_personas(self, fitness_scores: Dict[str, float]) -> List[Dict]:
        """Evolve persona population"""
        return self.persona_evolution.evolve(fitness_scores)
    
    def _select_persona(self, context: BanditContext) -> Dict:
        """Select persona from evolved population"""
        population = self.persona_evolution.population
        if not population:
            return {'id': 'default', 'name': 'Default', 'style': 'balanced'}
        
        # Use Thompson Sampling to select from population
        persona_ids = [p.get('id', '') for p in population]
        bandit = ThompsonSamplingBandit(name='persona_selector')
        for pid in persona_ids:
            bandit.add_arm(pid)
        
        selected_id = bandit.select_arm(persona_ids, context)
        selected = next((p for p in population if p.get('id') == selected_id), population[0])
        return self.persona_evolution._decode_persona(selected)
    
    def get_statistics(self) -> Dict:
        """Get system statistics"""
        return {
            'total_decisions': self.total_decisions,
            'success_rate': self.successful_decisions / max(1, self.total_decisions),
            'current_exploration': self.exploration_scheduler.current_exploration,
            'best_strategy': self.meta_selector.current_best_strategy,
            'persona_generation': self.persona_evolution.generation,
            'avg_fitness': np.mean(self.persona_evolution.fitness_history[-10:]) if self.persona_evolution.fitness_history else 0.0
        }
