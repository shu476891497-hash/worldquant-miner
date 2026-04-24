"""
Black Box Expression Compiler for FASTEXPR
Compiles expressions through multiple stages: Code → AST → IR → Final Expression

Compiler Pipeline:
1. Lexical Analysis: Tokenize source code
2. Parsing: Build AST from tokens
3. Semantic Analysis: Validate types and operators
4. Intermediate Representation: Transform AST to IR
5. Code Generation: Generate final expression with operators and data fields
6. Optimization: Optimize expression (optional)
"""

import logging
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from .fast_expr_ast import FASTEXPRParser, ASTNode, SyntaxError

logger = logging.getLogger(__name__)


class CompilerStage(Enum):
    """Compiler pipeline stages"""
    LEXICAL = "lexical"
    PARSING = "parsing"
    SEMANTIC = "semantic"
    IR = "intermediate_representation"
    CODE_GEN = "code_generation"
    OPTIMIZATION = "optimization"


@dataclass
class Token:
    """Token from lexical analysis"""
    token_type: str  # 'OPERATOR', 'FIELD', 'LITERAL', 'PAREN', 'ARITHMETIC'
    value: str
    position: Tuple[int, int]


@dataclass
class IRNode:
    """Intermediate Representation Node"""
    node_type: str  # 'operator_call', 'field_ref', 'literal', 'arithmetic'
    operator: Optional[str] = None
    field_id: Optional[str] = None
    literal_value: Optional[Any] = None
    arguments: List['IRNode'] = field(default_factory=list)
    arithmetic_op: Optional[str] = None
    left: Optional['IRNode'] = None
    right: Optional['IRNode'] = None
    metadata: Dict[str, Any] = field(default_factory=dict)  # Type info, validation results, etc.
    
    def to_expression(self) -> str:
        """Convert IR node to FASTEXPR expression"""
        if self.node_type == 'operator_call':
            args = ', '.join(arg.to_expression() for arg in self.arguments)
            return f"{self.operator}({args})"
        elif self.node_type == 'field_ref':
            return self.field_id if self.field_id else ""
        elif self.node_type == 'literal':
            return str(self.literal_value) if self.literal_value is not None else ""
        elif self.node_type == 'arithmetic':
            left_expr = self.left.to_expression() if self.left else ""
            right_expr = self.right.to_expression() if self.right else ""
            if left_expr and right_expr and self.arithmetic_op:
                return f"({left_expr} {self.arithmetic_op} {right_expr})"
            elif left_expr and self.arithmetic_op:  # Unary operator
                return f"({self.arithmetic_op}{left_expr})"
            else:
                return left_expr or right_expr or ""
        else:
            return ""


