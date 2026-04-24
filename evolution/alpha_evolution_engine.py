"""
Genetic Algorithm for Alpha Evolution
Evolves successful alphas through crossover and mutation
"""

import random
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)


@dataclass
class AlphaResult:
    """Result from alpha testing"""
    template: str
    sharpe: float
    fitness: float
    turnover: float
    region: str = ""
    success: bool = True


class AlphaEvolutionEngine:
    """
    Genetic algorithm engine for evolving alpha expressions
    
    Uses tournament selection, crossover, and mutation to evolve
    successful alpha expressions into potentially better ones.
    """
    
    def __init__(self, mutation_rate: float = 0.1, crossover_rate: float = 0.7):
        """
        Initialize evolution engine
        
        Args:
            mutation_rate: Probability of mutation (0-1)
            crossover_rate: Probability of crossover (0-1)
        """
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.population: List[AlphaResult] = []  # Current population of alphas
        self.fitness_scores: Dict[str, float] = {}  # {alpha_expression: fitness_score}
        
        # Common operators and fields for mutation
        self.operators = ['+', '-', '*', '/', 'max', 'min', 'ts_rank', 'ts_delta', 
                         'ts_mean', 'ts_std', 'ts_corr', 'ts_cov', 'rank', 'delta']
        self.fields = ['close', 'open', 'high', 'low', 'volume', 'vwap', 
                      'returns', 'adv20', 'adv60']
        
    def initialize_population(
        self, 
        initial_alphas: List[AlphaResult], 
        population_size: int = 50
    ):
        """
        Initialize population with successful alphas
        
        Args:
            initial_alphas: List of successful alpha results
            population_size: Target population size
        """
        if len(initial_alphas) == 0:
            logger.warning("No initial alphas provided")
            return
        
        # Select top performers
        sorted_alphas = sorted(
            initial_alphas, 
            key=lambda a: a.sharpe * a.fitness, 
            reverse=True
        )
        self.population = sorted_alphas[:population_size]
        
        # Calculate fitness scores
        for alpha in self.population:
            self.fitness_scores[alpha.template] = (
                alpha.sharpe * 0.5 + 
                alpha.fitness * 0.3 + 
                (1.0 / (1.0 + alpha.turnover)) * 0.2
            )
        
        logger.info(
            f"Initialized population with {len(self.population)} alphas, "
            f"top fitness: {max(self.fitness_scores.values()):.3f}"
        )
    
    def select_parents(self, num_parents: int = 2) -> List[str]:
        """
        Select parents using tournament selection
        
        Args:
            num_parents: Number of parents to select
            
        Returns:
            List of parent alpha expressions
        """
        if len(self.population) == 0:
            return []
        
        parents = []
        tournament_size = min(3, len(self.population))
        
        for _ in range(num_parents):
            # Tournament selection
            tournament = random.sample(
                self.population, 
                tournament_size
            )
            winner = max(
                tournament, 
                key=lambda a: self.fitness_scores.get(a.template, 0)
            )
            parents.append(winner.template)
        
        return parents
    
    def parse_expression(self, expression: str) -> Dict[str, Any]:
        """
        Parse alpha expression into a tree structure
        
        Args:
            expression: Alpha expression string
            
        Returns:
            Parsed tree structure
        """
        # Simple parsing - extract components
        # This is a simplified parser; full implementation would use AST
        tree = {
            'expression': expression,
            'operators': [],
            'fields': [],
            'parameters': []
        }
        
        # Extract operators
        for op in self.operators:
            if op in expression:
                tree['operators'].append(op)
        
        # Extract fields
        for field in self.fields:
            if field in expression:
                tree['fields'].append(field)
        
        # Extract numeric parameters
        numbers = re.findall(r'\d+', expression)
        tree['parameters'] = [int(n) for n in numbers]
        
        return tree
    
    def select_random_subtree(self, tree: Dict[str, Any]) -> str:
        """Select a random component from the tree"""
        components = []
        if tree['operators']:
            components.extend(tree['operators'])
        if tree['fields']:
            components.extend(tree['fields'])
        if components:
            return random.choice(components)
        return ""
    
    def replace_subtree(
        self, 
        tree1: Dict[str, Any], 
        subtree1: str, 
        subtree2: str
    ) -> Dict[str, Any]:
        """Replace a subtree in tree1 with subtree2"""
        # Simplified implementation
        new_tree = tree1.copy()
        if subtree1 in new_tree['operators']:
            new_tree['operators'].remove(subtree1)
            new_tree['operators'].append(subtree2)
        elif subtree1 in new_tree['fields']:
            new_tree['fields'].remove(subtree1)
            new_tree['fields'].append(subtree2)
        return new_tree
    
    def expression_to_string(self, tree: Dict[str, Any]) -> str:
        """Convert tree back to expression string"""
        # Simplified - return original if available
        if 'expression' in tree:
            return tree['expression']
        # Otherwise reconstruct (simplified)
        return "close"
    
    def crossover(self, parent1: str, parent2: str) -> str:
        """
        Crossover two alpha expressions
        
        Args:
            parent1: First parent expression
            parent2: Second parent expression
            
        Returns:
            Child expression
        """
        if random.random() > self.crossover_rate:
            return parent1  # No crossover
        
        # Parse expressions into trees
        tree1 = self.parse_expression(parent1)
        tree2 = self.parse_expression(parent2)
        
        # Select random component from each parent
        subtree1 = self.select_random_subtree(tree1)
        subtree2 = self.select_random_subtree(tree2)
        
        if not subtree1 or not subtree2:
            return parent1  # Can't crossover
        
        # Replace component in parent1 with component from parent2
        child_tree = self.replace_subtree(tree1, subtree1, subtree2)
        
        # Simple crossover: combine parts of both expressions
        # Extract meaningful parts
        parts1 = re.findall(r'\w+\([^)]+\)', parent1)
        parts2 = re.findall(r'\w+\([^)]+\)', parent2)
        
        if parts1 and parts2:
            # Take random parts from each parent
            from_parent1 = random.choice(parts1)
            from_parent2 = random.choice(parts2)
            # Combine with an operator
            child = f"({from_parent1} + {from_parent2}) / 2"
        else:
            # Fallback: simple combination
            child = f"({parent1} + {parent2}) / 2"
        
        return child
    
    def replace_random_operator(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        """Replace a random operator"""
        if tree['operators']:
            old_op = random.choice(tree['operators'])
            new_op = random.choice([o for o in self.operators if o != old_op])
            tree['operators'].remove(old_op)
            tree['operators'].append(new_op)
        return tree
    
    def replace_random_field(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        """Replace a random field"""
        if tree['fields']:
            old_field = random.choice(tree['fields'])
            new_field = random.choice([f for f in self.fields if f != old_field])
            tree['fields'].remove(old_field)
            tree['fields'].append(new_field)
        return tree
    
    def modify_random_parameter(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        """Modify a random numeric parameter"""
        if tree['parameters']:
            idx = random.randint(0, len(tree['parameters']) - 1)
            # Modify by ±20%
            change = random.choice([-0.2, 0.2])
            tree['parameters'][idx] = int(tree['parameters'][idx] * (1 + change))
        return tree
    
    def add_random_operator(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new operator layer"""
        new_op = random.choice(self.operators)
        tree['operators'].append(new_op)
        return tree
    
    def remove_random_operator(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        """Remove an operator layer"""
        if tree['operators']:
            tree['operators'].pop()
        return tree
    
    def mutate(self, expression: str) -> str:
        """
        Mutate an alpha expression
        
        Args:
            expression: Alpha expression to mutate
            
        Returns:
            Mutated expression
        """
        if random.random() > self.mutation_rate:
            return expression  # No mutation
        
        tree = self.parse_expression(expression)
        
        # Mutation operations
        mutation_type = random.choice([
            'replace_operator',
            'replace_field',
            'modify_parameter',
            'add_operator',
            'remove_operator'
        ])
        
        if mutation_type == 'replace_operator':
            tree = self.replace_random_operator(tree)
        elif mutation_type == 'replace_field':
            tree = self.replace_random_field(tree)
        elif mutation_type == 'modify_parameter':
            tree = self.modify_random_parameter(tree)
        elif mutation_type == 'add_operator':
            tree = self.add_random_operator(tree)
        elif mutation_type == 'remove_operator':
            tree = self.remove_random_operator(tree)
        
        # Reconstruct expression (simplified)
        mutated = self.expression_to_string(tree)
        
        # Simple mutation: modify numbers in expression
        def modify_number(match):
            num = int(match.group())
            change = random.choice([-2, -1, 1, 2])
            return str(max(1, num + change))
        
        mutated = re.sub(r'\d+', modify_number, mutated)
        
        return mutated
    
    def evolve_generation(self) -> List[str]:
        """
        Evolve one generation
        
        Returns:
            List of evolved alpha expressions
        """
        if len(self.population) == 0:
            logger.warning("No population to evolve")
            return []
        
        new_population = []
        
        # Elitism: keep top 10%
        elite_count = max(1, int(len(self.population) * 0.1))
        elite = sorted(
            self.population, 
            key=lambda a: self.fitness_scores.get(a.template, 0),
            reverse=True
        )[:elite_count]
        new_population.extend([a.template for a in elite])
        
        logger.info(f"Keeping {elite_count} elite alphas")
        
        # Generate offspring
        while len(new_population) < len(self.population):
            # Select parents
            parents = self.select_parents(2)
            
            if len(parents) < 2:
                # Not enough parents, use random from population
                parents = [random.choice(self.population).template] * 2
            
            # Crossover
            child = self.crossover(parents[0], parents[1])
            
            # Mutate
            child = self.mutate(child)
            
            new_population.append(child)
        
        logger.info(f"Evolved generation: {len(new_population)} alphas")
        return new_population
    
    def update_fitness(self, alpha_expression: str, result: AlphaResult):
        """
        Update fitness score for an alpha
        
        Args:
            alpha_expression: Alpha expression
            result: Test result
        """
        self.fitness_scores[alpha_expression] = (
            result.sharpe * 0.5 + 
            result.fitness * 0.3 + 
            (1.0 / (1.0 + result.turnover)) * 0.2
        )
    
    def get_population_stats(self) -> Dict:
        """Get statistics about current population"""
        if len(self.population) == 0:
            return {}
        
        fitness_values = [
            self.fitness_scores.get(a.template, 0) 
            for a in self.population
        ]
        sharpe_values = [a.sharpe for a in self.population]
        
        return {
            'population_size': len(self.population),
            'avg_fitness': sum(fitness_values) / len(fitness_values),
            'max_fitness': max(fitness_values),
            'avg_sharpe': sum(sharpe_values) / len(sharpe_values),
            'max_sharpe': max(sharpe_values)
        }

