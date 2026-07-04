from __future__ import annotations

import re

# Drop non-content tags before MarkItDown — reduces noise from SPAs without
# removing the visible article body.
_STRIP_TAG_RE = re.compile(
    r"<(script|style|noscript|svg|iframe|nav|footer|header)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def sanitize_scraped_html(html: str) -> str:
    cleaned = _HTML_COMMENT_RE.sub("", html)
    cleaned = _STRIP_TAG_RE.sub("", cleaned)
    return cleaned
