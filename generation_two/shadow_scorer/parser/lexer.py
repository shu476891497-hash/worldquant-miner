"""
Tokenizer for WQ alpha expressions.

Handles: numbers (int, float, scientific notation), string literals,
identifiers (field names & operator names), arithmetic/comparison/logical
operators, delimiters, and keyword arguments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List


class TokenType(Enum):
    # Literals
    NUMBER = auto()
    STRING = auto()
    IDENTIFIER = auto()

    # Arithmetic operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    CARET = auto()

    # Comparison operators
    GT = auto()
    LT = auto()
    GTE = auto()
    LTE = auto()
    EQ = auto()       # ==
    NEQ = auto()       # !=

    # Logical operators
    AMP = auto()       # &
    PIPE = auto()      # |

    # Delimiters
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    SEMICOLON = auto()

    # Assignment
    ASSIGN = auto()    # = (single, not ==)

    # Special
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    pos: int  # position in original string

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, pos={self.pos})"


# --- Token patterns (order matters) ---
_TOKEN_SPEC: List[tuple] = [
    # Whitespace (skip)
    ("SKIP", r"[ \t\r\n]+"),
    # Numbers: scientific notation, floats, ints
    ("NUMBER", r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"),
    # String literals (single or double quoted)
    ("STRING", r'"[^"]*"|\'[^\']*\''),
    # Two-char operators (must come before single-char)
    ("GTE", r">="),
    ("LTE", r"<="),
    ("EQ", r"=="),
    ("NEQ", r"!="),
    # Single-char operators & delimiters
    ("GT", r">"),
    ("LT", r"<"),
    ("PLUS", r"\+"),
    ("MINUS", r"-"),
    ("STAR", r"\*"),
    ("SLASH", r"/"),
    ("CARET", r"\^"),
    ("AMP", r"&"),
    ("PIPE", r"\|"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("COMMA", r","),
    ("SEMICOLON", r";"),
    ("ASSIGN", r"="),
    # Identifiers (letters, digits, underscores — must start with letter or _)
    ("IDENTIFIER", r"[A-Za-z_][A-Za-z0-9_]*"),
]

_TOKEN_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC)
)

_SIMPLE_MAP = {
    "PLUS": TokenType.PLUS,
    "MINUS": TokenType.MINUS,
    "STAR": TokenType.STAR,
    "SLASH": TokenType.SLASH,
    "CARET": TokenType.CARET,
    "GT": TokenType.GT,
    "LT": TokenType.LT,
    "GTE": TokenType.GTE,
    "LTE": TokenType.LTE,
    "EQ": TokenType.EQ,
    "NEQ": TokenType.NEQ,
    "AMP": TokenType.AMP,
    "PIPE": TokenType.PIPE,
    "LPAREN": TokenType.LPAREN,
    "RPAREN": TokenType.RPAREN,
    "COMMA": TokenType.COMMA,
    "SEMICOLON": TokenType.SEMICOLON,
    "ASSIGN": TokenType.ASSIGN,
}


class LexerError(Exception):
    """Raised on unexpected characters during tokenization."""

    def __init__(self, char: str, pos: int):
        self.char = char
        self.pos = pos
        super().__init__(f"Unexpected character {char!r} at position {pos}")


def tokenize(expression: str) -> List[Token]:
    """Tokenize a WQ alpha expression string into a list of Tokens.

    Parameters
    ----------
    expression : str
        The raw alpha expression.

    Returns
    -------
    list[Token]
        Ordered list of tokens, ending with an EOF token.

    Raises
    ------
    LexerError
        If an unrecognised character is encountered.
    """
    tokens: List[Token] = []
    pos = 0

    for m in _TOKEN_RE.finditer(expression):
        start = m.start()
        # Check for unmatched characters between last pos and this match
        if start > pos:
            bad = expression[pos:start].strip()
            if bad:
                raise LexerError(bad[0], pos)
        pos = m.end()

        kind = m.lastgroup
        value = m.group()

        if kind == "SKIP":
            continue
        elif kind == "NUMBER":
            tokens.append(Token(TokenType.NUMBER, value, start))
        elif kind == "STRING":
            # Strip surrounding quotes
            tokens.append(Token(TokenType.STRING, value[1:-1], start))
        elif kind == "IDENTIFIER":
            tokens.append(Token(TokenType.IDENTIFIER, value, start))
        elif kind in _SIMPLE_MAP:
            tokens.append(Token(_SIMPLE_MAP[kind], value, start))
        else:
            raise LexerError(value[0], start)  # pragma: no cover

    # Check trailing
    if pos < len(expression):
        remainder = expression[pos:].strip()
        if remainder:
            raise LexerError(remainder[0], pos)

    tokens.append(Token(TokenType.EOF, "", len(expression)))
    return tokens
