"""
Template Validator with Self-Correcting AST and V2 Prompt Engineering
Combines AST parsing with intelligent prompt-based correction
"""

import logging
import re
import time
import sqlite3
from typing import List, Dict, Optional, Tuple, Set
from .fast_expr_ast import FASTEXPRParser, SelfCorrectingAST, FASTEXPRValidator
from .expression_compiler import ExpressionCompiler, CompilationResult

logger = logging.getLogger(__name__)


class TemplateValidator:
    """
    Advanced template validator combining:
    1. Self-correcting AST parsing with operator-field compatibility
    2. V2-style prompt engineering
    3. Learning from simulation errors
    """
    
    def __init__(self, operators: List[Dict] = None, data_fields: List[Dict] = None, ollama_manager=None, db_path: str = None, use_ast: bool = False):
        """
        Initialize validator
        
        Args:
            operators: List of operator dicts from operatorRAW.json
            data_fields: List of data field dicts from API
            ollama_manager: Ollama manager for prompt-based correction
            db_path: Path to database for storing compiler knowledge (defaults to "generation_two_backtests.db")
            use_ast: Whether to use AST parsing for validation (default: False - uses prompt engineering only)
        """
        self.use_ast = use_ast
        self.db_path = db_path or "generation_two_backtests.db"
        
        # Only initialize AST components if AST is enabled
        if self.use_ast:
            self.parser = FASTEXPRParser(operators=operators, data_fields=data_fields)
            # Pass db_path to parser so it can be used by SelfCorrectingAST
            self.parser.db_path = self.db_path
            self.corrector = SelfCorrectingAST(self.parser)
            self.validator = FASTEXPRValidator(self.parser, self.corrector)
            # Initialize compiler for full compilation pipeline
            self.compiler = ExpressionCompiler(self.parser)
        else:
            # Store operators and data_fields for database-based validation
            self.operators = operators or []
            self.data_fields = data_fields or []
            self.parser = None
            self.corrector = None
            self.validator = None
            self.compiler = None
        
        self.ollama_manager = ollama_manager
        
        # V2-style error patterns
        self.error_patterns = {
            'unknown_variable': [
                r'unknown variable',
                r'undefined variable',
                r'variable.*not found',
            ],
            'invalid_field': [
                r'invalid field',
                r'field.*not found',
                r'unknown field',
            ],
            'syntax_error': [
                r'syntax error',
                r'invalid syntax',
                r'parse error',
            ],
            'type_error': [
                r'type error',
                r'type mismatch',
                r'incompatible types',
            ],
        }
    
    def _cleanup_template(self, template: str) -> str:
        """
        Clean up common syntax errors in generated templates
        
        Fixes:
        - Removes region prefixes (USA., EUR., CHN., etc.)
        - Removes leading + signs before fields
        - Fixes invalid * operator usage
        - Removes invalid commas
        - Fixes other common syntax issues
        """
        import re
        
        cleaned = template.strip()
        
        # Remove region prefixes (USA., EUR., CHN., ASI., GLB., IND.)
        cleaned = re.sub(r'\b(USA|EUR|CHN|ASI|GLB|IND)\.([a-z][a-z0-9_]+)\b', r'\2', cleaned, flags=re.IGNORECASE)
        
        # Remove leading + signs before fields or operators
        cleaned = re.sub(r'\(\s*\+([a-z][a-z0-9_]+)', r'(\1', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\(\s*\+([a-z_]+)\s*\(', r'(\1(', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\+\s*([a-z][a-z0-9_]+)\s*\)', r' \1)', cleaned, flags=re.IGNORECASE)
        
        # Fix invalid * operator at start (*(field -> multiply(field or just field)
        cleaned = re.sub(r'\(\s*\*\s*\(([a-z][a-z0-9_]+)', r'(\1', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\(\s*\*\s*([a-z][a-z0-9_]+)', r'(\1', cleaned, flags=re.IGNORECASE)
        
        # FASTEXPR DOES use commas for operator parameters!
        # Keep commas between field and parameter: operator(field, param) is CORRECT
        # Only remove commas in clearly wrong contexts (like between closing parens without operator)
        # Pattern: field, number or field, field - these are CORRECT (keep them)
        # Pattern: ), number or ), field - these might be wrong if not in operator context
        # For now, keep all commas - they're needed for operator parameters
        
        # Fix missing commas: ) number -> ), number (common error from LLM)
        # Pattern: ) followed by number or identifier -> ), number/identifier
        import re
        cleaned = re.sub(r'\)\s+(\d+)', r'), \1', cleaned)  # ) 20 -> ), 20
        cleaned = re.sub(r'\)\s+([a-z][a-z0-9_]+)', r'), \1', cleaned)  # ) field -> ), field
        
        # Fix double operators (rankrank -> rank, ts_meants_mean -> ts_mean)
        cleaned = re.sub(r'([a-z_]+)\1', r'\1', cleaned, flags=re.IGNORECASE)
        
        # Fix invalid operator combinations (add(field1 + field2) -> field1 + field2)
        cleaned = re.sub(r'\b(add|multiply|subtract|divide)\s*\(([^)]+\+[^)]+)\)', r'(\2)', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(add|multiply|subtract|divide)\s*\(([^)]+\*[^)]+)\)', r'(\2)', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(add|multiply|subtract|divide)\s*\(([^)]+-[^)]+)\)', r'(\2)', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(add|multiply|subtract|divide)\s*\(([^)]+/[^)]+)\)', r'(\2)', cleaned, flags=re.IGNORECASE)
        
        # Remove extra spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = cleaned.strip()
        
        # Fix unbalanced parentheses (remove trailing extra closing parens)
        # This can happen after deduplication of nested operators
        open_count = cleaned.count('(')
        close_count = cleaned.count(')')
        if close_count > open_count:
            # Remove trailing extra closing parentheses
            extra_closes = close_count - open_count
            # Remove from the end, but be careful not to break valid expressions
            # Only remove if they're clearly trailing
            while extra_closes > 0 and cleaned.endswith(')'):
                cleaned = cleaned[:-1]
                extra_closes -= 1
            if extra_closes > 0:
                logger.debug(f"⚠️ Template still has {extra_closes} extra closing parentheses after cleanup")
        
        return cleaned
    
    def validate_template(self, template: str, region: str = None, delay: int = None) -> Tuple[bool, str, Optional[str]]:
        """
        Validate template
        
        Returns:
            (is_valid, error_message, suggested_fix)
        """
        if not template or not template.strip():
            return False, "Empty template", None
        
        # Clean up common syntax errors first
        cleaned_template = self._cleanup_template(template)
        if cleaned_template != template:
            logger.info(f"🧹 Cleaned template: {template[:50]}... -> {cleaned_template[:50]}...")
            template = cleaned_template
        
        # If AST is disabled, only do basic validation (parentheses, syntax)
        if not self.use_ast:
            # Basic syntax validation only
            errors = self._validate_basic_syntax(template, region, delay)
            if not errors:
                return True, "", None
            error_msg = "; ".join(errors)
            return False, error_msg, None
        
        # AST validation (only if enabled)
        ast, errors = self.parser.parse(template)
        
        if not errors:
            return True, "", None
        
        # Collect error messages
        error_messages = [e.message for e in errors]
        error_msg = "; ".join(error_messages)
        
        # Try to suggest fixes
        suggested_fix = None
        if errors:
            # Use first error's suggested fix
            if errors[0].suggested_fix:
                suggested_fix = errors[0].suggested_fix
            else:
                # Try to generate fix using AST
                suggested_fix = self._generate_fix_from_ast(template, errors)
        
        return False, error_msg, suggested_fix
    
    def fix_template(self, template: str, error_message: str = None, region: str = None, delay: int = None) -> Tuple[str, List[str]]:
        """
        Fix template using both AST and prompt engineering
        
        Returns:
            (fixed_template, list of fixes applied)
        """
        fixes_applied = []
        
        # Method 1: AST-based correction (only if AST is enabled)
        fixed_ast = template
        if self.use_ast and self.validator:
            fixed_ast, is_valid, ast_fixes = self.validator.validate_and_fix(template, error_message)
            fixes_applied.extend(ast_fixes)
            
            if is_valid:
                return fixed_ast, fixes_applied
        
        # Method 2: V2-style prompt engineering (if Ollama available)
        if self.ollama_manager and error_message:
            fixed_prompt, prompt_fixes = self._fix_with_prompt_engineering(template, error_message, region, delay)
            if fixed_prompt and fixed_prompt != template:
                # Validate the prompt-fixed version
                is_valid, _, _ = self.validate_template(fixed_prompt, region, delay)
                if is_valid:
                    fixes_applied.append("Prompt engineering fix")
                    return fixed_prompt, fixes_applied
                else:
                    # Try combining both fixes
                    combined = self._combine_fixes(fixed_ast, fixed_prompt)
                    fixes_applied.append("Combined AST + prompt fix")
                    return combined, fixes_applied
        
        # Return AST fix even if not perfect
        return fixed_ast, fixes_applied
    
    def _validate_basic_syntax(self, template: str, region: str = None, delay: int = None) -> List[str]:
        """Basic syntax validation without AST (parentheses, basic checks)"""
        errors = []
        
        # Check balanced parentheses
        open_count = template.count('(')
        close_count = template.count(')')
        if open_count != close_count:
            errors.append(f"Unbalanced parentheses: {open_count} open, {close_count} close")
        
        # Check for empty template
        if not template.strip():
            errors.append("Empty template")
        
        # Check for event input compatibility (using database)
        if region and delay:
            event_input_errors = self._check_event_input_compatibility(template, region, delay)
            errors.extend(event_input_errors)
        
        return errors
    
    def _check_event_input_compatibility(self, template: str, region: str, delay: int) -> List[str]:
        """Check if template uses event inputs with incompatible operators (using database)"""
        errors = []
        import re
        
        # Get event input fields from database
        event_fields = self._get_event_input_fields(region, delay)
        if not event_fields:
            return errors
        
        # Get incompatible operators from database
        incompatible_ops = self._get_incompatible_operators()
        
        # Extract operators from template
        operator_pattern = r'\b([a-z_]+)\s*\('
        operators_used = re.findall(operator_pattern, template, re.IGNORECASE)
        
        # Extract field IDs from template
        field_pattern = r'\b([a-z][a-z0-9_]{10,})\b'
        fields_used = re.findall(field_pattern, template, re.IGNORECASE)
        
        # Check if any event input fields are used with incompatible operators
        event_fields_used = [f for f in fields_used if f.lower() in [ef.lower() for ef in event_fields]]
        incompatible_ops_used = [op for op in operators_used if op.lower() in [io.lower() for io in incompatible_ops]]
        
        if event_fields_used and incompatible_ops_used:
            # Check if they're used together (simplified check - if both exist in template)
            errors.append(f"Operator(s) {', '.join(incompatible_ops_used)} do not support event inputs (field(s): {', '.join(event_fields_used[:3])})")
        
        return errors
    
    def _get_incompatible_operators(self) -> Set[str]:
        """Get set of operators that don't support event inputs from database"""
        try:
            from ..storage.backtest_storage import BacktestStorage
            storage = BacktestStorage(self.db_path)
            
            import sqlite3
            conn = sqlite3.connect(storage.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT DISTINCT operator_name FROM compiler_knowledge 
                WHERE knowledge_type = 'event_input_incompatible' 
                AND compatibility_status = 'incompatible'
            ''')
            
            incompatible_ops = {row[0] for row in cursor.fetchall() if row[0]}
            conn.close()
            
            return incompatible_ops
        except Exception as e:
            logger.debug(f"Failed to get incompatible operators: {e}")
            # Return known incompatible operators as fallback
            return {'negative_colocation', 'add', 'subtract', 'multiply', 'divide', 'power', 'signed_power', 
                   'abs', 'log', 'sqrt', 'min', 'max', 'rank', 'delta', 'correlation'}
    
    def _fix_with_database_knowledge(self, template: str, error_message: str, region: str = None, delay: int = None) -> Tuple[str, List[str]]:
        """Fix template using database knowledge (event inputs, operator incompatibilities)"""
        import re
        fixes_applied = []
        fixed_template = template
        
        # Check for event input errors
        if 'does not support event inputs' in error_message.lower() or 'expects only event inputs' in error_message.lower():
            fixed_template, event_fixes = self._fix_event_input_error(fixed_template, error_message, region)
            fixes_applied.extend(event_fixes)
            # Learn and save the incompatible operator
            self._learn_event_input_compatibility(template, error_message)
        
        # Fix missing lookback parameter: "Required attribute 'lookback' must have a value"
        if "required attribute" in error_message.lower() and "lookback" in error_message.lower():
            fixed_template, lookback_fixes = self._fix_missing_lookback(fixed_template, error_message)
            fixes_applied.extend(lookback_fixes)
        
        # Fix missing comma: "Unexpected character 'X'" near ") X)"
        if "unexpected character" in error_message.lower():
            fixed_template, comma_fixes = self._fix_missing_comma(fixed_template, error_message)
            fixes_applied.extend(comma_fixes)
        
        # Fix unknown variable: "Attempted to use unknown variable"
        if "unknown variable" in error_message.lower() or "attempted to use unknown variable" in error_message.lower():
            fixed_template, var_fixes = self._fix_unknown_variable(fixed_template, error_message, region)
            fixes_applied.extend(var_fixes)
        
        # Fix unknown/inaccessible operator: "Attempted to use inaccessible or unknown operator"
        if ("unknown operator" in error_message.lower() or 
            "inaccessible" in error_message.lower() and "operator" in error_message.lower() or
            "attempted to use inaccessible" in error_message.lower()):
            fixed_template, op_fixes = self._fix_unknown_operator(fixed_template, error_message, region)
            fixes_applied.extend(op_fixes)
        
        return fixed_template, fixes_applied
    
    def _generate_fix_from_ast(self, template: str, errors: List) -> Optional[str]:
        """Generate fix from AST errors (only if AST is enabled)"""
        if not self.use_ast or not errors:
            return None
        
        # Simple fixes based on error type
        fixed = template
        for error in errors:
            if error.error_type == 'unbalanced_parens':
                # Try to balance parentheses
                open_count = template.count('(')
                close_count = template.count(')')
                if open_count > close_count:
                    fixed = fixed + ')' * (open_count - close_count)
                elif close_count > open_count:
                    fixed = ')' * (close_count - open_count) + fixed
            elif error.error_type == 'invalid_field' and error.suggested_fix:
                # Replace invalid field with suggested
                start, end = error.position
                fixed = fixed[:start] + error.suggested_fix + fixed[end:]
        
        return fixed if fixed != template else None
    
    def _load_operators_from_json(self) -> List[Dict]:
        """Load operators from operatorRAW.json with full definitions and descriptions"""
        import json
        import os
        
        # Try multiple possible paths
        possible_paths = [
            'generation_two/constants/operatorRAW.json',
            'constants/operatorRAW.json',
            '../constants/operatorRAW.json',
            '../../constants/operatorRAW.json',
            'operatorRAW.json'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        operators = json.load(f)
                    logger.debug(f"Loaded {len(operators)} operators from {path}")
                    return operators
                except Exception as e:
                    logger.debug(f"Failed to load operators from {path}: {e}")
                    continue
        
        logger.warning("Could not find operatorRAW.json, using stored operators")
        return self.operators or []
    
    def _fix_with_prompt_engineering(self, template: str, error_message: str, region: str = None, delay: int = None) -> Tuple[str, List[str]]:
        """Fix template using AI agent approach with multi-step diagnosis and fix - returns tuple for refeed compatibility"""
        if not self.ollama_manager:
            return template, []
        
        # Load operators from operatorRAW.json for accurate definitions
        operators_from_json = self._load_operators_from_json()
        
        # Get available operators and fields for context (from parser if AST enabled, otherwise from stored lists)
        if self.use_ast and self.parser:
            available_operators = list(self.parser.operators.keys())
            available_fields = list(self.parser.data_fields.keys())
            # Get full operator definitions from parser
            operator_definitions = []
            for op_name in available_operators:
                op_info = self.parser.operators.get(op_name, {})
                # Try to find in JSON for full definition
                json_op = next((op for op in operators_from_json if op.get('name') == op_name), None)
                operator_definitions.append({
                    'name': op_name,
                    'definition': json_op.get('definition', '') if json_op else op_info.get('definition', ''),
                    'description': json_op.get('description', '') if json_op else '',
                    'num_inputs': op_info.get('num_inputs', '?'),
                    'lookback': op_info.get('lookback', '?'),
                    'category': json_op.get('category', '') if json_op else op_info.get('category', '')
                })
        else:
            # Use stored operators and data_fields lists
            available_operators = [op.get('name', '') for op in self.operators if op.get('name')]
            available_fields = [field.get('id', '') for field in self.data_fields if field.get('id')]
            # Get full operator definitions from JSON (preferred) or stored operators list
            operator_definitions = []
            for op in (operators_from_json if operators_from_json else self.operators):
                if op.get('name'):
                    operator_definitions.append({
                        'name': op.get('name', ''),
                        'definition': op.get('definition', ''),
                        'description': op.get('description', ''),
                        'num_inputs': op.get('num_inputs', '?'),
                        'lookback': op.get('lookback', '?'),
                        'category': op.get('category', '')
                    })
        
        # Get event input fields from database for context
        event_input_fields = self._get_event_input_fields(region or 'USA', delay or 1)
        event_input_list = list(event_input_fields)[:10] if event_input_fields else []
        
        # Get incompatible operators from database for context
        incompatible_operators = self._get_incompatible_operators()
        incompatible_list = list(incompatible_operators)[:10] if incompatible_operators else []
        
        # Get successful templates from database
        successful_examples = []
        try:
            from ..storage.backtest_storage import BacktestStorage
            storage = BacktestStorage(self.db_path)
            import sqlite3
            conn = sqlite3.connect(storage.db_path)
            cursor = conn.cursor()
            # Get successful templates from backtest_results
            cursor.execute('''
                SELECT DISTINCT template FROM backtest_results 
                WHERE success = 1 AND template IS NOT NULL AND LENGTH(template) > 20
                ORDER BY sharpe DESC 
                LIMIT 5
            ''')
            successful_templates = [row[0] for row in cursor.fetchall() if row[0]]
            conn.close()
            successful_examples = successful_templates
        except Exception as e:
            logger.debug(f"Could not load successful templates: {e}")
        
        # Step 1: AI Agent Diagnosis
        diagnosis_prompt = f"""You are an AI diagnostic agent for WorldQuant Brain FASTEXPR expressions.

ERROR MESSAGE: {error_message}
BROKEN EXPRESSION: {template}

Analyze this error and identify:
1. What specific syntax error is present?
2. Where in the expression is the error located?
3. What is the root cause?

Common FASTEXPR errors:
- "Unexpected character 'X'" = Invalid character or missing operator/space
- "Unexpected end of input" = Missing closing parentheses or incomplete expression
- "does not support event inputs" = Wrong operator for event input fields
- "Invalid number of inputs : X, should be exactly Y" = Operator has wrong number of parameters
- "Required attribute 'lookback' must have a value" = Time-series operator missing required lookback parameter

DIAGNOSIS (be specific):"""

        try:
            diagnosis = self.ollama_manager.generate(diagnosis_prompt, max_tokens=200)
            logger.debug(f"AI Diagnosis: {diagnosis[:100] if diagnosis else 'None'}")
        except Exception as e:
            logger.debug(f"Diagnosis step failed: {e}")
            diagnosis = None
        
        # Step 2: AI Agent Fix with Examples
        examples_section = ""
        if successful_examples:
            examples_section = f"""

=== CORRECT EXAMPLES (learn from these) ===
{chr(10).join([f"Example {i+1}: {ex}" for i, ex in enumerate(successful_examples[:3])])}
"""
        
        fix_prompt = f"""You are an AI repair agent for WorldQuant Brain FASTEXPR expressions. Fix the broken expression.

=== ERROR ANALYSIS ===
Error: {error_message}
Broken Expression: {template}
{('Diagnosis: ' + diagnosis[:200] if diagnosis else '')}
{examples_section}

=== CRITICAL FASTEXPR SYNTAX (MUST FOLLOW EXACTLY) ===
1. OPERATOR SYNTAX WITH PARAMETERS: operator(field, parameter) - USE COMMAS!
   - COMMAS are REQUIRED between field and parameter
   - Example: ts_rank(DATA_FIELD1, 20) - COMMA between field and parameter
   - Example: winsorize(DATA_FIELD1, 4) - COMMA between field and parameter
   - Example: rank(DATA_FIELD1, DATA_FIELD2) - COMMA between multiple fields
   - WRONG: ts_rank(DATA_FIELD1 20) - missing comma
   - WRONG: winsorize(DATA_FIELD1 4) - missing comma

2. OPERATORS WITHOUT PARAMETERS: operator(field) - NO comma needed
   - Example: zscore(DATA_FIELD1) - no parameter, no comma
   - Example: rank(DATA_FIELD1) - no parameter, no comma

3. NESTED OPERATORS: operator1(operator2(field1, param2), param3)
   - All parentheses must be balanced
   - Example: rank(normalize(DATA_FIELD1), 20) - COMMA before parameter
   - Example: ts_rank(winsorize(DATA_FIELD1, 4), 10) - COMMAS in both operators

4. ARITHMETIC: DATA_FIELD1 + DATA_FIELD2, DATA_FIELD1 - DATA_FIELD2
   - Use spaces around operators: DATA_FIELD1 + DATA_FIELD2 NOT DATA_FIELD1+DATA_FIELD2
   - NO comma in arithmetic expressions

3. TIME-SERIES OPERATORS REQUIRE LOOKBACK PARAMETER:
   - Operators with "lookback=REQUIRED" MUST have a lookback value
   - Example: ts_rank(field, 20) - 20 is the lookback parameter
   - Example: ts_max(field, 10) - 10 is the lookback parameter
   - WRONG: ts_rank(field) - missing lookback parameter (will cause "Required attribute 'lookback' must have a value")
   - WRONG: ts_max(field) - missing lookback parameter
   - FIX: Add lookback parameter: ts_rank(field) -> ts_rank(field, 20)

4. OPERATOR INPUT COUNT REQUIREMENTS:
   - Operators have specific input count requirements (see operator info below)
   - Example: power(field1, field2) - requires exactly 2 inputs
   - Example: ts_rank(field, 20) - requires exactly 1 field input + 1 lookback parameter
   - WRONG: power(field1) - only 1 input, needs 2 (will cause "Invalid number of inputs : 1, should be exactly 2")
   - FIX: Add missing input: power(field1) -> power(field1, field2) or power(field1, 2)

5. COMMON FIXES:
   - "Required attribute 'lookback' must have a value":
     * Operator requires lookback parameter but it's missing
     * FIX: Add lookback value: ts_rank(field) -> ts_rank(field, 20)
     * Check operator info below for which operators require lookback
   
   - "Invalid number of inputs : X, should be exactly Y":
     * Operator has wrong number of inputs
     * FIX: Add or remove inputs to match required count
     * Check operator info below for input count requirements
   
   - "Unexpected character 'X'" near "Y) X)":
     * Likely missing COMMA before parameter
     * Check: ts_rank((DATA_FIELD1 + DATA_FIELD2), 20) - COMMA before 20
     * NOT: ts_rank((DATA_FIELD1 + DATA_FIELD2) 20) - missing comma
   
   - "Unexpected end of input":
     * Count opening ( and closing ) - they must match
     * Add missing closing parentheses at the end
   
   - Numbers as parameters: operator(field, 20) - COMMA required!

6. FIELD IDs: Use exact field IDs like "anl14_actvalue_capex_fp0"
   - NO region prefix (not "USA.field_id")
   - Must match available fields exactly

=== AVAILABLE OPERATORS (with full definitions from operatorRAW.json) ===
{self._format_operator_info_with_json(operator_definitions, error_message, operators_from_json)}

=== AVAILABLE FIELDS ===
{', '.join(available_fields[:30])}

=== YOUR TASK ===
Fix the expression following FASTEXPR syntax EXACTLY. Return ONLY the corrected expression, nothing else.
NO explanations, NO markdown, NO code blocks, NO prefixes, NO quotes.
Just the pure FASTEXPR expression.

FIXED EXPRESSION:"""

        fixed = None  # Initialize to avoid "cannot access local variable" error
        try:
            # Use higher max_tokens for complex fixes
            response = self.ollama_manager.generate(fix_prompt, max_tokens=800)
            if response:
                # Extract expression from response
                fixed = self._extract_expression_from_response(response)
                
                # Step 3: Validate and retry if needed
                if fixed and fixed != template:
                    # Quick validation: check parentheses balance
                    open_parens = fixed.count('(')
                    close_parens = fixed.count(')')
                    if open_parens == close_parens:
                        logger.info(f"✅ AI agent fixed template (diagnosis: {diagnosis[:50] if diagnosis else 'N/A'})")
                        return fixed, ["AI agent fix with diagnosis"]
                    else:
                        # Retry with balance fix
                        logger.debug(f"Retrying fix - parentheses unbalanced: {open_parens} open, {close_parens} close")
                        if open_parens > close_parens:
                            fixed = fixed + ')' * (open_parens - close_parens)
                        elif close_parens > open_parens:
                            fixed = '(' * (close_parens - open_parens) + fixed
                        logger.info(f"✅ AI agent fixed template (with balance correction)")
                        return fixed, ["AI agent fix with balance correction"]
        except Exception as e:
            logger.warning(f"AI agent fix failed: {e}")
        
        return template, []
    
    def _format_operator_info_with_json(self, operator_definitions: List[Dict], error_message: str, operators_from_json: List[Dict]) -> str:
        """Format operator info with full definitions and descriptions from operatorRAW.json"""
        import re
        
        # Extract operator name from error if possible
        error_operator = None
        if 'operator' in error_message.lower():
            # Try to extract operator name from error
            op_match = re.search(r'operator\s+(\w+)', error_message, re.IGNORECASE)
            if op_match:
                error_operator = op_match.group(1).lower()
        if not error_operator and 'lookback' in error_message.lower():
            match = re.search(r'(\w+).*lookback', error_message, re.IGNORECASE)
            if match:
                error_operator = match.group(1).lower()
        if not error_operator and 'invalid number of inputs' in error_message.lower():
            match = re.search(r'(\w+).*invalid number of inputs', error_message, re.IGNORECASE)
            if match:
                error_operator = match.group(1).lower()
        
        # Build operator info string with full definitions
        operator_info_lines = []
        
        # First, show operators relevant to the error with FULL definitions
        if error_operator:
            for op_def in operator_definitions:
                if op_def['name'].lower() == error_operator:
                    name = op_def['name']
                    definition = op_def.get('definition', '')
                    description = op_def.get('description', '')
                    category = op_def.get('category', '')
                    
                    info_parts = [f"⚠️ {name}"]
                    if definition:
                        info_parts.append(f"Definition: {definition}")
                    if description:
                        info_parts.append(f"Description: {description}")
                    if category:
                        info_parts.append(f"Category: {category}")
                    
                    operator_info_lines.append(' | '.join(info_parts))
                    break
        
        # Then show other common operators with their definitions (limit to 25 to avoid too long prompt)
        shown_count = len(operator_info_lines)
        for op_def in operator_definitions:
            if shown_count >= 25:
                break
            if error_operator and op_def['name'].lower() == error_operator:
                continue  # Already shown
            
            name = op_def['name']
            definition = op_def.get('definition', '')
            description = op_def.get('description', '')
            category = op_def.get('category', '')
            
            info_parts = [f"  {name}"]
            if definition:
                info_parts.append(f"Def: {definition}")
            if description:
                # Truncate long descriptions
                desc = description[:80] + '...' if len(description) > 80 else description
                info_parts.append(f"Desc: {desc}")
            
            operator_info_lines.append(' | '.join(info_parts))
            shown_count += 1
        
        return '\n'.join(operator_info_lines) if operator_info_lines else "No operator information available"
    
    def _format_operator_info(self, operator_definitions: List[Dict], error_message: str) -> str:
        """
        Format operator information for prompt, highlighting operators relevant to the error
        """
        # Extract operator name from error if present
        error_operator = None
        if 'lookback' in error_message.lower():
            # Try to find operator name in error message
            import re
            match = re.search(r'(\w+).*lookback', error_message, re.IGNORECASE)
            if match:
                error_operator = match.group(1).lower()
        elif 'invalid number of inputs' in error_message.lower():
            # Try to find operator name in error message
            import re
            match = re.search(r'(\w+).*invalid number of inputs', error_message, re.IGNORECASE)
            if match:
                error_operator = match.group(1).lower()
        
        # Build operator info string
        operator_info_lines = []
        
        # First, show operators relevant to the error
        if error_operator:
            for op_def in operator_definitions:
                if op_def['name'].lower() == error_operator:
                    num_inputs = op_def.get('num_inputs', '?')
                    lookback = op_def.get('lookback', '?')
                    definition = op_def.get('definition', '')
                    category = op_def.get('category', '')
                    
                    info_parts = [f"{op_def['name']}"]
                    if num_inputs != '?':
                        info_parts.append(f"inputs={num_inputs}")
                    if lookback != '?' and lookback:
                        info_parts.append(f"lookback=REQUIRED")
                    if definition:
                        info_parts.append(f"({definition[:50]})")
                    if category:
                        info_parts.append(f"[{category}]")
                    
                    operator_info_lines.append(f"⚠️ {': '.join(info_parts)}")
                    break
        
        # Then show other common operators (limit to 20 to avoid too long prompt)
        shown_count = len(operator_info_lines)
        for op_def in operator_definitions:
            if shown_count >= 20:
                break
            if error_operator and op_def['name'].lower() == error_operator:
                continue  # Already shown
            
            num_inputs = op_def.get('num_inputs', '?')
            lookback = op_def.get('lookback', '?')
            definition = op_def.get('definition', '')
            category = op_def.get('category', '')
            
            info_parts = [f"{op_def['name']}"]
            if num_inputs != '?':
                info_parts.append(f"inputs={num_inputs}")
            if lookback != '?' and lookback:
                info_parts.append(f"lookback=REQUIRED")
            if definition:
                info_parts.append(f"({definition[:40]})")
            
            operator_info_lines.append(f"  {': '.join(info_parts)}")
            shown_count += 1
        
        if not operator_info_lines:
            # Fallback: just show operator names
            return ', '.join([op.get('name', '') for op in operator_definitions[:30]])
        
        return '\n'.join(operator_info_lines)
    
    def _extract_expression_from_response(self, response: str) -> str:
        """Extract FASTEXPR expression from LLM response with improved parsing"""
        if not response:
            return ""
        
        # Remove markdown code blocks
        response = response.strip()
        
        # Remove ```fast or ```python or ``` or ```fast or ```fast
        while response.startswith('```'):
            lines = response.split('\n', 1)
            if len(lines) > 1:
                response = lines[1]
            else:
                response = ""
            response = response.strip()
            if response.endswith('```'):
                response = response[:-3].strip()
        
        # Remove common explanatory prefixes (case insensitive)
        explanatory_prefixes = [
            'here is the corrected fastexpr alpha expression:',
            'here is the corrected expression:',
            'here is the expression:',
            'the expression is:',
            'corrected expression:',
            'the corrected expression is:',
            'fastexpr expression:',
            'alpha expression:',
            'expression:',
            'fixed expression:',
            'the fixed expression is:',
            'corrected:',
            'fixed:',
            'answer:',
            'result:',
        ]
        
        response_lower = response.lower()
        for prefix in explanatory_prefixes:
            if response_lower.startswith(prefix):
                response = response[len(prefix):].strip()
                # Remove colon if present
                response = response.lstrip(':').strip()
                break
        
        # Remove quotes (both single and double, at start and end)
        response = response.strip('"\'')
        
        # Remove backticks (common error)
        response = response.replace('`', '')
        
        # Split into lines and find the best expression candidate
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        expression_candidates = []
        
        for line in lines:
            # Skip lines that are clearly not expressions
            if any(skip in line.lower() for skip in ['explanation', 'note:', 'tip:', 'remember:', 'example:']):
                continue
            
            # Remove backticks and quotes
            line = line.replace('`', '').strip('"\'')
            
            # Check if line looks like an expression
            # Must have parentheses and alphanumeric characters
            if '(' in line and ')' in line:
                # Count alphanumeric characters (should have operators and fields)
                alnum_count = sum(1 for c in line if c.isalnum() or c in '._')
                if alnum_count > 5:  # Minimum length check
                    # Remove trailing punctuation
                    line = line.rstrip('.,;!?')
                    # Remove any remaining backticks
                    line = line.replace('`', '')
                    expression_candidates.append(line)
        
        # If we found expression candidates, use the longest one (usually most complete)
        if expression_candidates:
            response = max(expression_candidates, key=len)
        elif lines:
            # Fallback: use first non-empty line
            response = lines[0]
            response = response.rstrip('.,;!?')
            response = response.replace('`', '').strip('"\'')
        
        # Final cleanup
        response = response.strip()
        response = response.replace('`', '')
        
        # Remove any leading/trailing quotes that might remain
        response = response.strip('"\'')
        
        return response
    
    def _combine_fixes(self, ast_fix: str, prompt_fix: str) -> str:
        """Combine AST fix and prompt fix intelligently"""
        # If prompt fix is valid, prefer it
        is_valid, _, _ = self.validate_template(prompt_fix)
        if is_valid:
            return prompt_fix
        
        # Otherwise, try to merge best parts
        # For now, return prompt fix as it's usually better
        return prompt_fix
    
    def refeed_with_correction(self, template: str, error_message: str, region: str = None, max_attempts: int = 3) -> Tuple[Optional[str], List[str]]:
        """
        V2-style refeed mechanism: Fix template using both AST and prompt engineering, then validate with compiler
        
        Args:
            template: Original template that failed
            error_message: Error message from simulation
            region: Region code
            max_attempts: Maximum number of correction attempts (ignored for event input errors - retries indefinitely)
            
        Returns:
            (fixed_template, list of fixes applied) or (None, []) if all attempts failed
        """
        current_template = template
        all_fixes = []
        
        # Check if this is an event input error - retry indefinitely
        is_event_input_error = 'does not support event inputs' in error_message.lower() or 'expects only event inputs' in error_message.lower()
        if is_event_input_error:
            max_attempts = 999  # Effectively unlimited retries
            logger.info("🔄 Event input error detected - will retry until successful")
        
        # Check if this is an "Invalid number of inputs" error - also retry indefinitely
        is_input_count_error = ('invalid number of inputs' in error_message.lower() or 
                               'should be exactly' in error_message.lower() or 
                               'should be at least' in error_message.lower())
        if is_input_count_error:
            max_attempts = 999  # Effectively unlimited retries
            logger.info("🔄 Invalid number of inputs error detected - will retry until successful")
        
        # Check if this is an "Unexpected character" error (missing comma) - also retry indefinitely
        is_unexpected_char_error = 'unexpected character' in error_message.lower()
        if is_unexpected_char_error:
            max_attempts = 999  # Effectively unlimited retries
            logger.info("🔄 Unexpected character error detected (likely missing comma) - will retry until successful")
        
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            logger.info(f"🔄 Refeed attempt {attempt}/{max_attempts} for error: {error_message[:60]}")
            
            # Step 0: Apply database knowledge fixes FIRST (lookback, missing comma, unknown variable, event inputs, unknown operator)
            db_fixed, db_fixes = self._fix_with_database_knowledge(current_template, error_message, region, None)
            if db_fixes:
                all_fixes.extend([f"DB: {f}" for f in db_fixes])
                current_template = db_fixed
                logger.info(f"🔧 Applied database knowledge fixes: {db_fixes}")
            
            # Step 1: Fix "Invalid number of inputs" errors (CRITICAL - retry until success)
            if is_input_count_error:
                logger.info("🔧 Applying fix for invalid number of inputs error...")
                fixed_template, input_fixes = self._fix_input_count_error(current_template, error_message)
                if input_fixes:
                    all_fixes.extend([f"InputCount: {f}" for f in input_fixes])
                    current_template = fixed_template
                    logger.info(f"🔧 Applied input count fix: {input_fixes}")
            
            # Step 1.1: Quick fix for common errors (like commas)
            if 'unexpected character' in error_message.lower() and ',' in error_message:
                # FASTEXPR DOES use commas for operator parameters (operator(field, param))
                # Only remove duplicate/malformed commas, not all commas
                if re.search(r'\)\s*,\s*,', current_template) or re.search(r',\s*,', current_template):
                    current_template = re.sub(r'\)\s*,\s*,', ') ', current_template)
                    current_template = re.sub(r',\s*,', ' ', current_template)
                    all_fixes.append("Removed duplicate/malformed commas")
                    logger.debug("Removed malformed commas from template")
                else:
                    # Don't remove commas - they're needed for operator parameters!
                    logger.debug("Comma found but not removing - needed for operator parameters")
            
            # Step 1.5: Fix event input errors by replacing operators (CRITICAL - retry until success)
            if is_event_input_error:
                # ALWAYS use aggressive fix for event input errors to ensure ALL operators are replaced
                logger.info("🔧 Applying aggressive event input fix to replace ALL incompatible operators...")
                current_template = self._aggressive_event_input_fix(current_template, error_message, region)
                all_fixes.append("Applied aggressive event input fix (replaced all incompatible operators)")
                
                # Also try targeted fix for the specific operator mentioned in error
                fixed_template, operator_fixes = self._fix_event_input_error(current_template, error_message, region)
                if operator_fixes:
                    all_fixes.extend([f"EventInput: {f}" for f in operator_fixes])
                    current_template = fixed_template
                    logger.info(f"🔧 Also applied targeted fix: {operator_fixes}")
                
                # Learn this pattern
                self._learn_event_input_compatibility(current_template, error_message)
            
            # Step 2: AST-based correction (only if AST is enabled)
            if self.use_ast and self.validator:
                ast_fixed, ast_fixes = self._fix_with_ast(current_template, error_message, region)
                if ast_fixes:
                    all_fixes.extend([f"AST: {f}" for f in ast_fixes])
                    current_template = ast_fixed
                    logger.debug(f"AST fixes applied: {ast_fixes}")
            
            # Step 3: Prompt engineering correction (SKIP for event input errors, input count errors, and unexpected character errors to avoid regenerating with same issues)
            if not is_event_input_error and not is_input_count_error and not is_unexpected_char_error:
                prompt_fixed, prompt_fixes = self._fix_with_prompt_engineering(current_template, error_message, region, None)
                if prompt_fixes:
                    all_fixes.extend([f"Prompt: {f}" for f in prompt_fixes])
                    current_template = prompt_fixed
                    logger.debug(f"Prompt fixes applied: {prompt_fixes}")
            else:
                if is_event_input_error:
                    logger.debug("Skipping prompt engineering for event input error (to avoid regenerating with same operators)")
                if is_input_count_error:
                    logger.debug("Skipping prompt engineering for input count error (to avoid regenerating with same parameter count)")
                if is_unexpected_char_error:
                    logger.debug("Skipping prompt engineering for unexpected character error (already fixed with database knowledge)")
            
            # Step 4: Compiler validation (compiler working principle as code)
            compile_result = self.compile_template(current_template, optimize=False)
            if compile_result.success:
                logger.info(f"✅ Refeed successful after {attempt} attempt(s) - template compiled")
                # Learn from successful fix
                self.learn_from_simulation_error(template, error_message, current_template)
                return current_template, all_fixes
            else:
                # Compiler found errors, try again with new error info
                if compile_result.errors:
                    error_msg = compile_result.errors[0].message
                    logger.debug(f"Compiler error (attempt {attempt}): {error_msg}, retrying...")
                    # Check if it's still the same type of error
                    if 'does not support event inputs' in error_msg.lower() or 'expects only event inputs' in error_msg.lower():
                        # Still event input error - continue loop with new error message
                        error_message = error_msg
                        is_event_input_error = True
                        logger.warning(f"⚠️ Still event input error after fix, retrying with: {error_msg[:50]}")
                    elif ('invalid number of inputs' in error_msg.lower() or 
                          'should be exactly' in error_msg.lower() or 
                          'should be at least' in error_msg.lower()):
                        # Still input count error - continue loop with new error message
                        error_message = error_msg
                        is_input_count_error = True
                        logger.warning(f"⚠️ Still input count error after fix, retrying with: {error_msg[:50]}")
                    elif 'unexpected character' in error_msg.lower():
                        # Still unexpected character error (like missing comma) - continue loop with new error message
                        error_message = error_msg
                        is_unexpected_char_error = True
                        logger.warning(f"⚠️ Still unexpected character error after fix, retrying with: {error_msg[:50]}")
                    else:
                        # Different error - use it for next attempt
                        error_message = error_msg
                        # Update error type flags
                        is_event_input_error = 'does not support event inputs' in error_msg.lower() or 'expects only event inputs' in error_msg.lower()
                        is_input_count_error = ('invalid number of inputs' in error_msg.lower() or 
                                               'should be exactly' in error_msg.lower() or 
                                               'should be at least' in error_msg.lower())
                else:
                    # Try traditional validation
                    is_valid, error_msg, _ = self.validate_template(current_template, region)
                    if is_valid:
                        logger.info(f"✅ Refeed successful - template validated")
                        self.learn_from_simulation_error(template, error_message, current_template)
                        return current_template, all_fixes
                    else:
                        error_message = error_msg
        
        # All attempts failed
        logger.warning(f"❌ Refeed failed after {max_attempts} attempts")
        # Still learn from the error
        self.learn_from_simulation_error(template, error_message, None)
        return None, all_fixes
    
    def _get_event_input_fields(self, region: str, delay: int = 1) -> Set[str]:
        """Get set of event input field IDs for a region and delay"""
        try:
            from ..storage.backtest_storage import BacktestStorage
            storage = BacktestStorage(self.db_path)
            
            import sqlite3
            conn = sqlite3.connect(storage.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT field_id FROM field_types 
                WHERE region = ? AND delay = ? AND is_event_input = 1
            ''', (region, delay))
            
            event_fields = {row[0] for row in cursor.fetchall()}
            conn.close()
            
            return event_fields
        except Exception as e:
            logger.debug(f"Failed to get event input fields: {e}")
            return set()
    
    def _aggressive_event_input_fix(self, template: str, error_message: str, region: str = None) -> str:
        """Aggressively fix event input errors by replacing ALL incompatible operators (including arithmetic operators in expressions)"""
        import re
        
        fixed_template = template
        
        # Replace ALL instances of incompatible operators with ts_* versions
        # First pass: Replace function calls (operator(...))
        function_replacements = [
            (r'\badd\s*\(', 'ts_add('),
            (r'\bsubtract\s*\(', 'ts_subtract('),
            (r'\bmultiply\s*\(', 'ts_multiply('),
            (r'\bdivide\s*\(', 'ts_divide('),
            (r'\bpower\s*\(', 'ts_power('),
            (r'\bsigned_power\s*\(', 'ts_signed_power('),
            (r'\babs\s*\(', 'ts_abs('),
            (r'\blog\s*\(', 'ts_log('),
            (r'\bsqrt\s*\(', 'ts_sqrt('),
            (r'\bmin\s*\(', 'ts_min('),
            (r'\bmax\s*\(', 'ts_max('),
            (r'\brank\s*\(', 'ts_rank('),
            (r'\bdelta\s*\(', 'ts_delta('),
            (r'\bcorrelation\s*\(', 'ts_correlation('),
            (r'\breverse\s*\(', 'ts_reverse('),
        ]
        
        # Apply function call replacements (multiple passes for nested cases)
        for _ in range(5):
            for pattern, replacement in function_replacements:
                if re.search(pattern, fixed_template, re.IGNORECASE):
                    fixed_template = re.sub(pattern, replacement, fixed_template, flags=re.IGNORECASE)
        
        # Second pass: Replace arithmetic operators in expressions (field1 + field2 -> ts_add(field1, field2))
        # Only replace if both sides are field identifiers (not already in function calls)
        # Pattern: field_id + field_id (but not inside function calls)
        arithmetic_replacements = [
            # Match: field_id + field_id (but be careful with parentheses)
            (r'([a-z][a-z0-9_]{10,})\s*\+\s*([a-z][a-z0-9_]{10,})', r'ts_add(\1, \2)'),
            (r'([a-z][a-z0-9_]{10,})\s*-\s*([a-z][a-z0-9_]{10,})', r'ts_subtract(\1, \2)'),
            (r'([a-z][a-z0-9_]{10,})\s*\*\s*([a-z][a-z0-9_]{10,})', r'ts_multiply(\1, \2)'),
            (r'([a-z][a-z0-9_]{10,})\s*/\s*([a-z][a-z0-9_]{10,})', r'ts_divide(\1, \2)'),
        ]
        
        # Apply arithmetic replacements (multiple passes for nested expressions)
        for _ in range(3):
            for pattern, replacement in arithmetic_replacements:
                if re.search(pattern, fixed_template, re.IGNORECASE):
                    fixed_template = re.sub(pattern, replacement, fixed_template, flags=re.IGNORECASE)
        
        # Also handle standalone arithmetic operators (not in function calls)
        # Replace: field1 + field2 (when not already in a function)
        # This is tricky, so we'll do a simpler approach: replace all +, -, *, / between identifiers
        # But we need to be careful not to break function calls
        
        logger.info(f"🔧 Aggressive fix applied: {template[:50]}... -> {fixed_template[:50]}...")
        return fixed_template
    
    def _fix_event_input_error(self, template: str, error_message: str, region: str = None) -> Tuple[str, List[str]]:
        """
        Fix event input errors by replacing incompatible operators
        
        Args:
            template: Template with event input error
            error_message: Error message mentioning event inputs
            region: Region code (for field type lookup)
            
        Returns:
            (fixed_template, list of fixes)
        """
        import re
        fixes = []
        fixed_template = template
        
        # Extract operator name from error message
        # Pattern: "Operator X does not support event inputs" or "Operator X expects only event inputs"
        operator_match = re.search(r'Operator\s+(\w+)\s+(?:does not support|expects only)\s+event inputs', error_message, re.IGNORECASE)
        if not operator_match:
            # Try alternative pattern
            operator_match = re.search(r'(\w+)\s+(?:does not support|expects only)\s+event inputs', error_message, re.IGNORECASE)
        
        if operator_match:
            problematic_operator = operator_match.group(1)
            
            # Map of operators that don't support event inputs to replacements
            # Event input compatible operators: vec_*, ts_* (some), event-specific operators
            # Non-event operators: arithmetic (add, subtract, multiply, divide), cross-sectional (rank, winsorize, zscore)
            event_input_replacements = {
                'multiply': 'ts_multiply',  # Time series version
                'add': 'ts_add',
                'subtract': 'ts_subtract',
                'divide': 'ts_divide',
                'power': 'ts_power',
                'signed_power': 'ts_signed_power',
                'abs': 'ts_abs',
                'log': 'ts_log',
                'sqrt': 'ts_sqrt',
                'min': 'ts_min',
                'max': 'ts_max',
                'rank': 'ts_rank',  # Time series rank instead of cross-sectional
                'delta': 'ts_delta',
                'correlation': 'ts_correlation',
                'winsorize': 'ts_winsorize',  # Try ts_ version if exists
                'zscore': 'ts_zscore',  # Try ts_ version
                'reverse': 'ts_reverse',  # Time series reverse
            }
            
            # Try to find replacement
            replacement = event_input_replacements.get(problematic_operator.lower())
            
            if replacement:
                # Replace operator in template
                # Pattern: operator_name( or operator_name (with space)
                pattern = r'\b' + re.escape(problematic_operator) + r'\s*\('
                if re.search(pattern, fixed_template, re.IGNORECASE):
                    fixed_template = re.sub(pattern, replacement + '(', fixed_template, flags=re.IGNORECASE)
                    fixes.append(f"Replaced {problematic_operator} with {replacement} (event input compatible)")
                    logger.info(f"🔄 Replaced {problematic_operator} -> {replacement} for event input compatibility")
                else:
                    # Try without parentheses
                    pattern = r'\b' + re.escape(problematic_operator) + r'\b'
                    fixed_template = re.sub(pattern, replacement, fixed_template, flags=re.IGNORECASE)
                    fixes.append(f"Replaced {problematic_operator} with {replacement} (event input compatible)")
            else:
                # No direct replacement - try wrapping with ts_* or using vec_* operators
                # For arithmetic operators, try ts_* prefix
                if problematic_operator in ['multiply', 'add', 'subtract', 'divide']:
                    ts_version = 'ts_' + problematic_operator
                    pattern = r'\b' + re.escape(problematic_operator) + r'\s*\('
                    if re.search(pattern, fixed_template, re.IGNORECASE):
                        fixed_template = re.sub(pattern, ts_version + '(', fixed_template, flags=re.IGNORECASE)
                        fixes.append(f"Replaced {problematic_operator} with {ts_version} (event input compatible)")
                else:
                    # For cross-sectional operators, try removing or wrapping
                    logger.warning(f"⚠️ No replacement found for {problematic_operator} with event inputs")
                    fixes.append(f"Could not find replacement for {problematic_operator}")
        
        # If still no replacement found, try to identify event input fields and replace operators
        if not fixes and region:
            # Get event input fields for this region
            event_fields = self._get_event_input_fields(region, delay=1)
            
            # Check if template uses event input fields
            field_pattern = r'\b([a-z][a-z0-9_]{10,})\b'
            template_fields = set(re.findall(field_pattern, template))
            
            if template_fields.intersection(event_fields) if event_fields else True:  # Assume true if unknown
                # Template uses event inputs - replace all incompatible operators
                logger.info(f"🔧 Template uses event input fields, replacing all incompatible operators")
                fixed_template = self._aggressive_event_input_fix(template, error_message, region)
                if fixed_template != template:
                    fixes.append("Replaced all incompatible operators with ts_* versions for event inputs")
                    return fixed_template, fixes
        
        return fixed_template, fixes
    
    def _learn_event_input_compatibility(self, template: str, error_message: str):
        """Learn about event input compatibility from errors and store in database"""
        import re
        logger.info(f"📚 _learn_event_input_compatibility called for: {error_message[:100]}")
        
        # Extract operator and learn that it doesn't support event inputs
        # Try multiple patterns to catch different error message formats
        operator_match = re.search(r'Operator\s+(\w+)\s+(?:does not support|expects only)\s+event inputs', error_message, re.IGNORECASE)
        if not operator_match:
            operator_match = re.search(r'(\w+)\s+(?:does not support|expects only)\s+event inputs', error_message, re.IGNORECASE)
        if not operator_match:
            # Try pattern: "Operator X does not support event inputs" or "X does not support event inputs"
            operator_match = re.search(r'(?:Operator\s+)?(\w+)\s+does\s+not\s+support\s+event\s+inputs', error_message, re.IGNORECASE)
        if not operator_match:
            # Try pattern: "Operator X expects only event inputs"
            operator_match = re.search(r'(?:Operator\s+)?(\w+)\s+expects\s+only\s+event\s+inputs', error_message, re.IGNORECASE)
        
        if operator_match:
            logger.info(f"📚 Found operator match: {operator_match.group(1)}")
            operator_name = operator_match.group(1).lower()
            
            # Store in parser's knowledge base (in-memory) - only if AST is enabled
            if self.use_ast and self.parser:
                if not hasattr(self.parser, 'event_input_incompatible_operators'):
                    self.parser.event_input_incompatible_operators = set()
                self.parser.event_input_incompatible_operators.add(operator_name)
            
            # Store in database for persistence (always, regardless of AST setting)
            try:
                from ..storage.backtest_storage import BacktestStorage
                storage = BacktestStorage(self.db_path)
                
                # Extract replacement operator if available
                replacement = None
                if hasattr(self, '_fix_event_input_error'):
                    # Check replacement mapping
                    event_input_replacements = {
                        'multiply': 'ts_multiply',
                        'add': 'ts_add',
                        'subtract': 'ts_subtract',
                        'divide': 'ts_divide',
                        'rank': 'ts_rank',
                        'power': 'ts_power',
                        'signed_power': 'ts_signed_power',
                        'abs': 'ts_abs',
                        'log': 'ts_log',
                        'sqrt': 'ts_sqrt',
                        'min': 'ts_min',
                        'max': 'ts_max',
                        'delta': 'ts_delta',
                        'correlation': 'ts_correlation',
                        'reverse': 'ts_reverse',
                        'negative_colocation': None,  # No direct replacement
                    }
                    replacement = event_input_replacements.get(operator_name)
                
                # Extract AST pattern from template (only if AST is enabled)
                ast_pattern = None
                if self.use_ast and self.parser:
                    try:
                        ast, _ = self.parser.parse(template)
                        if ast:
                            ast_pattern = self._extract_ast_structure(ast)
                    except:
                        pass
                
                logger.info(f"📚 Calling store_compiler_knowledge for operator: {operator_name}, replacement: {replacement}")
                logger.info(f"📚 Database path: {self.db_path}")
                
                result = storage.store_compiler_knowledge(
                    knowledge_type='event_input_incompatible',
                    operator_name=operator_name,
                    compatibility_status='incompatible',
                    error_message=error_message,
                    learned_from_template=template,
                    learned_from_error=error_message,
                    replacement_operator=replacement,
                    ast_pattern=ast_pattern,
                    compiler_rule=f"Operator {operator_name} does not support event inputs. Use {replacement} instead." if replacement else f"Operator {operator_name} does not support event inputs.",
                    metadata={'learned_at': time.time()}
                )
                
                if result:
                    logger.info(f"✅ Successfully stored compiler knowledge: {operator_name} does not support event inputs (replacement: {replacement})")
                else:
                    logger.error(f"❌ store_compiler_knowledge returned False for operator: {operator_name}")
            except Exception as e:
                logger.error(f"❌ Failed to store compiler knowledge: {e}", exc_info=True)
                logger.error(f"❌ Database path was: {self.db_path}")
        else:
            # Even if we can't extract operator name, store the error for learning
            logger.warning(f"⚠️ Could not extract operator name from error message: {error_message[:100]}")
            # Try to extract any operator name from the template
            import re
            operators_in_template = re.findall(r'\b([a-z_]+)\s*\(', template.lower())
            if operators_in_template:
                # Store knowledge for the first operator found
                operator_name = operators_in_template[0]
                logger.info(f"📚 Using first operator from template: {operator_name}")
                try:
                    from ..storage.backtest_storage import BacktestStorage
                    storage = BacktestStorage(self.db_path)
                    result = storage.store_compiler_knowledge(
                        knowledge_type='event_input_incompatible',
                        operator_name=operator_name,
                        compatibility_status='incompatible',
                        error_message=error_message,
                        learned_from_template=template,
                        learned_from_error=error_message,
                        replacement_operator=None,
                        ast_pattern=None,
                        compiler_rule=f"Operator {operator_name} may not support event inputs (extracted from template)",
                        metadata={'learned_at': time.time(), 'extracted_from_template': True}
                    )
                    if result:
                        logger.info(f"✅ Stored compiler knowledge (extracted operator): {operator_name}")
                except Exception as e:
                    logger.error(f"❌ Failed to store compiler knowledge (extracted): {e}", exc_info=True)
    
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
    
    def _fix_with_ast(self, template: str, error_message: str, region: str = None) -> Tuple[str, List[str]]:
        """Fix template using AST-based correction"""
        fixes = []
        corrected = template
        
        # Use self-correcting AST (only if enabled)
        if self.use_ast and self.corrector:
            corrected, ast_fixes = self.corrector.correct_template(corrected, error_message)
            fixes.extend(ast_fixes)
        
        return corrected, fixes
    
    def learn_from_simulation_error(self, template: str, error_message: str, fixed_template: Optional[str] = None):
        """Learn from simulation error with enhanced feedback - stores to both compiler knowledge and AST patterns"""
        logger.info(f"📚 LEARNING FROM ERROR: {error_message[:100]}")
        logger.info(f"📚 Template: {template[:100]}")
        logger.info(f"📚 Database path: {self.db_path}")
        
        # Extract error details for better learning
        error_type = self._classify_error_from_message(error_message)
        
        # Learn event input compatibility if applicable (stores to compiler_knowledge table)
        if 'event input' in error_message.lower():
            logger.info(f"📚 Detected event input error - calling _learn_event_input_compatibility")
            self._learn_event_input_compatibility(template, error_message)
        
        # Try to generate a fix if not provided
        if not fixed_template:
            try:
                fixed_template, _ = self.fix_template(template, error_message)
            except Exception as e:
                logger.debug(f"Error generating fix in learn_from_simulation_error: {e}")
                fixed_template = template  # Use original template if fix generation fails
        
        # Learn from the error (stores to JSON file) - only if AST is enabled
        if self.use_ast and self.corrector:
            self.corrector.learn_from_error(template, error_message, fixed_template)
        
        # ALWAYS store AST pattern for failed templates (for learning what NOT to do) - only if AST is enabled
        if self.use_ast and self.parser:
            try:
                ast, errors = self.parser.parse(template)
                if ast:
                    # Extract AST structure
                    ast_structure = self._extract_ast_structure(ast)
                    
                    # Extract operators and field types
                    operators = []
                    field_types = []
                    self._extract_operators_and_fields_from_ast(ast, operators, field_types)
                    
                    # Store failed AST pattern in database
                    from ..storage.backtest_storage import BacktestStorage
                    storage = BacktestStorage(self.db_path)
                    logger.info(f"📚 Calling store_ast_pattern for failed pattern, database: {self.db_path}")
                    
                    result = storage.store_ast_pattern(
                        pattern_type='failed',
                        pattern_structure=ast_structure,
                        operator_sequence=operators,
                        field_types=field_types,
                        example_template=template,
                        success=False,
                        metadata={'error_message': error_message[:200], 'error_type': error_type}  # Store error for reference
                    )
                    
                    if result:
                        logger.info(f"✅ Stored failed AST pattern: {ast_structure[:50]}... (error: {error_message[:50]})")
                    else:
                        logger.error(f"❌ store_ast_pattern returned False")
            except Exception as e:
                logger.error(f"❌ Failed to store failed AST pattern: {e}", exc_info=True)
        
        # Update parser with learned corrections - only if AST is enabled
        if self.use_ast and self.parser and fixed_template and fixed_template != template:
            # Parse the fixed template to validate
            ast, errors = self.parser.parse(fixed_template)
            if not errors:
                logger.info(f"📚 Learned from error: {error_message[:50]} -> Fixed template validated")
            else:
                logger.warning(f"⚠️ Fixed template still has errors: {errors[0].message if errors else 'Unknown'}")
        else:
            logger.info(f"📚 Learned from error: {error_message[:50]} (no fix generated)")
    
    def _extract_operators_and_fields_from_ast(self, ast, operators: List, field_types: List):
        """Extract operators and field types from AST"""
        if ast.node_type == 'function':
            operators.append(ast.value)
        elif ast.node_type == 'field':
            field_type = self.parser.field_types.get(ast.value, 'UNKNOWN')
            field_types.append(field_type)
        
        for child in ast.children:
            self._extract_operators_and_fields_from_ast(child, operators, field_types)
    
    def _classify_error_from_message(self, error_message: str) -> str:
        """Classify error type from WorldQuant API error message"""
        error_lower = error_message.lower()
        
        for error_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if re.search(pattern, error_lower):
                    return error_type
        
        return 'unknown_error'
    
    def learn_from_success(self, template: str):
        """Learn from successful template (only if AST is enabled)"""
        if self.use_ast and self.corrector:
            self.corrector.learn_from_success(template)
    
    def compile_template(
        self,
        template: str,
        optimize: bool = False
    ) -> CompilationResult:
        """
        Compile template through full compiler pipeline
        
        Args:
            template: FASTEXPR template to compile
            optimize: Whether to apply optimizations
            
        Returns:
            CompilationResult with all compilation stages
        """
        if not self.use_ast or not self.compiler:
            # Return a mock result if AST is disabled
            from .expression_compiler import CompilationResult, CompilerStage
            return CompilationResult(
                success=True,
                source_code=template,
                final_expression=template,
                stage_reached=CompilerStage.CODE_GEN
            )
        return self.compiler.compile(template, optimize=optimize)
    
    def _fix_input_count_error(self, template: str, error_message: str) -> Tuple[str, List[str]]:
        """
        Fix "Invalid number of inputs" errors by adjusting operator parameters
        
        Args:
            template: Template with input count error
            error_message: Error message like "Invalid number of inputs : 2, should be exactly 1 input(s)"
            
        Returns:
            (fixed_template, list of fixes)
        """
        import re
        fixes = []
        fixed_template = template
        
        # Extract operator name and expected/actual input count from error message
        # Pattern: "Invalid number of inputs : 2, should be exactly 1 input(s)"
        # Or: "Invalid number of inputs : 1, should be at least 2 input(s)"
        # Or: "Operator X expects 1 input(s), got 2"
        input_count_match = re.search(r'invalid number of inputs\s*:\s*(\d+)\s*,\s*should be exactly\s*(\d+)', error_message, re.IGNORECASE)
        if not input_count_match:
            # Try "should be at least"
            input_count_match = re.search(r'invalid number of inputs\s*:\s*(\d+)\s*,\s*should be at least\s*(\d+)', error_message, re.IGNORECASE)
        if not input_count_match:
            input_count_match = re.search(r'expects\s+(\d+)\s+input', error_message, re.IGNORECASE)
            if input_count_match:
                expected = int(input_count_match.group(1))
                # Try to find actual count
                got_match = re.search(r'got\s+(\d+)', error_message, re.IGNORECASE)
                actual = int(got_match.group(1)) if got_match else None
            else:
                expected = None
                actual = None
        else:
            actual = int(input_count_match.group(1))
            expected = int(input_count_match.group(2))
        
        if expected is not None and actual is not None:
            logger.info(f"🔧 Fixing input count: operator has {actual} inputs, needs {expected}")
            
            # Find operators in template that might have wrong parameter count
            # Pattern: operator_name(param1, param2, ...)
            operator_pattern = r'\b([a-z_]+)\s*\('
            operators = re.finditer(operator_pattern, fixed_template, re.IGNORECASE)
            
            for op_match in operators:
                op_name = op_match.group(1)
                op_start = op_match.start()
                
                # Find the matching closing parenthesis
                paren_count = 0
                i = op_match.end() - 1  # Start from opening paren
                while i < len(fixed_template):
                    if fixed_template[i] == '(':
                        paren_count += 1
                    elif fixed_template[i] == ')':
                        paren_count -= 1
                        if paren_count == 0:
                            # Found matching closing paren
                            op_end = i + 1
                            
                            # Count parameters (split by comma, but not inside nested parens)
                            params = []
                            current_param = ""
                            nested_parens = 0
                            param_start = op_match.end()
                            for j in range(param_start, op_end - 1):
                                char = fixed_template[j]
                                if char == '(':
                                    nested_parens += 1
                                    current_param += char
                                elif char == ')':
                                    nested_parens -= 1
                                    current_param += char
                                elif char == ',' and nested_parens == 0:
                                    if current_param.strip():
                                        params.append(current_param.strip())
                                    current_param = ""
                                else:
                                    current_param += char
                            
                            if current_param.strip():
                                params.append(current_param.strip())
                            
                            param_count = len(params)
                            
                            # If this operator has the wrong number of parameters, fix it
                            if param_count == actual and expected == 1:
                                # Too many parameters - remove extra ones, keep first
                                if len(params) > 0:
                                    fixed_call = f"{op_name}({params[0]})"
                                    fixed_template = fixed_template[:op_start] + fixed_call + fixed_template[op_end:]
                                    fixes.append(f"Reduced {op_name} parameters from {param_count} to 1 (kept first parameter)")
                                    logger.info(f"🔧 Fixed {op_name}: removed extra parameters, kept first")
                                    break  # Fix one at a time
                            elif param_count == actual and expected > 1:
                                # Too few parameters - this is harder, might need to duplicate or add default
                                # For now, try to add a default value (1 or 0)
                                if len(params) == 1:
                                    # Add a default second parameter
                                    fixed_call = f"{op_name}({params[0]}, 1)"
                                    fixed_template = fixed_template[:op_start] + fixed_call + fixed_template[op_end:]
                                    fixes.append(f"Increased {op_name} parameters from {param_count} to {expected} (added default)")
                                    logger.info(f"🔧 Fixed {op_name}: added default parameter")
                                    break
                            break
                    i += 1
        
        # If no specific fix found, try prompt engineering approach
        if not fixes and self.ollama_manager:
            logger.info("🔧 Trying prompt engineering for input count fix...")
            prompt = f"""Fix this FASTEXPR expression that has wrong number of operator parameters:

ERROR: {error_message}
EXPRESSION: {template}

The operator has the wrong number of inputs. Fix it by:
1. If it says "should be exactly 1 input(s)" but has 2, remove the extra parameter
2. If it says "should be exactly 2 input(s)" but has 1, add a default parameter (like 1 or 0)
3. Keep the operator name and first parameter, adjust others

Return ONLY the fixed expression, no explanations:"""
            
            try:
                response = self.ollama_manager.generate(prompt, max_tokens=300)
                if response:
                    fixed = self._extract_expression_from_response(response)
                    if fixed and fixed != template:
                        fixed_template = fixed
                        fixes.append("Prompt engineering fix for input count")
                        logger.info(f"🔧 Prompt engineering fixed input count: {fixed[:50]}...")
            except Exception as e:
                logger.debug(f"Prompt engineering for input count failed: {e}")
                # fixed_template already set to template at the beginning, so no need to set it again
        
        return fixed_template, fixes
    
    def get_validation_stats(self) -> Dict:
        """Get validation statistics"""
        if not self.use_ast or not self.corrector:
            return {
                'successful_templates': 0,
                'failed_templates': 0,
                'correction_rules': 0,
                'error_history': 0
            }
        return {
            'successful_templates': len(self.corrector.successful_templates),
            'failed_templates': len(self.corrector.failed_templates),
            'correction_rules': sum(len(rules) for rules in self.corrector.correction_rules.values()),
            'error_history': len(self.corrector.error_history)
        }
    
    def _fix_missing_lookback(self, template: str, error_message: str) -> Tuple[str, List[str]]:
        """Fix missing lookback parameter by adding default lookback value (e.g., 20)"""
        import re
        fixes = []
        fixed_template = template
        
        # Find operators that require lookback (ts_* operators typically need lookback)
        # Pattern: operator_name(field) -> operator_name(field, 20)
        lookback_operators = ['ts_rank', 'ts_sum', 'ts_mean', 'ts_max', 'ts_min', 'ts_std', 
                             'ts_delta', 'ts_correlation', 'ts_covariance', 'ts_decay', 
                             'ts_product', 'ts_argmax', 'ts_argmin', 'ts_scale', 'ts_winsorize',
                             'ts_zscore', 'ts_log', 'ts_reverse', 'ts_abs']
        
        for op in lookback_operators:
            # Pattern: operator(field) but not operator(field, ...)
            pattern = r'\b' + re.escape(op) + r'\s*\(\s*([^,)]+)\s*\)(?!\s*,\s*\d)'
            matches = list(re.finditer(pattern, fixed_template, re.IGNORECASE))
            if matches:
                # Replace from end to start to preserve positions
                for match in reversed(matches):
                    field_expr = match.group(1)
                    # Add lookback parameter: operator(field) -> operator(field, 20)
                    replacement = f"{op}({field_expr}, 20)"
                    fixed_template = fixed_template[:match.start()] + replacement + fixed_template[match.end():]
                    fixes.append(f"Added lookback parameter (20) to {op}")
                    logger.info(f"🔧 Added lookback to {op}: {op}({field_expr}) -> {op}({field_expr}, 20)")
        
        return fixed_template, fixes
    
    def _fix_missing_comma(self, template: str, error_message: str) -> Tuple[str, List[str]]:
        """Fix missing comma before parameters (e.g., ) 20 -> ), 20 or ))) 20 -> ))), 20)"""
        import re
        fixes = []
        fixed_template = template
        original_template = template
        
        # Pattern 1: One or more closing parentheses followed by whitespace and number -> add comma
        # Match: ) 20, )) 20, ))) 20, etc. -> ), 20, )), 20, ))), 20
        # But be careful: don't match if there's already a comma or if it's inside a nested expression
        pattern1 = r'(\)+)\s+(\d+)'
        matches = list(re.finditer(pattern1, fixed_template))
        if matches:
            # Replace from end to start to preserve positions
            for match in reversed(matches):
                parens = match.group(1)
                number = match.group(2)
                # Check if there's already a comma before this (look backwards)
                start_pos = match.start()
                # Check if this is actually a parameter (should be after a closing paren of an operator call)
                # Simple check: if there's a comma right before the parens, skip
                if start_pos > 0 and fixed_template[start_pos - 1] == ',':
                    continue
                # Replace: ))) 20 -> ))), 20
                replacement = parens + ', ' + number
                fixed_template = fixed_template[:match.start()] + replacement + fixed_template[match.end():]
            
            if fixed_template != original_template:
                fixes.append("Added missing comma before numeric parameter")
                logger.info(f"🔧 Fixed missing comma: ) number -> ), number (template: {original_template[:50]}... -> {fixed_template[:50]}...)")
        
        # Pattern 2: One or more closing parentheses followed by whitespace and identifier -> add comma
        pattern2 = r'(\)+)\s+([a-z][a-z0-9_]+)'
        matches = list(re.finditer(pattern2, fixed_template))
        if matches:
            for match in reversed(matches):
                parens = match.group(1)
                identifier = match.group(2)
                start_pos = match.start()
                # Check if there's already a comma before this
                if start_pos > 0 and fixed_template[start_pos - 1] == ',':
                    continue
                # Replace: ))) field -> ))), field
                replacement = parens + ', ' + identifier
                fixed_template = fixed_template[:match.start()] + replacement + fixed_template[match.end():]
            
            if fixed_template != original_template and "Added missing comma before identifier parameter" not in fixes:
                fixes.append("Added missing comma before identifier parameter")
                logger.info(f"🔧 Fixed missing comma: ) identifier -> ), identifier")
        
        return fixed_template, fixes
    
    def _fix_unknown_variable(self, template: str, error_message: str, region: str = None) -> Tuple[str, List[str]]:
        """Fix unknown variable by removing or replacing with valid field"""
        import re
        fixes = []
        fixed_template = template
        
        # Extract variable name from error message
        # Pattern: "Attempted to use unknown variable 'X'" or "unknown variable 'X'"
        var_match = re.search(r"unknown variable ['\"]?(\w+)['\"]?", error_message, re.IGNORECASE)
        if not var_match:
            var_match = re.search(r"attempted to use unknown variable ['\"]?(\w+)['\"]?", error_message, re.IGNORECASE)
        
        if var_match:
            unknown_var = var_match.group(1)
            logger.info(f"🔧 Found unknown variable: {unknown_var}")
            
            # Try to get valid fields for this region
            valid_fields = []
            if region:
                try:
                    from ..storage.backtest_storage import BacktestStorage
                    storage = BacktestStorage(self.db_path)
                    import sqlite3
                    conn = sqlite3.connect(storage.db_path)
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT DISTINCT field_id FROM data_fields 
                        WHERE region = ? AND field_id IS NOT NULL
                        LIMIT 10
                    ''', (region,))
                    valid_fields = [row[0] for row in cursor.fetchall() if row[0]]
                    conn.close()
                except Exception as e:
                    logger.debug(f"Could not get valid fields: {e}")
            
            # If we have valid fields, try to replace
            # Also check for case-insensitive match (e.g., DATA_FIELD1 vs data_field1)
            pattern = r'\b' + re.escape(unknown_var) + r'\b'
            case_insensitive_pattern = r'\b' + re.escape(unknown_var) + r'\b'
            
            # Try case-insensitive search first
            if re.search(pattern, fixed_template, re.IGNORECASE):
                if valid_fields:
                    # Replace with first valid field
                    replacement_field = valid_fields[0]
                    fixed_template = re.sub(pattern, replacement_field, fixed_template, flags=re.IGNORECASE)
                    fixes.append(f"Replaced unknown variable '{unknown_var}' with '{replacement_field}'")
                    logger.info(f"🔧 Replaced unknown variable '{unknown_var}' with '{replacement_field}'")
                else:
                    # No valid fields available - try to remove or let prompt engineering handle
                    # For DATA_FIELD1 or similar placeholders, try to find a common field pattern
                    if 'data_field' in unknown_var.lower() or 'field' in unknown_var.lower():
                        # This is likely a placeholder - let prompt engineering replace it
                        fixes.append(f"Detected placeholder variable '{unknown_var}' - prompt engineering will replace")
                        logger.warning(f"⚠️ Placeholder variable '{unknown_var}' detected - prompt engineering will handle replacement")
                    else:
                        # Try to remove the variable usage (risky, but better than leaving it)
                        fixes.append(f"Detected unknown variable '{unknown_var}' - needs manual fix")
                        logger.warning(f"⚠️ Unknown variable '{unknown_var}' detected - prompt engineering will handle replacement")
        
        return fixed_template, fixes
    
    def _fix_unknown_operator(self, template: str, error_message: str, region: str = None) -> Tuple[str, List[str]]:
        """Fix unknown/inaccessible operator by replacing with valid operator"""
        import re
        fixes = []
        fixed_template = template
        
        # Extract operator name from error message
        # Pattern: "Attempted to use inaccessible or unknown operator 'X'"
        op_match = re.search(r"unknown operator ['\"]?(\w+)['\"]?", error_message, re.IGNORECASE)
        if not op_match:
            op_match = re.search(r"inaccessible.*operator ['\"]?(\w+)['\"]?", error_message, re.IGNORECASE)
        if not op_match:
            op_match = re.search(r"attempted to use.*operator ['\"]?(\w+)['\"]?", error_message, re.IGNORECASE)
        
        if op_match:
            unknown_op = op_match.group(1)
            logger.info(f"🔧 Found unknown operator: {unknown_op}")
            
            # Try to get valid operators for this region
            valid_operators = []
            if self.use_ast and self.parser:
                valid_operators = list(self.parser.operators.keys())
            elif self.operators:
                valid_operators = [op.get('name', '') for op in self.operators if op.get('name')]
            
            # Try to find a similar operator (e.g., ts_* version)
            if unknown_op in fixed_template:
                # Try common replacements
                replacements = {
                    'reverse': 'ts_reverse',
                    'log': 'ts_log',
                    'abs': 'ts_abs',
                    'rank': 'ts_rank',
                    'sum': 'ts_sum',
                    'mean': 'ts_mean',
                    'max': 'ts_max',
                    'min': 'ts_min',
                    'std': 'ts_std',
                }
                
                replacement = replacements.get(unknown_op.lower())
                if replacement and replacement in valid_operators:
                    pattern = r'\b' + re.escape(unknown_op) + r'\s*\('
                    fixed_template = re.sub(pattern, replacement + '(', fixed_template, flags=re.IGNORECASE)
                    fixes.append(f"Replaced unknown operator '{unknown_op}' with '{replacement}'")
                    logger.info(f"🔧 Replaced unknown operator: {unknown_op} -> {replacement}")
                else:
                    # Remove the operator call or let prompt engineering handle it
                    fixes.append(f"Detected unknown operator '{unknown_op}' - needs manual fix")
                    logger.warning(f"⚠️ Unknown operator '{unknown_op}' detected - prompt engineering will handle replacement")
        
        return fixed_template, fixes