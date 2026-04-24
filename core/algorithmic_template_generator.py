"""
Algorithmic Template Generator
Generates placeholder expressions using mathematical algorithms (random walk, brownian motion, etc.)
Then uses Ollama to select actual operators/fields by index
"""

import logging
import random
import math
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OperatorMetadata:
    """Metadata extracted from operatorRAW.json"""
    name: str
    category: str
    scope: List[str]  # REGULAR, MATRIX, VECTOR, COMBO, SELECTION
    definition: str
    description: str
    num_inputs: int  # Parsed from definition (exact number)
    min_inputs: int  # Minimum number of inputs (for "at least N" operators)
    supports_event_input: bool  # Based on definition/description
    uses_lookback: bool  # True if definition contains time series parameters
    example: Optional[str] = None


class AlgorithmicTemplateGenerator:
    """
    Generates placeholder expressions algorithmically, then uses Ollama to select indices
    """
    
    def __init__(self, operators: List[Dict], data_fields: List[Dict]):
        """
        Initialize algorithmic template generator
        
        Args:
            operators: List of operator dicts from operatorRAW.json
            data_fields: List of data field dicts
        """
        self.operators = operators
        self.data_fields = data_fields
        self.operator_metadata = self._extract_operator_metadata(operators)
        
    def _extract_operator_metadata(self, operators: List[Dict]) -> Dict[str, OperatorMetadata]:
        """Extract metadata from operators"""
        metadata = {}
        
        for op in operators:
            name = op.get('name', '')
            if not name:
                continue
                
            definition = op.get('definition', '')
            description = op.get('description', '')
            scope = op.get('scope', [])
            category = op.get('category', '')
            
            # Parse number of inputs from definition
            num_inputs, min_inputs = self._parse_num_inputs(definition)
            
            # Check if supports event input (heuristic: check description/definition)
            supports_event = self._check_supports_event(definition, description, name)
            
            # Check if uses lookback (time series operators typically have lookback parameters)
            uses_lookback = self._check_uses_lookback(definition, description, name)
            
            # Generate example
            example = self._generate_example(name, definition, num_inputs)
            
            metadata[name] = OperatorMetadata(
                name=name,
                category=category,
                scope=scope,
                definition=definition,
                description=description,
                num_inputs=num_inputs,
                min_inputs=min_inputs,
                supports_event_input=supports_event,
                uses_lookback=uses_lookback,
                example=example
            )
        
        return metadata
    
    def _parse_num_inputs(self, definition: str) -> Tuple[int, int]:
        """
        Parse number of inputs from definition
        
        Returns:
            (num_inputs, min_inputs) tuple
            - num_inputs: Exact number of inputs (or 1 if variable)
            - min_inputs: Minimum number of inputs (for "at least N" operators)
        """
        if not definition:
            return (1, 1)  # Default to 1 input
        
        # Check for "at least" patterns
        at_least_match = re.search(r'at least (\d+)', definition, re.IGNORECASE)
        if at_least_match:
            min_inputs = int(at_least_match.group(1))
            # For "at least N", we'll use N as the default, but track minimum
            return (min_inputs, min_inputs)
        
        # Check for "minimum" patterns
        minimum_match = re.search(r'minimum.*?(\d+)', definition, re.IGNORECASE)
        if minimum_match:
            min_inputs = int(minimum_match.group(1))
            return (min_inputs, min_inputs)
        
        # Count input parameters: input1, input2, input3, etc.
        input_matches = re.findall(r'\binput\d+\b', definition, re.IGNORECASE)
        if input_matches:
            # Extract numbers and find max
            input_nums = [int(re.search(r'\d+', inp).group()) for inp in input_matches if re.search(r'\d+', inp)]
            num_inputs = max(input_nums) if input_nums else len(input_matches)
            return (num_inputs, num_inputs)  # Exact match
        
        # Check for common patterns
        # operator(x) -> 1 input
        # operator(x, y) -> 2 inputs (if y is not a parameter)
        # operator(x, lookback=20) -> 1 input + parameter
        
        # Count commas (rough estimate)
        comma_count = definition.count(',')
        
        # Check if it's a parameter (lookback, filter, etc.)
        has_params = bool(re.search(r'(lookback|filter|threshold|value|reverse)\s*=', definition, re.IGNORECASE))
        
        if has_params:
            # If has parameters, inputs = comma_count
            num_inputs = comma_count
        else:
            # If no parameters, inputs = comma_count + 1
            num_inputs = comma_count + 1 if comma_count > 0 else 1
        
        return (num_inputs, num_inputs)  # Default: exact match
    
    def _check_supports_event(self, definition: str, description: str, name: str) -> bool:
        """Check if operator supports event inputs"""
        # Most operators don't support event inputs
        # Event operators typically have "event" in name or description
        text = (definition + " " + description + " " + name).lower()
        
        # Check for event-related keywords
        event_keywords = ['event', 'earnings', 'announcement', 'dividend']
        if any(keyword in text for keyword in event_keywords):
            return True
        
        # Some operators explicitly support events (rare)
        # For now, assume most don't support events
        return False
    
    def _check_uses_lookback(self, definition: str, description: str, name: str) -> bool:
        """Check if operator uses lookback (time series)"""
        text = (definition + " " + description + " " + name).lower()
        
        # Time series operators typically have "ts_" prefix or lookback parameters
        if name.startswith('ts_'):
            return True
        
        # Check for lookback-related keywords
        lookback_keywords = ['lookback', 'window', 'period', 'lag', 'lead', 'delta']
        if any(keyword in text for keyword in lookback_keywords):
            return True
        
        return False
    
    def _generate_example(self, name: str, definition: str, num_inputs: int) -> str:
        """Generate example usage"""
        if num_inputs == 0:
            return f"{name}()"
        elif num_inputs == 1:
            return f"{name}(DATA_FIELD1)"
        elif num_inputs == 2:
            return f"{name}(DATA_FIELD1, DATA_FIELD2)"
        else:
            fields = ", ".join([f"DATA_FIELD{i+1}" for i in range(num_inputs)])
            return f"{name}({fields})"
    
    def generate_placeholder_expression(
        self,
        max_operators: int = 5,
        method: str = "random_walk"
    ) -> str:
        """
        Generate placeholder expression using algorithmic methods
        
        Args:
            max_operators: Maximum number of operators
            method: Generation method ("random_walk", "brownian", "tree", "linear")
        
        Returns:
            Placeholder expression like "OPERATOR1(OPERATOR2(DATA_FIELD1), 5)"
        """
        if method == "random_walk":
            return self._random_walk_generation(max_operators)
        elif method == "brownian":
            return self._brownian_motion_generation(max_operators)
        elif method == "tree":
            return self._tree_generation(max_operators)
        elif method == "linear":
            return self._linear_generation(max_operators)
        else:
            return self._random_walk_generation(max_operators)
    
    def _random_walk_generation(self, max_operators: int) -> str:
        """Generate using random walk approach"""
        num_operators = random.randint(1, max_operators)
        
        # Random walk: start with a field, then randomly add operators
        expression = "DATA_FIELD1"
        field_counter = 1
        operator_counter = 1
        
        for i in range(num_operators):
            # Random decision: nest, wrap, or combine
            decision = random.random()
            
            if decision < 0.4:  # 40%: Nest operator
                expression = f"OPERATOR{operator_counter}({expression})"
                operator_counter += 1
            elif decision < 0.7:  # 30%: Wrap with parameter
                param = random.choice([5, 10, 20, 30, 50, 100])
                expression = f"OPERATOR{operator_counter}({expression}, {param})"
                operator_counter += 1
            else:  # 30%: Combine with another field (ensures at least 2 inputs for operators that need it)
                field_counter += 1
                op = random.choice(['+', '-', '*', '/'])
                # This creates OPERATOR(field1 op field2) which has 2 inputs
                expression = f"OPERATOR{operator_counter}(DATA_FIELD{field_counter} {op} {expression})"
                operator_counter += 1
        
        return expression
    
    def _brownian_motion_generation(self, max_operators: int) -> str:
        """Generate using Brownian motion-inspired approach"""
        num_operators = random.randint(1, max_operators)
        
        # Brownian motion: random drift with volatility
        expression = "DATA_FIELD1"
        field_counter = 1
        operator_counter = 1
        
        # Drift parameter (tendency to nest)
        drift = 0.3
        # Volatility (randomness)
        volatility = 0.4
        
        for i in range(num_operators):
            # Brownian step: drift + random walk
            step = drift + random.gauss(0, volatility)
            
            if step < 0.3:  # Nest
                expression = f"OPERATOR{operator_counter}({expression})"
                operator_counter += 1
            elif step < 0.6:  # Wrap with parameter
                param = random.choice([5, 10, 20, 30, 50, 100])
                expression = f"OPERATOR{operator_counter}({expression}, {param})"
                operator_counter += 1
            else:  # Combine
                field_counter += 1
                op = random.choice(['+', '-', '*', '/'])
                expression = f"OPERATOR{operator_counter}(DATA_FIELD{field_counter} {op} {expression})"
                operator_counter += 1
        
        return expression
    
    def _tree_generation(self, max_operators: int) -> str:
        """Generate using tree structure"""
        num_operators = random.randint(1, max_operators)
        
        # Build binary tree structure
        def build_tree(depth: int, max_depth: int, field_id: int, op_id: int) -> Tuple[str, int, int]:
            if depth >= max_depth or op_id > num_operators:
                return f"DATA_FIELD{field_id}", field_id, op_id
            
            # Random decision: leaf or branch
            if random.random() < 0.5:
                # Leaf: just a field
                return f"DATA_FIELD{field_id}", field_id, op_id
            else:
                # Branch: operator with children
                left, field_id, op_id = build_tree(depth + 1, max_depth, field_id, op_id)
                if op_id <= num_operators and random.random() < 0.6:
                    right, field_id, op_id = build_tree(depth + 1, max_depth, field_id + 1, op_id)
                    op = random.choice(['+', '-', '*', '/'])
                    expr = f"OPERATOR{op_id}({left} {op} {right})"
                    op_id += 1
                else:
                    expr = f"OPERATOR{op_id}({left})"
                    op_id += 1
                return expr, field_id, op_id
        
        max_depth = math.ceil(math.log2(num_operators + 1))
        expression, _, _ = build_tree(0, max_depth, 1, 1)
        return expression
    
    def _linear_generation(self, max_operators: int) -> str:
        """Generate using linear chain"""
        num_operators = random.randint(1, max_operators)
        
        expression = "DATA_FIELD1"
        operator_counter = 1
        
        for i in range(num_operators):
            if random.random() < 0.5:
                # Wrap with parameter
                param = random.choice([5, 10, 20, 30, 50, 100])
                expression = f"OPERATOR{operator_counter}({expression}, {param})"
            else:
                # Simple wrap
                expression = f"OPERATOR{operator_counter}({expression})"
            operator_counter += 1
        
        return expression
    
    def get_operator_selection_prompt(
        self,
        placeholder_expression: str,
        available_operators: List[Dict],
        available_fields: List[Dict],
        recently_used_fields: List[str] = None  # New: fields to avoid
    ) -> str:
        """
        Generate prompt for Ollama to select operators/fields by index
        
        Args:
            placeholder_expression: Expression with placeholders like "OPERATOR1(OPERATOR2(DATA_FIELD1), 5)"
            available_operators: List of available operators
            available_fields: List of available data fields
        
        Returns:
            Prompt string for Ollama
        """
        import random
        
        # Count placeholders (case-insensitive matching)
        operator_placeholders = re.findall(r'OPERATOR(\d+)', placeholder_expression, re.IGNORECASE)
        field_placeholders = re.findall(r'DATA_FIELD(\d+)', placeholder_expression, re.IGNORECASE)
        
        # Get unique placeholders (normalized to uppercase)
        unique_operator_placeholders = sorted(set([f"OPERATOR{p}" for p in operator_placeholders]), 
                                             key=lambda x: int(re.search(r'\d+', x).group()))
        unique_field_placeholders = sorted(set([f"DATA_FIELD{p}" for p in field_placeholders]),
                                           key=lambda x: int(re.search(r'\d+', x).group()))
        
        num_operators_needed = len(unique_operator_placeholders)
        num_fields_needed = len(unique_field_placeholders)
        
        # Randomly shuffle operators and fields for diversity
        operator_indices = list(range(len(available_operators)))
        random.shuffle(operator_indices)
        field_indices = list(range(len(available_fields)))
        random.shuffle(field_indices)
        
        # Build operator selection list with full metadata (use shuffled indices)
        operator_list = []
        operator_mapping = {}  # Map display index to actual operator index
        for display_idx, actual_idx in enumerate(operator_indices[:50]):  # Limit to 50 for prompt size
            if actual_idx >= len(available_operators):
                continue
            op = available_operators[actual_idx]
            name = op.get('name', '')
            if not name:
                continue
            
            metadata = self.operator_metadata.get(name)
            if metadata:
                op_info = f"[{display_idx}] {name}"
                op_info += f" | Category: {metadata.category}"
                if metadata.min_inputs > 1 and metadata.min_inputs == metadata.num_inputs:
                    op_info += f" | Inputs: {metadata.num_inputs} (at least {metadata.min_inputs})"
                else:
                    op_info += f" | Inputs: {metadata.num_inputs}"
                op_info += f" | Scope: {', '.join(metadata.scope[:3])}"  # First 3 scopes
                op_info += f" | Event Input: {'Yes' if metadata.supports_event_input else 'No'}"
                op_info += f" | Uses Lookback: {'Yes' if metadata.uses_lookback else 'No'}"
                if metadata.description:
                    op_info += f" | Description: {metadata.description[:80]}"
                if metadata.definition:
                    op_info += f" | Definition: {metadata.definition}"
                if metadata.example:
                    op_info += f" | Example: {metadata.example}"
                operator_list.append(op_info)
                operator_mapping[display_idx] = actual_idx
        
        # Build field selection list (use shuffled indices)
        # Exclude recently used fields to ensure diversity
        recently_used_set = set()
        if recently_used_fields:
            recently_used_set = {f.lower() for f in recently_used_fields}
            logger.debug(f"Excluding {len(recently_used_set)} recently used fields from selection")
        
        field_list = []
        field_mapping = {}  # Map display index to actual field index
        # Shuffle again to ensure different selection each time
        random.shuffle(field_indices)
        
        # Filter out recently used fields and select diverse fields
        excluded_count = 0
        for actual_idx in field_indices:
            if actual_idx >= len(available_fields):
                continue
            field = available_fields[actual_idx]
            field_id = field.get('id', '')
            if field_id:
                # Skip if this field was recently used
                if field_id.lower() in recently_used_set:
                    excluded_count += 1
                    continue
                
                # Add to list (we'll limit to 50 total)
                if len(field_list) >= 50:
                    break
                
                display_idx = len(field_list)
                field_list.append(f"[{display_idx}] {field_id}")
                field_mapping[display_idx] = actual_idx
        
        # If we excluded too many and don't have enough fields, add some back (but prefer unused)
        if len(field_list) < 30 and excluded_count > 0:
            logger.debug(f"Only {len(field_list)} fields available after exclusion, adding some recently used fields back")
            for actual_idx in field_indices:
                if actual_idx >= len(available_fields):
                    continue
                field = available_fields[actual_idx]
                field_id = field.get('id', '')
                if field_id and field_id.lower() in recently_used_set:
                    if len(field_list) >= 50:
                        break
                    display_idx = len(field_list)
                    field_list.append(f"[{display_idx}] {field_id} (recently used)")
                    field_mapping[display_idx] = actual_idx
        
        if excluded_count > 0:
            logger.debug(f"Excluded {excluded_count} recently used fields, showing {len(field_list)} diverse fields to Ollama")
        
        # Build explicit list of placeholders that MUST be selected
        operator_placeholder_list = ", ".join(unique_operator_placeholders) if unique_operator_placeholders else "NONE"
        field_placeholder_list = ", ".join(unique_field_placeholders) if unique_field_placeholders else "NONE"
        
        prompt = f"""You are a selection assistant. Your ONLY job is to select INDEX NUMBERS from the lists below.

DO NOT generate or write any operator names or field names.
ONLY return the INDEX NUMBERS in JSON format.

Expression with placeholders:
{placeholder_expression}

🚨 CRITICAL: You MUST select indices for ALL of the following placeholders found in the expression above:

REQUIRED OPERATOR PLACEHOLDERS (you MUST select all {num_operators_needed}):
{operator_placeholder_list}

REQUIRED FIELD PLACEHOLDERS (you MUST select all {num_fields_needed}):
{field_placeholder_list}

CRITICAL RULES:
1. ONLY return index numbers (like 0, 5, 12, 23) - DO NOT write operator names or field names
2. Use UPPERCASE placeholder names as keys: OPERATOR1, OPERATOR2, DATA_FIELD1, DATA_FIELD2
3. You MUST include ALL placeholders listed above in your JSON response - missing any placeholder will cause an error
4. Map each placeholder to an INDEX NUMBER from the lists below
5. Select DIFFERENT field indices for different DATA_FIELD placeholders when possible
6. **PRIORITIZE DIVERSITY**: Choose fields that are different from recently used ones - avoid repetitive selections
7. If an operator shows "at least N" inputs, the template structure should already provide enough inputs

AVAILABLE OPERATORS (randomly shuffled - select by INDEX number in brackets):
{chr(10).join(operator_list)}

AVAILABLE DATA FIELDS (randomly shuffled - select by INDEX number in brackets):
{chr(10).join(field_list)}
{f"⚠️ NOTE: {len(recently_used_set)} recently used fields have been excluded from this list to ensure diversity. Choose from the fields shown above." if recently_used_set else ""}

Return ONLY a JSON object with INDEX NUMBERS (no names, no explanations):
{{
  "operators": {{"OPERATOR1": 5, "OPERATOR2": 12, "OPERATOR3": 23}},
  "fields": {{"DATA_FIELD1": 3, "DATA_FIELD2": 18}}
}}

Example: If you want to select the operator at [5] for OPERATOR1, return "OPERATOR1": 5
Example: If you want to select the field at [3] for DATA_FIELD1, return "DATA_FIELD1": 3

ONLY return the JSON with index numbers. DO NOT generate operator names or field names."""
        
        # Store mappings for later use in replacement
        self._last_operator_mapping = operator_mapping
        self._last_field_mapping = field_mapping
        # Store the list of required placeholders for validation
        self._required_operator_placeholders = unique_operator_placeholders
        self._required_field_placeholders = unique_field_placeholders
        
        return prompt