@dataclass
class CompilationResult:
    """Result of compilation process"""
    success: bool
    source_code: str
    tokens: List[Token] = field(default_factory=list)
    ast: Optional[ASTNode] = None
    ir: Optional[IRNode] = None
    final_expression: Optional[str] = None
    errors: List[SyntaxError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stage_reached: CompilerStage = CompilerStage.LEXICAL
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExpressionCompiler:
    """
    Black Box Expression Compiler
    
    Compiles FASTEXPR expressions through a multi-stage pipeline:
    1. Lexical Analysis: Tokenize input
    2. Parsing: Build AST
    3. Semantic Analysis: Validate
    4. IR Generation: Transform to intermediate representation
    5. Code Generation: Generate final expression
    6. Optimization: Optimize (optional)
    """
    
    def __init__(self, parser: FASTEXPRParser):
        """
        Initialize compiler
        
        Args:
            parser: FASTEXPR parser with operators and data fields
        """
        self.parser = parser
        self.optimization_enabled = False
    
    def compile(
        self,
        source_code: str,
        optimize: bool = False
    ) -> CompilationResult:
        """
        Compile source code through full pipeline
        
        Args:
            source_code: FASTEXPR source code
            optimize: Whether to apply optimizations
            
        Returns:
            CompilationResult with all stages
        """
        self.optimization_enabled = optimize
        result = CompilationResult(success=False, source_code=source_code)
        
        try:
            # Stage 1: Lexical Analysis
            result.tokens = self._lexical_analysis(source_code)
            result.stage_reached = CompilerStage.LEXICAL
            logger.debug(f"Lexical analysis: {len(result.tokens)} tokens")
            
            # Stage 2: Parsing
            ast, parse_errors = self.parser.parse(source_code)
            result.ast = ast
            result.errors.extend(parse_errors)
            if parse_errors:
                logger.warning(f"Parsing errors: {len(parse_errors)}")
                return result
            result.stage_reached = CompilerStage.PARSING
            logger.debug("Parsing: AST built successfully")
            
            # Stage 3: Semantic Analysis
            semantic_errors = self._semantic_analysis(ast, source_code)
            result.errors.extend(semantic_errors)
            if semantic_errors:
                logger.warning(f"Semantic errors: {len(semantic_errors)}")
                return result
            result.stage_reached = CompilerStage.SEMANTIC
            logger.debug("Semantic analysis: Validation passed")
            
            # Stage 4: IR Generation
            result.ir = self._generate_ir(ast)
            result.stage_reached = CompilerStage.IR
            logger.debug("IR generation: Intermediate representation created")
            
            # Stage 5: Code Generation
            result.final_expression = result.ir.to_expression()
            result.stage_reached = CompilerStage.CODE_GEN
            logger.debug(f"Code generation: {result.final_expression}")
            
            # Stage 6: Optimization (optional)
            if optimize:
                result.final_expression = self._optimize(result.final_expression, result.ir)
                result.stage_reached = CompilerStage.OPTIMIZATION
                logger.debug("Optimization: Applied")
            
            result.success = True
            result.metadata = {
                'operator_count': self._count_operators(ast),
                'field_count': self._count_fields(ast),
                'complexity': self._calculate_complexity(ast),
            }
            
        except Exception as e:
            logger.error(f"Compilation error: {e}", exc_info=True)
            result.errors.append(SyntaxError(
                'compilation_error',
                f'Compilation failed: {str(e)}',
                (0, len(source_code)),
                source_code
            ))
        
        return result
    
    def _lexical_analysis(self, source_code: str) -> List[Token]:
        """Stage 1: Tokenize source code"""
        tokens = []
        i = 0
        
        while i < len(source_code):
            # Skip whitespace
            if source_code[i].isspace():
                i += 1
                continue
            
            # Check for multi-character operators
            if i + 1 < len(source_code):
                two_char = source_code[i:i+2]
                if two_char in ['>=', '<=', '==', '!=', '&&', '||']:
                    tokens.append(Token('ARITHMETIC', two_char, (i, i+2)))
                    i += 2
                    continue
            
            # Single character arithmetic operators
            if source_code[i] in FASTEXPRParser.ARITHMETIC_OPERATORS:
                tokens.append(Token('ARITHMETIC', source_code[i], (i, i+1)))
                i += 1
                continue
            
            # Parentheses
            if source_code[i] in '()':
                tokens.append(Token('PAREN', source_code[i], (i, i+1)))
                i += 1
                continue
            
            # Numbers (literals)
            if source_code[i].isdigit() or source_code[i] == '-':
                start = i
                if source_code[i] == '-':
                    i += 1
                while i < len(source_code) and (source_code[i].isdigit() or source_code[i] == '.'):
                    i += 1
                tokens.append(Token('LITERAL', source_code[start:i], (start, i)))
                continue
            
            # Identifiers (operators or fields)
            if source_code[i].isalnum() or source_code[i] == '_':
                start = i
                while i < len(source_code) and (source_code[i].isalnum() or source_code[i] == '_' or source_code[i] == '.'):
                    i += 1
                value = source_code[start:i]
                # Determine if it's an operator or field
                if value in self.parser.operators:
                    tokens.append(Token('OPERATOR', value, (start, i)))
                else:
                    tokens.append(Token('FIELD', value, (start, i)))
                continue
            
            # Unknown character
            tokens.append(Token('UNKNOWN', source_code[i], (i, i+1)))
            i += 1
        
        return tokens
    
    def _semantic_analysis(self, ast: ASTNode, source_code: str) -> List[SyntaxError]:
        """Stage 3: Semantic analysis and validation with event input checking"""
        # Use parser's validation
        _, errors = self.parser.parse(source_code)
        
        # Additional event input compatibility check
        errors.extend(self._check_event_input_compatibility(ast, source_code))
        
        return errors
    
    def _check_event_input_compatibility(self, ast: ASTNode, source_code: str) -> List[SyntaxError]:
        """Check event input compatibility (learned from simulation errors)"""
        from .fast_expr_ast import SyntaxError
        errors = []
        
        if ast.node_type == 'function':
            operator_name = ast.value
            
            # Check all child nodes (fields/expressions)
            for child in ast.children:
                if child.node_type == 'field':
                    field_name = child.value
                    field_info = self.parser.data_fields.get(field_name, {})
                    
                    # Detect event input fields
                    is_event_input = (
                        field_info.get('type') == 'EVENT' or 
                        'event' in str(field_info.get('category', '')).lower() or
                        'event' in str(field_info.get('name', '')).lower()
                    )
                    
                    # Check if operator is known to be incompatible with event inputs
                    if is_event_input and operator_name in self.parser.event_input_incompatible_operators:
                        errors.append(SyntaxError(
                            'event_input_incompatible',
                            f'Operator {operator_name} does not support event inputs (field: {field_name})',
                            child.position,
                            source_code,
                            operator_name=operator_name,
                            field_name=field_name,
                            expected_type='NON_EVENT',
                            actual_type='EVENT'
                        ))
                
                # Recursively check nested expressions
                if child.children:
                    errors.extend(self._check_event_input_compatibility(child, source_code))
        
        return errors
    
    def _generate_ir(self, ast: ASTNode) -> IRNode:
        """Stage 4: Generate Intermediate Representation from AST"""
        if ast.node_type == 'function':
            # Operator call
            args = [self._generate_ir(child) for child in ast.children]
            return IRNode(
                node_type='operator_call',
                operator=ast.value,
                arguments=args,
                metadata={'operator_name': ast.value}
            )
        elif ast.node_type == 'field':
            # Field reference
            field_info = self.parser.data_fields.get(ast.value, {})
            return IRNode(
                node_type='field_ref',
                field_id=ast.value,
                metadata={
                    'field_type': self.parser.field_types.get(ast.value, 'REGULAR'),
                    'field_info': field_info
                }
            )
        elif ast.node_type == 'literal':
            # Literal value
            try:
                value = float(ast.value) if '.' in ast.value else int(ast.value)
            except:
                value = ast.value
            return IRNode(
                node_type='literal',
                literal_value=value
            )
        elif ast.node_type == 'arithmetic':
            # Arithmetic operation
            left = self._generate_ir(ast.children[0]) if len(ast.children) > 0 else None
            right = self._generate_ir(ast.children[1]) if len(ast.children) > 1 else None
            return IRNode(
                node_type='arithmetic',
                arithmetic_op=ast.value,
                left=left,
                right=right
            )
        else:
            # Fallback
            return IRNode(node_type='unknown')
    
    def _optimize(self, expression: str, ir: IRNode) -> str:
        """Stage 6: Optimize expression (optional)"""
        # Basic optimizations:
        # 1. Remove redundant parentheses
        # 2. Simplify arithmetic expressions
        # 3. Constant folding (if applicable)
        
        optimized = expression
        
        # Remove double parentheses: ((x)) -> (x)
        while '(((' in optimized or ')))' in optimized:
            optimized = optimized.replace('((', '(').replace('))', ')')
        
        # Remove unnecessary parentheses around single values
        # This is a simple optimization - more complex ones can be added
        
        return optimized
    
    def _count_operators(self, ast: ASTNode) -> int:
        """Count operators in AST"""
        count = 0
        if ast.node_type == 'function':
            count = 1
        for child in ast.children:
            count += self._count_operators(child)
        return count
    
    def _count_fields(self, ast: ASTNode) -> int:
        """Count fields in AST"""
        count = 0
        if ast.node_type == 'field':
            count = 1
        for child in ast.children:
            count += self._count_fields(child)
        return count
    
    def _calculate_complexity(self, ast: ASTNode) -> int:
        """Calculate expression complexity (depth + operators)"""
        if not ast:
            return 0
        
        depth = 1
        for child in ast.children:
            depth = max(depth, 1 + self._calculate_complexity(child))
        
        return depth
    
    def evaluate(
        self,
        expression: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        """
        Evaluate expression (for testing/debugging)
        
        Note: This is a simplified evaluator. Real evaluation happens in WorldQuant Brain.
        
        Args:
            expression: FASTEXPR expression
            context: Optional context with field values (for testing)
            
        Returns:
            Evaluation result (if evaluable)
        """
        result = self.compile(expression)
        if not result.success:
            logger.warning(f"Cannot evaluate invalid expression: {result.errors}")
            return None
        
        # For now, just return the compiled expression
        # Real evaluation would require WorldQuant Brain runtime
        return result.final_expression
    
    def transform(
        self,
        expression: str,
        transformations: List[str]
    ) -> Optional[str]:
        """
        Transform expression using compiler pipeline
        
        Args:
            expression: Source expression
            transformations: List of transformation names to apply
            
        Returns:
            Transformed expression or None if failed
        """
        result = self.compile(expression)
        if not result.success:
            return None
        
        # Apply transformations
        transformed_ir = result.ir
        for transform_name in transformations:
            transformed_ir = self._apply_transformation(transformed_ir, transform_name)
        
        return transformed_ir.to_expression() if transformed_ir else None
    
    def _apply_transformation(self, ir: IRNode, transform_name: str) -> IRNode:
        """Apply a transformation to IR"""
        # Placeholder for transformation logic
        # Can implement: field substitution, operator replacement, etc.
        return ir
