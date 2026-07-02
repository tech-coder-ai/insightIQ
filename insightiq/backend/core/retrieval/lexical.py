from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str | None) -> list[str]:
    """Shared lightweight tokenizer used by the BM25 sparse index, the lexical
    reranker, and context-compression scoring — keeps all of them consistent
    without pulling in a heavier NLP dependency."""
    return _TOKEN_RE.findall((text or "").lower())
