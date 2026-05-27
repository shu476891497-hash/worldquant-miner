"""
Submission dedup - avoid resubmitting identical or near-identical alpha expressions.
Uses normalized expression hashing to track last N submissions.
"""
import hashlib
import re
from collections import OrderedDict


class SubmissionDedup:
    """Track submitted expressions to avoid resubmitting near-identical variants.
    
    Normalizes expressions (strip whitespace, round floats) then hashes.
    Maintains a rolling window of the last `max_size` submissions.
    """

    def __init__(self, max_size=2000):
        self._seen = OrderedDict()  # hash -> original expr
        self._max_size = max_size
        self._dedup_count = 0  # how many duplicates we've caught

    @staticmethod
    def _normalize(expr):
        """Normalize expression for dedup comparison."""
        s = expr.strip()
        s = re.sub(r'\s+', ' ', s)
        # Round float coefficients to 1 decimal place
        s = re.sub(r'\b(\d+)\.(\d)\d*\b', r'\1.\2', s)
        return s

    def _hash(self, expr):
        """Get 16-char hash of normalized expression."""
        return hashlib.md5(self._normalize(expr).encode()).hexdigest()[:16]

    def is_duplicate(self, expr):
        """Check if this expression was already submitted."""
        h = self._hash(expr)
        if h in self._seen:
            self._dedup_count += 1
            return True
        return False

    def record(self, expr):
        """Record a submitted expression."""
        h = self._hash(expr)
        self._seen[h] = expr
        while len(self._seen) > self._max_size:
            self._seen.popitem(last=False)

    def record_batch(self, exprs):
        """Record multiple expressions at once."""
        for expr in exprs:
            self.record(expr)

    def stats(self):
        """Return dedup statistics string."""
        return f"Dedup: {len(self._seen)}/{self._max_size} tracked, {self._dedup_count} duplicates caught"


# Global singleton
_global_dedup = SubmissionDedup(max_size=2000)


def is_duplicate(expr):
    """Check if expression is a duplicate (module-level convenience function)."""
    return _global_dedup.is_duplicate(expr)


def record_submission(expr):
    """Record a submitted expression (module-level convenience function)."""
    _global_dedup.record(expr)


def record_batch(exprs):
    """Record multiple submitted expressions."""
    _global_dedup.record_batch(exprs)


def dedup_stats():
    """Get dedup statistics."""
    return _global_dedup.stats()
