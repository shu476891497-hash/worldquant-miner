"""
Tests for the WQ alpha expression parser.

Covers: simple expressions, nested function calls (5+ levels),
multi-statement with variable assignment, keyword arguments,
binary operations, comparisons, and edge cases.
"""

import pytest

from shadow_scorer.parser.ast_nodes import (
    Assignment,
    BinaryOp,
    ExpressionList,
    FunctionCall,
    Identifier,
    NumberLiteral,
    StringLiteral,
    UnaryOp,
)
from shadow_scorer.parser.lexer import LexerError, Token, TokenType, tokenize
from shadow_scorer.parser.parser import ParseError, parse_expression


# ====================================================================
# Lexer tests
# ====================================================================

class TestLexer:
    def test_simple_identifier(self):
        tokens = tokenize("close")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "close"
        assert tokens[1].type == TokenType.EOF

    def test_number_int(self):
        tokens = tokenize("42")
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "42"

    def test_number_float(self):
        tokens = tokenize("3.14")
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "3.14"

    def test_number_scientific(self):
        tokens = tokenize("1.5e-3")
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "1.5e-3"

    def test_string_double(self):
        tokens = tokenize('"gaussian"')
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "gaussian"

    def test_string_single(self):
        tokens = tokenize("'uniform'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "uniform"

    def test_operators(self):
        tokens = tokenize("+ - * / ^ > < >= <= == != & |")
        types = [t.type for t in tokens[:-1]]  # skip EOF
        expected = [
            TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.SLASH,
            TokenType.CARET, TokenType.GT, TokenType.LT, TokenType.GTE,
            TokenType.LTE, TokenType.EQ, TokenType.NEQ, TokenType.AMP,
            TokenType.PIPE,
        ]
        assert types == expected

    def test_delimiters(self):
        tokens = tokenize("(,;)")
        types = [t.type for t in tokens[:-1]]
        assert types == [TokenType.LPAREN, TokenType.COMMA, TokenType.SEMICOLON, TokenType.RPAREN]

    def test_assign_vs_eq(self):
        tokens = tokenize("x = 1")
        assert tokens[1].type == TokenType.ASSIGN
        tokens2 = tokenize("x == 1")
        assert tokens2[1].type == TokenType.EQ

    def test_complex_expression(self):
        tokens = tokenize("ts_mean(close, 5)")
        assert len(tokens) == 7  # ts_mean ( close , 5 ) EOF

    def test_unexpected_char_raises(self):
        with pytest.raises(LexerError):
            tokenize("close @ volume")


# ====================================================================
# Parser tests
# ====================================================================

class TestParser:
    # --- Simple expressions ---

    def test_simple_function(self):
        ast = parse_expression("rank(close)")
        assert isinstance(ast, FunctionCall)
        assert ast.name == "rank"
        assert len(ast.args) == 1
        assert isinstance(ast.args[0], Identifier)
        assert ast.args[0].name == "close"

    def test_number_literal(self):
        ast = parse_expression("42")
        assert isinstance(ast, NumberLiteral)
        assert ast.value == 42.0

    def test_string_literal(self):
        ast = parse_expression('"hello"')
        assert isinstance(ast, StringLiteral)
        assert ast.value == "hello"

    def test_identifier(self):
        ast = parse_expression("volume")
        assert isinstance(ast, Identifier)
        assert ast.name == "volume"

    # --- Binary operations ---

    def test_binary_add(self):
        ast = parse_expression("close + volume")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "+"
        assert isinstance(ast.left, Identifier)
        assert isinstance(ast.right, Identifier)

    def test_binary_div(self):
        ast = parse_expression("close / volume")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "/"

    def test_operator_precedence(self):
        """Multiplication binds tighter than addition."""
        ast = parse_expression("a + b * c")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "+"
        assert isinstance(ast.right, BinaryOp)
        assert ast.right.op == "*"

    def test_power_right_assoc(self):
        """Power is right-associative: 2^3^4 = 2^(3^4)."""
        ast = parse_expression("2 ^ 3 ^ 4")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "^"
        assert isinstance(ast.right, BinaryOp)
        assert ast.right.op == "^"

    # --- Comparison operators ---

    def test_comparison_gt(self):
        ast = parse_expression("ts_rank(x, 20) > 0.8")
        assert isinstance(ast, BinaryOp)
        assert ast.op == ">"
        assert isinstance(ast.left, FunctionCall)
        assert isinstance(ast.right, NumberLiteral)

    def test_comparison_eq(self):
        ast = parse_expression("a == b")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "=="

    def test_comparison_neq(self):
        ast = parse_expression("a != b")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "!="

    # --- Unary operators ---

    def test_unary_minus(self):
        ast = parse_expression("-close")
        assert isinstance(ast, UnaryOp)
        assert ast.op == "-"
        assert isinstance(ast.operand, Identifier)

    def test_unary_plus(self):
        ast = parse_expression("+42")
        assert isinstance(ast, NumberLiteral)
        assert ast.value == 42.0

    # --- Function calls ---

    def test_function_multiple_args(self):
        ast = parse_expression("ts_mean(close, 5)")
        assert isinstance(ast, FunctionCall)
        assert ast.name == "ts_mean"
        assert len(ast.args) == 2
        assert isinstance(ast.args[0], Identifier)
        assert isinstance(ast.args[1], NumberLiteral)

    def test_function_no_args(self):
        ast = parse_expression("ts_step(1)")
        assert isinstance(ast, FunctionCall)
        assert len(ast.args) == 1

    # --- Keyword arguments ---

    def test_kwargs(self):
        ast = parse_expression("winsorize(x, std=3)")
        assert isinstance(ast, FunctionCall)
        assert ast.name == "winsorize"
        assert len(ast.args) == 1
        assert len(ast.kwargs) == 1
        assert ast.kwargs[0][0] == "std"
        assert isinstance(ast.kwargs[0][1], NumberLiteral)
        assert ast.kwargs[0][1].value == 3.0

    def test_multiple_kwargs(self):
        ast = parse_expression("ts_regression(y, x, 20, lag=0, rettype=1)")
        assert isinstance(ast, FunctionCall)
        assert len(ast.args) == 3
        assert len(ast.kwargs) == 2

    # --- Nested function calls (5+ levels) ---

    def test_nested_5_levels(self):
        expr = "group_neutralize(ts_zscore(pasteurize(ts_delta(close, 5)), 60), subindustry)"
        ast = parse_expression(expr)
        assert isinstance(ast, FunctionCall)
        assert ast.name == "group_neutralize"
        # Level 1: group_neutralize(...)
        # Level 2: ts_zscore(...)
        inner = ast.args[0]
        assert isinstance(inner, FunctionCall)
        assert inner.name == "ts_zscore"
        # Level 3: pasteurize(...)
        inner2 = inner.args[0]
        assert isinstance(inner2, FunctionCall)
        assert inner2.name == "pasteurize"
        # Level 4: ts_delta(...)
        inner3 = inner2.args[0]
        assert isinstance(inner3, FunctionCall)
        assert inner3.name == "ts_delta"
        # Level 5: close (identifier)
        inner4 = inner3.args[0]
        assert isinstance(inner4, Identifier)
        assert inner4.name == "close"

    def test_deeply_nested(self):
        expr = "rank(normalize(ts_decay_linear(group_neutralize(ts_zscore(close, 20), sector), 10)))"
        ast = parse_expression(expr)
        assert isinstance(ast, FunctionCall)
        assert ast.name == "rank"

    # --- Multi-statement with assignment ---

    def test_assignment(self):
        ast = parse_expression("iv = ts_backfill(implied_volatility_call_30, 5); rank(iv)")
        assert isinstance(ast, ExpressionList)
        assert len(ast.expressions) == 2
        assert isinstance(ast.expressions[0], Assignment)
        assert ast.expressions[0].name == "iv"
        assert isinstance(ast.expressions[1], FunctionCall)
        assert ast.expressions[1].name == "rank"

    def test_multiple_assignments(self):
        ast = parse_expression("a = close; b = volume; a / b")
        assert isinstance(ast, ExpressionList)
        assert len(ast.expressions) == 3
        assert isinstance(ast.expressions[0], Assignment)
        assert isinstance(ast.expressions[1], Assignment)
        assert isinstance(ast.expressions[2], BinaryOp)

    def test_trailing_semicolon(self):
        """Trailing semicolons should be handled gracefully."""
        ast = parse_expression("rank(close);")
        assert isinstance(ast, FunctionCall)
        assert ast.name == "rank"

    # --- Parenthesised expressions ---

    def test_parentheses(self):
        ast = parse_expression("(a + b) * c")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "*"
        assert isinstance(ast.left, BinaryOp)
        assert ast.left.op == "+"

    # --- Logical operators ---

    def test_logical_and(self):
        ast = parse_expression("a & b")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "&"

    def test_logical_or(self):
        ast = parse_expression("a | b")
        assert isinstance(ast, BinaryOp)
        assert ast.op == "|"

    # --- Complex real-world expressions ---

    def test_real_world_alpha(self):
        expr = "group_neutralize(ts_rank(ts_decay_linear(ts_delta(close, 5), 20), 60), subindustry)"
        ast = parse_expression(expr)
        assert isinstance(ast, FunctionCall)
        assert ast.name == "group_neutralize"

    def test_expression_with_binary_inside_function(self):
        expr = "rank(close / ts_mean(close, 5))"
        ast = parse_expression(expr)
        assert isinstance(ast, FunctionCall)
        assert isinstance(ast.args[0], BinaryOp)

    # --- Error handling ---

    def test_unexpected_token_raises(self):
        with pytest.raises(ParseError):
            parse_expression("rank(,)")

    def test_unclosed_paren_raises(self):
        with pytest.raises(ParseError):
            parse_expression("rank(close")

    def test_empty_expression_raises(self):
        with pytest.raises(ParseError):
            parse_expression("")
