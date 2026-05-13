"""
FASTEXPR AST Parser and Self-Correcting System
For WorldQuant Brain's FASTEXPR language

FASTEXPR is a combination of:
- Operators (from operatorRAW.json) with scope: REGULAR, MATRIX, VECTOR
- Data Fields (from API) with type: REGULAR, MATRIX, VECTOR
- Arithmetic operators: +, -, *, /, etc.

Features:
- AST parsing and validation
- Operator-field type compatibility checking
- Self-correcting through trial and error
- Learning from simulation errors
"""

import re
import logging
from typing import List, Dict, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from collections import defaultdict
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ASTNode:
    """AST Node for FASTEXPR"""
    node_type: str  # 'operator', 'field', 'literal', 'function', 'arithmetic'
    value: str
    children: List['ASTNode'] = field(default_factory=list)
    position: Tuple[int, int] = (0, 0)  # (start, end) character positions
    parent: Optional['ASTNode'] = None
    
    def to_string(self) -> str:
        """Convert AST node back to string"""
        if self.node_type == 'arithmetic':
            if len(self.children) == 2:
                return f"({self.children[0].to_string()} {self.value} {self.children[1].to_string()})"
            elif len(self.children) == 1:
                return f"({self.value} {self.children[0].to_string()})"
        elif self.node_type == 'function':
            args = ', '.join(child.to_string() for child in self.children)
            return f"{self.value}({args})"
        elif self.node_type in ['field', 'variable']:
            return self.value
        else:
            return self.value


@dataclass
class SyntaxError:
    """Represents a syntax error in FASTEXPR"""
    error_type: str  # 'invalid_operator', 'invalid_field', 'type_mismatch', 'unbalanced_parens', 'invalid_syntax'
    message: str
    position: Tuple[int, int]
    template: str
    suggested_fix: Optional[str] = None
    operator_name: Optional[str] = None
    field_name: Optional[str] = None
    expected_type: Optional[str] = None
    actual_type: Optional[str] = None


