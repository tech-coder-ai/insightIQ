from __future__ import annotations

import re

from core.llm.base import ILLMProvider, LLMMessage
from core.llm.factory import LLM_PROVIDERS

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 1000

_STOPWORDS = {
    "show", "the", "a", "an", "as", "by", "for", "from", "in", "on", "to", "and", "or",
    "all", "top", "me", "my", "what", "how", "many", "each", "per", "over", "time",
    "which", "was", "were", "is", "are", "of", "with", "give", "get", "find", "list",
    "please", "can", "you", "tell", "want", "need", "row", "rows", "table", "data",
}
_SUPERLATIVE_DESC = {"most", "highest", "top", "best", "largest", "greatest", "max", "maximum", "biggest"}
_SUPERLATIVE_ASC = {"least", "lowest", "worst", "smallest", "min", "minimum"}
_NUMERIC_TYPE_HINTS = (
    "int", "numeric", "decimal", "float", "double", "real", "serial", "money", "bigint",
)
_METRIC_NAME_HINTS = (
    "count", "total", "amount", "sum", "qty", "quantity", "rentals", "revenue", "price",
    "rate", "score", "rating", "sales", "value",
)


@LLM_PROVIDERS.register("heuristic")
class HeuristicLLMProvider(ILLMProvider):
    """
    Dev-mode fallback used when no real LLM provider is configured (e.g. missing
    ``OPENAI_API_KEY``). It does best-effort keyword matching against the schema so
    the app remains usable offline, but it cannot reliably reason about joins or
    aggregations — callers should treat SQL from this provider as low-confidence
    and confirm/clarify with the user rather than executing it blindly.
    """

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> str:
        question = messages[-1].content.strip()
        question_lc = question.lower()
        tables = _extract_tables(system)
        limit = _extract_limit(question_lc) or _DEFAULT_LIMIT

        if not tables:
            return "SELECT 1 AS value LIMIT 1"

        tokens = _tokenize(question_lc)
        table_name, columns, _score = _best_matching_table(tokens, tables)

        if "count" in tokens or "how many" in question_lc:
            return f"SELECT COUNT(*) AS count FROM {table_name}"

        direction = None
        if tokens & _SUPERLATIVE_DESC:
            direction = "DESC"
        elif tokens & _SUPERLATIVE_ASC:
            direction = "ASC"

        if direction:
            order_col = _pick_metric_column(tokens, columns)
            if order_col:
                return f"SELECT * FROM {table_name} ORDER BY {order_col} {direction} LIMIT {limit}"

        return f"SELECT * FROM {table_name} LIMIT {limit}"


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower()) if len(tok) > 2}


_TABLE_BLOCK_RE = re.compile(
    r"-\s*table:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\n\s*columns:\s*([^\n]*)",
    re.IGNORECASE,
)
_COLUMN_RE = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)")


def _extract_tables(system: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Parse ``- table: name\\n  columns: col (type, hints), ...`` blocks from the system prompt."""
    tables: list[tuple[str, list[tuple[str, str]]]] = []
    for match in _TABLE_BLOCK_RE.finditer(system):
        name = match.group(1)
        cols = [(c.group(1), c.group(2)) for c in _COLUMN_RE.finditer(match.group(2))]
        tables.append((name, cols))
    if tables:
        return tables
    # Fallback for prompts that only mention bare table names (no column list).
    return [(name, []) for name in re.findall(r"table:\s*([a-zA-Z_][a-zA-Z0-9_]*)", system, flags=re.IGNORECASE)]


def _best_matching_table(
    tokens: set[str], tables: list[tuple[str, list[tuple[str, str]]]]
) -> tuple[str, list[tuple[str, str]], int]:
    """Score each table by token overlap with its name/columns; default to the first table."""
    best_name, best_columns = tables[0]
    best_score = -1
    for name, columns in tables:
        haystack = {name.lower()}
        haystack.update(c.lower() for c, _t in columns)
        score = 0
        for tok in tokens - _STOPWORDS:
            for h in haystack:
                if tok == h:
                    score += 3
                    break
                if tok in h or h in tok:
                    score += 1
                    break
        if score > best_score:
            best_score = score
            best_name, best_columns = name, columns
    return best_name, best_columns, best_score


def _pick_metric_column(tokens: set[str], columns: list[tuple[str, str]]) -> str | None:
    """Pick a numeric column to ORDER BY for superlative questions (most/least/top/highest)."""
    if not columns:
        return None
    numeric_cols = [c for c, t in columns if any(hint in t.lower() for hint in _NUMERIC_TYPE_HINTS)]
    if not numeric_cols:
        return None
    # Prefer a column whose name matches a question token or a common metric keyword.
    for col in numeric_cols:
        if col.lower() in tokens:
            return col
    for col in numeric_cols:
        if any(hint in col.lower() for hint in _METRIC_NAME_HINTS):
            return col
    return numeric_cols[0]


def _extract_limit(question: str) -> int | None:
    """Parse a row limit from phrases like 'top 10', 'first 5 rows', 'limit 20'."""
    patterns = (
        r"\btop\s+(\d+)\b",
        r"\bfirst\s+(\d+)\b",
        r"\blimit\s+(\d+)\b",
        r"\b(\d+)\s+rows?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            value = int(match.group(1))
            return min(max(value, 1), _MAX_LIMIT)
    return None
