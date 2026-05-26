"""
Recursive-descent parser for WQ alpha expressions.

Grammar (informal, highest precedence at bottom):
    program        → statement (';' statement)* ';'?
    statement      → assignment | expression
    assignment     → IDENTIFIER '=' expression
    expression     → or_expr
    or_expr        → and_expr ('|' and_expr)*
    and_expr       → comparison ('&' comparison)*
    comparison     → addition (('>' | '<' | '>=' | '<=' | '==' | '!=') addition)*
    addition       → multiplication (('+' | '-') multiplication)*
    multiplication → power (('*' | '/') power)*
    power          → unary ('^' unary)*
    unary          → ('-' | '+') unary | postfix
    postfix        → primary ( '(' arglist ')' )?
    primary        → NUMBER | STRING | '(' expression ')' | IDENTIFIER
    arglist        → (arg (',' arg)*)?
    arg            → IDENTIFIER '=' expression  |  expression
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .ast_nodes import (
    ASTNode,
    Assignment,
    BinaryOp,
    ExpressionList,
    FunctionCall,
    Identifier,
    NumberLiteral,
    StringLiteral,
    UnaryOp,
)
from .lexer import Token, TokenType, tokenize


class ParseError(Exception):
    """Raised when the token stream doesn't match the grammar."""

    def __init__(self, message: str, token: Optional[Token] = None):
        self.token = token
        loc = f" at position {token.pos}" if token else ""
        super().__init__(f"{message}{loc}")


class _Parser:
    """Internal recursive-descent parser state."""

    def __init__(self, tokens: List[Token]):
        self._tokens = tokens
        self._pos = 0

    # ----- helpers -----

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, tt: TokenType) -> Token:
        tok = self._peek()
        if tok.type != tt:
            raise ParseError(f"Expected {tt.name}, got {tok.type.name} ({tok.value!r})", tok)
        return self._advance()

    def _match(self, *types: TokenType) -> Optional[Token]:
        if self._peek().type in types:
            return self._advance()
        return None

    # ----- grammar rules -----

    def parse_program(self) -> ASTNode:
        stmts: list[ASTNode] = []
        stmts.append(self._parse_statement())

        while self._match(TokenType.SEMICOLON):
            # Allow trailing semicolons
            if self._peek().type == TokenType.EOF:
                break
            stmts.append(self._parse_statement())

        self._expect(TokenType.EOF)

        if len(stmts) == 1:
            return stmts[0]
        return ExpressionList(tuple(stmts))

    def _parse_statement(self) -> ASTNode:
        # Look-ahead for assignment:  IDENTIFIER '=' expr
        # But NOT  IDENTIFIER '==' expr  (that's comparison).
        if (
            self._peek().type == TokenType.IDENTIFIER
            and self._pos + 1 < len(self._tokens)
            and self._tokens[self._pos + 1].type == TokenType.ASSIGN
        ):
            name_tok = self._advance()
            self._advance()  # consume '='
            value = self._parse_expression()
            return Assignment(name_tok.value, value)
        return self._parse_expression()

    def _parse_expression(self) -> ASTNode:
        return self._parse_or()

    def _parse_or(self) -> ASTNode:
        left = self._parse_and()
        while self._match(TokenType.PIPE):
            right = self._parse_and()
            left = BinaryOp("|", left, right)
        return left

    def _parse_and(self) -> ASTNode:
        left = self._parse_comparison()
        while self._match(TokenType.AMP):
            right = self._parse_comparison()
            left = BinaryOp("&", left, right)
        return left

    def _parse_comparison(self) -> ASTNode:
        left = self._parse_addition()
        _cmp_ops = {
            TokenType.GT: ">",
            TokenType.LT: "<",
            TokenType.GTE: ">=",
            TokenType.LTE: "<=",
            TokenType.EQ: "==",
            TokenType.NEQ: "!=",
        }
        while self._peek().type in _cmp_ops:
            op_tok = self._advance()
            right = self._parse_addition()
            left = BinaryOp(_cmp_ops[op_tok.type], left, right)
        return left

    def _parse_addition(self) -> ASTNode:
        left = self._parse_multiplication()
        while self._peek().type in (TokenType.PLUS, TokenType.MINUS):
            op_tok = self._advance()
            right = self._parse_multiplication()
            left = BinaryOp(op_tok.value, left, right)
        return left

    def _parse_multiplication(self) -> ASTNode:
        left = self._parse_power()
        while self._peek().type in (TokenType.STAR, TokenType.SLASH):
            op_tok = self._advance()
            right = self._parse_power()
            left = BinaryOp(op_tok.value, left, right)
        return left

    def _parse_power(self) -> ASTNode:
        base = self._parse_unary()
        if self._match(TokenType.CARET):
            # Right-associative
            exp = self._parse_power()
            return BinaryOp("^", base, exp)
        return base

    def _parse_unary(self) -> ASTNode:
        if self._peek().type == TokenType.MINUS:
            op = self._advance()
            operand = self._parse_unary()
            return UnaryOp("-", operand)
        if self._peek().type == TokenType.PLUS:
            self._advance()
            return self._parse_unary()
        return self._parse_postfix()

    def _parse_postfix(self) -> ASTNode:
        node = self._parse_primary()

        # If the primary was an Identifier and the next token is '(',
        # treat it as a function call.
        if isinstance(node, Identifier) and self._peek().type == TokenType.LPAREN:
            self._advance()  # consume '('
            args, kwargs = self._parse_arglist()
            self._expect(TokenType.RPAREN)
            node = FunctionCall(node.name, tuple(args), tuple(kwargs))
        return node

    def _parse_arglist(self) -> Tuple[List[ASTNode], List[Tuple[str, ASTNode]]]:
        args: List[ASTNode] = []
        kwargs: List[Tuple[str, ASTNode]] = []

        if self._peek().type == TokenType.RPAREN:
            return args, kwargs

        self._parse_arg(args, kwargs)
        while self._match(TokenType.COMMA):
            self._parse_arg(args, kwargs)

        return args, kwargs

    def _parse_arg(
        self,
        args: List[ASTNode],
        kwargs: List[Tuple[str, ASTNode]],
    ) -> None:
        # Look-ahead:  IDENTIFIER '=' (not '==')
        if (
            self._peek().type == TokenType.IDENTIFIER
            and self._pos + 1 < len(self._tokens)
            and self._tokens[self._pos + 1].type == TokenType.ASSIGN
        ):
            name_tok = self._advance()
            self._advance()  # consume '='
            value = self._parse_expression()
            kwargs.append((name_tok.value, value))
        else:
            args.append(self._parse_expression())

    def _parse_primary(self) -> ASTNode:
        tok = self._peek()

        if tok.type == TokenType.NUMBER:
            self._advance()
            return NumberLiteral(float(tok.value))

        if tok.type == TokenType.STRING:
            self._advance()
            return StringLiteral(tok.value)

        if tok.type == TokenType.IDENTIFIER:
            self._advance()
            return Identifier(tok.value)

        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN)
            return expr

        raise ParseError(f"Unexpected token {tok.type.name} ({tok.value!r})", tok)


def parse_expression(expression: str) -> ASTNode:
    """Parse a WQ alpha expression string into an AST.

    Parameters
    ----------
    expression : str
        Raw alpha expression, e.g. ``"rank(close / ts_mean(close, 5))"``

    Returns
    -------
    ASTNode
        The root of the parsed AST.

    Raises
    ------
    ParseError
        If the expression is syntactically invalid.
    """
    tokens = tokenize(expression)
    parser = _Parser(tokens)
    return parser.parse_program()