class FASTEXPRParser:
    """Parser for FASTEXPR language - validates operator-field combinations"""
    
    # Arithmetic operators
    ARITHMETIC_OPERATORS = {
        '+', '-', '*', '/', '^', '%',
        '>', '<', '>=', '<=', '==', '!=',
        '&&', '||', '!',
    }
    
    # Operator precedence (higher = evaluated first)
    OPERATOR_PRECEDENCE = {
        '^': 4,
        '*': 3, '/': 3, '%': 3,
        '+': 2, '-': 2,
        '>': 1, '<': 1, '>=': 1, '<=': 1, '==': 1, '!=': 1,
        '&&': 0, '||': 0,
    }
    
    def __init__(self, operators: List[Dict] = None, data_fields: List[Dict] = None):
        """
        Initialize parser with operators and data fields
        
        Args:
            operators: List of operator dicts from operatorRAW.json
            data_fields: List of data field dicts from API
        """
        self.operators: Dict[str, Dict] = {}
        self.operator_scopes: Dict[str, Set[str]] = {}  # operator_name -> {REGULAR, MATRIX, VECTOR}
        self.vec_operators: Set[str] = set()  # Operators that start with vec_
        self.data_fields: Dict[str, Dict] = {}
        self.field_types: Dict[str, str] = {}  # field_id -> REGULAR/MATRIX/VECTOR
        # Event input compatibility (learned from errors)
        self.event_input_incompatible_operators: Set[str] = set()  # Operators that don't support event inputs
        self.event_input_compatible_operators: Set[str] = set()  # Operators that support event inputs
        
        if operators:
            self.add_operators(operators)
        if data_fields:
            self.add_data_fields(data_fields)
        
        # Load compiler knowledge from JSON file
        self._load_compiler_knowledge_json()
    
    def add_operators(self, operators: List[Dict]):
        """Add operators from operatorRAW.json"""
        for op in operators:
            name = op.get('name', '')
            if name:
                self.operators[name] = op
                # Parse scope
                scope = op.get('scope', [])
                if isinstance(scope, list):
                    self.operator_scopes[name] = set(scope)
                else:
                    self.operator_scopes[name] = {scope} if scope else {'REGULAR'}
                
                # Track vec_ operators
                if name.startswith('vec_'):
                    self.vec_operators.add(name)
    
    def _load_compiler_knowledge_json(self):
        """Load compiler knowledge from JSON file"""
        try:
            compiler_knowledge_file = Path(__file__).parent / "compiler_knowledge.json"
            if compiler_knowledge_file.exists():
                with open(compiler_knowledge_file, 'r') as f:
                    data = json.load(f)
                    
                    # Load event input incompatibilities
                    event_input_data = data.get('event_input_compatibility', {})
                    incompatible = event_input_data.get('incompatible_operators', [])
                    for op in incompatible:
                        self.event_input_incompatible_operators.add(op.lower())
                    
                    logger.debug(f"Loaded {len(incompatible)} event input incompatible operators from JSON")
        except Exception as e:
            logger.debug(f"Failed to load compiler knowledge JSON: {e}")
    
    def add_data_fields(self, data_fields: List[Dict]):
        """Add data fields from API"""
        for field in data_fields:
            field_id = field.get('id', '')
            if field_id:
                self.data_fields[field_id] = field
                field_type = field.get('type', 'REGULAR')
                self.field_types[field_id] = field_type
    
    def parse(self, template: str) -> Tuple[Optional[ASTNode], List[SyntaxError]]:
        """
        Parse FASTEXPR template into AST
        
        Returns:
            (AST node, list of syntax errors)
        """
        errors = []
        
        # Basic validation
        if not template or not template.strip():
            errors.append(SyntaxError(
                'invalid_syntax',
                'Empty template',
                (0, 0),
                template
            ))
            return None, errors
        
        # Check balanced parentheses
        paren_errors = self._check_balanced_parentheses(template)
        errors.extend(paren_errors)
        
        if paren_errors:
            return None, errors
        
        # Try to parse
        try:
            ast = self._parse_expression(template, 0, len(template))
            if ast:
                # Validate AST for operator-field compatibility
                validation_errors = self._validate_ast(ast, template)
                errors.extend(validation_errors)
                return ast, errors
            else:
                errors.append(SyntaxError(
                    'invalid_syntax',
                    'Failed to parse expression',
                    (0, len(template)),
                    template
                ))
                return None, errors
        except Exception as e:
            errors.append(SyntaxError(
                'invalid_syntax',
                f'Parse error: {str(e)}',
                (0, len(template)),
                template
            ))
            return None, errors
    
    def _check_balanced_parentheses(self, template: str) -> List[SyntaxError]:
        """Check if parentheses are balanced"""
        errors = []
        stack = []
        
        for i, char in enumerate(template):
            if char == '(':
                stack.append(i)
            elif char == ')':
                if not stack:
                    errors.append(SyntaxError(
                        'unbalanced_parens',
                        'Unmatched closing parenthesis',
                        (i, i + 1),
                        template,
                        suggested_fix=template[:i] + template[i+1:]
                    ))
                else:
                    stack.pop()
        
        if stack:
            for pos in stack:
                errors.append(SyntaxError(
                    'unbalanced_parens',
                    'Unmatched opening parenthesis',
                    (pos, pos + 1),
                    template,
                    suggested_fix=template[:pos] + template[pos+1:]
                ))
        
        return errors
    
    def _parse_expression(self, template: str, start: int, end: int) -> Optional[ASTNode]:
        """Parse expression using recursive descent"""
        # Remove whitespace
        expr = template[start:end].strip()
        if not expr:
            return None
        
        # Handle parentheses
        if expr.startswith('(') and expr.endswith(')'):
            # Check if entire expression is wrapped
            depth = 0
            is_wrapped = True
            for i, char in enumerate(expr[1:-1]):
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                    if depth < 0:
                        is_wrapped = False
                        break
            if is_wrapped and depth == 0:
                return self._parse_expression(template, start + 1, end - 1)
        
        # Find lowest precedence arithmetic operator (rightmost for left-associative)
        lowest_prec = -1
        lowest_pos = -1
        lowest_op = None
        
        i = len(expr) - 1
        depth = 0
        while i >= 0:
            char = expr[i]
            if char == ')':
                depth += 1
            elif char == '(':
                depth -= 1
            elif depth == 0:
                # Check for multi-character operators
                for op_len in [2, 1]:
                    if i + op_len <= len(expr):
                        op = expr[i:i+op_len]
                        if op in self.ARITHMETIC_OPERATORS:
                            prec = self.OPERATOR_PRECEDENCE.get(op, 0)
                            if prec > lowest_prec:
                                lowest_prec = prec
                                lowest_pos = i
                                lowest_op = op
                                break
            i -= 1
        
        if lowest_op:
            # Split on arithmetic operator
            left_expr = expr[:lowest_pos].strip()
            right_expr = expr[lowest_pos + len(lowest_op):].strip()
            
            left_node = self._parse_expression(template, start, start + len(left_expr)) if left_expr else None
            right_node = self._parse_expression(template, start + lowest_pos + len(lowest_op), end) if right_expr else None
            
            return ASTNode(
                node_type='arithmetic',
                value=lowest_op,
                children=[n for n in [left_node, right_node] if n],
                position=(start, end)
            )
        
        # Check for function call (operator)
        func_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\((.*)\)$', expr)
        if func_match:
            func_name = func_match.group(1)
            args_str = func_match.group(2)
            
            # Parse arguments
            args = self._parse_arguments(args_str, start + len(func_name) + 1)
            
            return ASTNode(
                node_type='function',
                value=func_name,
                children=args,
                position=(start, end)
            )
        
        # Check for field/variable
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', expr):
            return ASTNode(
                node_type='field',
                value=expr,
                position=(start, end)
            )
        
        # Literal (number)
        if re.match(r'^-?\d+\.?\d*$', expr):
            return ASTNode(
                node_type='literal',
                value=expr,
                position=(start, end)
            )
        
        return None
    
    def _parse_arguments(self, args_str: str, start_pos: int) -> List[ASTNode]:
        """Parse function arguments"""
        if not args_str.strip():
            return []
        
        args = []
        depth = 0
        current_start = 0
        
        for i, char in enumerate(args_str):
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                arg_str = args_str[current_start:i].strip()
                if arg_str:
                    arg_node = self._parse_expression(args_str, current_start, i)
                    if arg_node:
                        args.append(arg_node)
                current_start = i + 1
        
        # Last argument
        if current_start < len(args_str):
            arg_str = args_str[current_start:].strip()
            if arg_str:
                arg_node = self._parse_expression(args_str, current_start, len(args_str))
                if arg_node:
                    args.append(arg_node)
        
        return args
    
    def _validate_ast(self, ast: ASTNode, template: str) -> List[SyntaxError]:
        """Validate AST for operator-field compatibility"""
        errors = []
        
        if ast.node_type == 'function':
            # This is an operator call
            operator_name = ast.value
            
            # Check if operator exists
            if operator_name not in self.operators:
                errors.append(SyntaxError(
                    'invalid_operator',
                    f'Unknown operator: {operator_name}',
                    ast.position,
                    template,
                    operator_name=operator_name
                ))
            else:
                # Get operator scope
                operator_scope = self.operator_scopes.get(operator_name, set())
                
                # Validate arguments (fields)
                for child in ast.children:
                    child_errors = self._validate_ast(child, template)
                    errors.extend(child_errors)
                    
                    # Check field-operator compatibility
                    if child.node_type == 'field':
                        field_name = child.value
                        field_type = self.field_types.get(field_name)
                        
                        # Check if field is event input type
                        field_info = self.data_fields.get(field_name, {})
                        is_event_input = field_info.get('type') == 'EVENT' or 'event' in str(field_info.get('category', '')).lower()
                        
                        # Check event input compatibility (learned from simulation errors)
                        if is_event_input and operator_name in self.event_input_incompatible_operators:
                            errors.append(SyntaxError(
                                'event_input_incompatible',
                                f'Operator {operator_name} does not support event inputs (field: {field_name})',
                                child.position,
                                template,
                                operator_name=operator_name,
                                field_name=field_name,
                                expected_type='NON_EVENT',
                                actual_type='EVENT'
                            ))
                        
                        if field_type:
                            # Check compatibility
                            if 'REGULAR' not in operator_scope and 'MATRIX' not in operator_scope and 'VECTOR' not in operator_scope:
                                # Operator has no scope defined, assume it works with all
                                pass
                            else:
                                # REGULAR scope operators work with REGULAR, MATRIX, and VECTOR fields
                                # MATRIX scope operators work with MATRIX fields
                                # VECTOR scope operators work with VECTOR fields
                                is_compatible = False
                                
                                if 'REGULAR' in operator_scope:
                                    # REGULAR operators work with REGULAR, MATRIX, and VECTOR
                                    is_compatible = True
                                elif 'MATRIX' in operator_scope and field_type == 'MATRIX':
                                    is_compatible = True
                                elif 'VECTOR' in operator_scope and field_type == 'VECTOR':
                                    is_compatible = True
                                elif field_type in operator_scope:
                                    # Direct match
                                    is_compatible = True
                                
                                if not is_compatible:
                                    # Type mismatch
                                    errors.append(SyntaxError(
                                        'type_mismatch',
                                        f'Operator {operator_name} (scope: {operator_scope}) incompatible with field {field_name} (type: {field_type})',
                                        child.position,
                                        template,
                                        operator_name=operator_name,
                                        field_name=field_name,
                                        expected_type=str(operator_scope),
                                        actual_type=field_type
                                    ))
                            
                            # Special check for vec_ operators
                            if operator_name.startswith('vec_'):
                                if field_type != 'VECTOR':
                                    errors.append(SyntaxError(
                                        'type_mismatch',
                                        f'vec_ operator {operator_name} requires VECTOR field, got {field_type}',
                                        child.position,
                                        template,
                                        operator_name=operator_name,
                                        field_name=field_name,
                                        expected_type='VECTOR',
                                        actual_type=field_type
                                    ))
                        else:
                            # Field not found in data fields
                            # Try to find similar field or suggest removing region prefix
                            suggested_fix = None
                            similar_fields = self._find_similar_fields(field_name)
                            if similar_fields:
                                suggested_fix = similar_fields[0]
                            elif '.' in field_name:
                                # If field has region prefix (e.g., "USA.MCAP"), try to find fields with the suffix
                                field_part = field_name.split('.', 1)[1]
                                for fid in self.data_fields.keys():
                                    if field_part.lower() in fid.lower() or fid.lower() in field_part.lower():
                                        suggested_fix = fid
                                        break
                            
                            error_msg = f'Unknown field: {field_name}'
                            if suggested_fix:
                                error_msg += f' (did you mean {suggested_fix}?)'
                            
                            errors.append(SyntaxError(
                                'invalid_field',
                                error_msg,
                                child.position,
                                template,
                                field_name=field_name,
                                suggested_fix=suggested_fix
                            ))
        
        elif ast.node_type == 'field':
            # Check if field exists
            field_name = ast.value
            if field_name not in self.data_fields:
                # Try to find similar field or suggest removing region prefix
                suggested_fix = None
                similar_fields = self._find_similar_fields(field_name)
                if similar_fields:
                    suggested_fix = similar_fields[0]
                elif '.' in field_name:
                    # If field has region prefix (e.g., "USA.MCAP"), try to find fields with the suffix
                    field_part = field_name.split('.', 1)[1]
                    for fid in self.data_fields.keys():
                        if field_part.lower() in fid.lower() or fid.lower() in field_part.lower():
                            suggested_fix = fid
                            break
                
                error_msg = f'Unknown field: {field_name}'
                if suggested_fix:
                    error_msg += f' (did you mean {suggested_fix}?)'
                
                errors.append(SyntaxError(
                    'invalid_field',
                    error_msg,
                    ast.position,
                    template,
                    field_name=field_name,
                    suggested_fix=suggested_fix
                ))
        
        elif ast.node_type == 'arithmetic':
            # Validate children
            for child in ast.children:
                errors.extend(self._validate_ast(child, template))
        
        return errors
    
    def _find_similar_fields(self, field_name: str) -> List[str]:
        """Find similar valid fields using fuzzy matching"""
        if not self.data_fields:
            return []
        
        # Simple similarity (Levenshtein-like)
        similarities = []
        for valid_field in self.data_fields.keys():
            # Check if field_name is substring or vice versa
            if field_name.lower() in valid_field.lower() or valid_field.lower() in field_name.lower():
                similarities.append(valid_field)
        
        return similarities[:5]  # Return top 5 matches


class SelfCorrectingAST:
    """Self-correcting AST system that learns from errors"""
    
    def __init__(self, parser: FASTEXPRParser):
        self.parser = parser
        self.error_history: List[Tuple[str, str, str]] = []  # (template, error, fixed_template)
        self.correction_rules: Dict[str, List[Dict]] = defaultdict(list)  # error_type -> [rules]
        self.successful_templates: List[str] = []
        self.failed_templates: List[Tuple[str, str]] = []  # (template, error_message)
        
        # Load learned patterns
        self._load_learned_patterns()
        
        # Load compiler knowledge from database
        self._load_compiler_knowledge()
    
    def _load_compiler_knowledge(self):
        """Load compiler knowledge from database (event input incompatibilities, etc.) - OPTIMIZED"""
        try:
            from ..storage.backtest_storage import BacktestStorage
            # Use db_path from parser if available, otherwise use default
            db_path = getattr(self.parser, 'db_path', 'generation_two_backtests.db')
            storage = BacktestStorage(db_path)
            
            # Load only event input incompatibilities (targeted query, no limit needed for this small set)
            knowledge = storage.get_compiler_knowledge(
                knowledge_type='event_input_incompatible',
                limit=50  # Reasonable limit for event input operators
            )
            for record in knowledge:
                operator_name = record.get('operator_name')
                if operator_name:
                    if not hasattr(self.parser, 'event_input_incompatible_operators'):
                        self.parser.event_input_incompatible_operators = set()
                    self.parser.event_input_incompatible_operators.add(operator_name.lower())
                    logger.debug(f"Loaded compiler knowledge: {operator_name} does not support event inputs")
        except Exception as e:
            logger.debug(f"Failed to load compiler knowledge: {e}")
    
    def learn_from_error(self, template: str, error_message: str, fixed_template: Optional[str] = None):
        """Learn from a template error"""
        self.failed_templates.append((template, error_message))
        
        # Extract error pattern
        error_type = self._classify_error(error_message)
        
        # Learn correction
        if fixed_template:
            self.error_history.append((template, error_message, fixed_template))
            self._extract_correction_rule(template, error_message, fixed_template, error_type)
        
        # Save learned patterns
        self._save_learned_patterns()
    
    def learn_from_success(self, template: str):
        """Learn from a successful template and store AST pattern"""
        self.successful_templates.append(template)
        self._extract_good_patterns(template)
        
        # Store AST pattern in database
        try:
            ast, errors = self.parser.parse(template)
            if ast and not errors:
                # Extract AST structure
                ast_structure = self._extract_ast_structure(ast)
                
                # Extract operators and field types
                operators = []
                field_types = []
                self._extract_operators_and_fields(ast, operators, field_types)
                
                # Store in database
                from ..storage.backtest_storage import BacktestStorage
                # Use db_path from parser if available, otherwise use default
                db_path = getattr(self.parser, 'db_path', 'generation_two_backtests.db')
                storage = BacktestStorage(db_path)
                storage.store_ast_pattern(
                    pattern_type='successful',
                    pattern_structure=ast_structure,
                    operator_sequence=operators,
                    field_types=field_types,
                    example_template=template,
                    success=True
                )
                logger.info(f"✅ Stored successful AST pattern to database: {db_path}")
        except Exception as e:
            logger.error(f"❌ Failed to store AST pattern: {e}", exc_info=True)
    
    def _extract_ast_structure(self, ast) -> str:
        """Extract AST structure as string representation"""
        if not ast:
            return ""
        
        structure_parts = []
        if ast.node_type == 'function':
            structure_parts.append(f"FUNC({ast.value})")
        elif ast.node_type == 'field':
            structure_parts.append(f"FIELD({ast.value})")
        elif ast.node_type == 'literal':
            structure_parts.append(f"LIT({ast.value})")
        elif ast.node_type == 'arithmetic':
            structure_parts.append(f"ARITH({ast.value})")
        
        if ast.children:
            child_structures = [self._extract_ast_structure(child) for child in ast.children]
            structure_parts.append(f"[{','.join(child_structures)}]")
        
        return "".join(structure_parts)
    
    def _extract_operators_and_fields(self, ast, operators: List, field_types: List):
        """Extract operators and field types from AST"""
        if ast.node_type == 'function':
            operators.append(ast.value)
        elif ast.node_type == 'field':
            field_type = self.parser.field_types.get(ast.value, 'UNKNOWN')
            field_types.append(field_type)
        
        for child in ast.children:
            self._extract_operators_and_fields(child, operators, field_types)
    
    def correct_template(self, template: str, error_message: Optional[str] = None) -> Tuple[str, List[str]]:
        """
        Correct a template using learned patterns
        
        Returns:
            (corrected_template, list of corrections applied)
        """
        corrections_applied = []
        corrected = template
        
        # Parse and get errors
        ast, errors = self.parser.parse(template)
        
        # Apply learned corrections
        if error_message:
            error_type = self._classify_error(error_message)
            for rule in self.correction_rules.get(error_type, []):
                if rule['pattern'].search(corrected):
                    corrected = rule['pattern'].sub(rule['replacement'], corrected)
                    corrections_applied.append(f"Applied rule: {rule['description']}")
        
        # Fix type mismatches
        for error in errors:
            if error.error_type == 'type_mismatch':
                # Try to fix by replacing field with compatible type
                if error.field_name and error.expected_type:
                    # Find compatible field
                    compatible_fields = self._find_compatible_fields(
                        error.field_name,
                        error.expected_type,
                        error.operator_name
                    )
                    if compatible_fields:
                        replacement = compatible_fields[0]
                        # Replace in template
                        start, end = error.position
                        corrected = corrected[:start] + replacement + corrected[end:]
                        corrections_applied.append(f"Fixed type mismatch: {error.field_name} -> {replacement}")
        
        # Fix syntax errors
        for error in errors:
            if error.suggested_fix:
                start, end = error.position
                corrected = corrected[:start] + error.suggested_fix + corrected[end:]
                corrections_applied.append(f"Fixed {error.error_type}: {error.message}")
        
        return corrected, corrections_applied
    
    def _find_compatible_fields(self, field_name: str, expected_type: str, operator_name: Optional[str] = None) -> List[str]:
        """Find fields compatible with expected type"""
        compatible = []
        
        # Parse expected type (could be set like {'REGULAR', 'MATRIX'})
        if isinstance(expected_type, str):
            expected_types = {expected_type}
        else:
            expected_types = set(expected_type) if expected_type else {'REGULAR', 'MATRIX', 'VECTOR'}
        
        # Find fields with matching type
        for field_id, field_data in self.parser.data_fields.items():
            field_type = self.parser.field_types.get(field_id, 'REGULAR')
            if field_type in expected_types:
                compatible.append(field_id)
        
        return compatible[:5]  # Return top 5
    
    def _classify_error(self, error_message: str) -> str:
        """Classify error type from error message"""
        error_lower = error_message.lower()
        
        if 'field' in error_lower or 'unknown variable' in error_lower:
            return 'invalid_field'
        elif 'operator' in error_lower or 'syntax' in error_lower:
            return 'invalid_operator'
        elif 'type' in error_lower or 'mismatch' in error_lower or 'incompatible' in error_lower:
            return 'type_mismatch'
        elif 'parenthesis' in error_lower or 'paren' in error_lower:
            return 'unbalanced_parens'
        else:
            return 'unknown_error'
    
    def _extract_correction_rule(self, original: str, error: str, fixed: str, error_type: str):
        """Extract correction rule from original -> fixed"""
        if original != fixed:
            pattern = re.escape(original)
            replacement = fixed
            
            rule = {
                'pattern': re.compile(pattern),
                'replacement': replacement,
                'description': f"Fix for {error_type}: {error[:50]}",
                'error_type': error_type
            }
            
            self.correction_rules[error_type].append(rule)
    
    def _extract_good_patterns(self, template: str):
        """Extract good patterns from successful templates"""
        # Parse successful template to learn structure
        ast, errors = self.parser.parse(template)
        if not errors and ast:
            # Extract operator+field patterns
            patterns = self._extract_ast_patterns(ast)
            if patterns:
                # Store patterns for use in generation prompts
                if not hasattr(self, 'good_patterns'):
                    self.good_patterns = []
                self.good_patterns.extend(patterns)
                # Keep only recent patterns (last 20)
                self.good_patterns = self.good_patterns[-20:]
    
    def _extract_ast_patterns(self, ast: ASTNode) -> List[str]:
        """Extract operator+field patterns from AST for prompt guidance"""
        patterns = []
        
        def traverse(node: ASTNode, depth: int = 0):
            if depth > 3:  # Limit depth to avoid too complex patterns
                return
            
            if node.node_type == 'function':
                # This is an operator call
                operator_name = node.value
                # Extract field references from children
                field_refs = []
                for child in node.children:
                    if child.node_type == 'field':
                        field_refs.append(child.value)
                    elif child.node_type == 'function':
                        # Nested operator - extract its pattern
                        nested_pattern = self._node_to_pattern(child)
                        if nested_pattern:
                            patterns.append(nested_pattern)
                
                # Create pattern: operator(field, ...)
                if field_refs:
                    pattern = f"{operator_name}({', '.join(field_refs[:3])})"  # Limit to 3 fields
                    patterns.append(pattern)
            
            # Traverse children
            for child in node.children:
                traverse(child, depth + 1)
        
        traverse(ast)
        return patterns
    
    def _node_to_pattern(self, node: ASTNode) -> Optional[str]:
        """Convert AST node to pattern string"""
        if node.node_type == 'function':
            args = []
            for child in node.children[:3]:  # Limit to 3 args
                if child.node_type == 'field':
                    args.append(child.value)
                elif child.node_type == 'literal':
                    args.append(str(child.value))
                elif child.node_type == 'function':
                    nested = self._node_to_pattern(child)
                    if nested:
                        args.append(nested)
            
            if args:
                return f"{node.value}({', '.join(args)})"
        
        return None
    
    def get_successful_patterns(self, limit: int = 5) -> List[str]:
        """Get successful template patterns for prompt guidance"""
        if hasattr(self, 'good_patterns') and self.good_patterns:
            return self.good_patterns[-limit:]
        # Fallback: return successful templates themselves
        return self.successful_templates[-limit:] if self.successful_templates else []
    
    def _load_learned_patterns(self):
        """Load learned correction patterns from disk"""
        pattern_file = Path.home() / ".generation_two" / "fast_expr_patterns.json"
        if pattern_file.exists():
            try:
                with open(pattern_file, 'r') as f:
                    data = json.load(f)
                    for error_type, rules in data.get('correction_rules', {}).items():
                        for rule_data in rules:
                            rule = {
                                'pattern': re.compile(rule_data['pattern']),
                                'replacement': rule_data['replacement'],
                                'description': rule_data['description'],
                                'error_type': error_type
                            }
                            self.correction_rules[error_type].append(rule)
            except Exception as e:
                logger.warning(f"Failed to load learned patterns: {e}")
    
    def _save_learned_patterns(self):
        """Save learned correction patterns to disk"""
        pattern_file = Path.home() / ".generation_two" / "fast_expr_patterns.json"
        pattern_file.parent.mkdir(exist_ok=True)
        
        try:
            data = {
                'correction_rules': {}
            }
            for error_type, rules in self.correction_rules.items():
                data['correction_rules'][error_type] = [
                    {
                        'pattern': rule['pattern'].pattern,
                        'replacement': rule['replacement'],
                        'description': rule['description'],
                        'error_type': error_type
                    }
                    for rule in rules
                ]
            
            with open(pattern_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save learned patterns: {e}")


class FASTEXPRValidator:
    """Validator that uses both AST and prompt engineering"""
    
    def __init__(self, parser: FASTEXPRParser, self_corrector: SelfCorrectingAST):
        self.parser = parser
        self.corrector = self_corrector
    
    def validate_and_fix(self, template: str, error_message: Optional[str] = None) -> Tuple[str, bool, List[str]]:
        """
        Validate and fix template using both AST and learned patterns
        
        Returns:
            (fixed_template, is_valid, list of fixes applied)
        """
        fixes_applied = []
        
        # First, try AST parsing
        ast, errors = self.parser.parse(template)
        
        if not errors and ast:
            # Template parses correctly
            return template, True, []
        
        # Apply AST-based fixes
        corrected = template
        for error in errors:
            if error.suggested_fix:
                start, end = error.position
                corrected = corrected[:start] + error.suggested_fix + corrected[end:]
                fixes_applied.append(f"AST fix: {error.error_type}")
        
        # Apply learned corrections
        if error_message:
            corrected, learned_fixes = self.corrector.correct_template(corrected, error_message)
            fixes_applied.extend(learned_fixes)
        
        # Re-validate
        ast, errors = self.parser.parse(corrected)
        is_valid = not errors
        
        return corrected, is_valid, fixes_applied
