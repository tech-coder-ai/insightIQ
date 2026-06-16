from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

import httpx


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                self.links.append(value)


def _same_site(a: str, b: str) -> bool:
    return urlparse(a).netloc == urlparse(b).netloc


def _extract_links(base_url: str, html: str) -> list[str]:
    parser = _LinkExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - malformed HTML should not abort the crawl
        return []
    out: list[str] = []
    for href in parser.links:
        absolute, _ = urldefrag(urljoin(base_url, href))
        scheme = urlparse(absolute).scheme
        if scheme in {"http", "https"}:
            out.append(absolute)
    return out


async def crawl(
    start_url: str,
    *,
    depth: int = 0,
    max_pages: int = 20,
    timeout: float = 15.0,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[tuple[str, str]]:
    """Breadth-first, same-site crawl.

    Returns a list of ``(url, html)`` pairs. ``depth`` is the number of link
    hops beyond the start page (0 = only the start page). The crawl never leaves
    the start URL's host and never fetches more than ``max_pages`` pages.
    """
    depth = max(0, min(depth, 5))
    max_pages = max(1, min(max_pages, 100))

    visited: set[str] = set()
    pages: list[tuple[str, str]] = []
    queue: deque[tuple[str, int]] = deque([(urldefrag(start_url)[0], 0)])

    headers = {"User-Agent": "InsightIQ-Crawler/1.0 (+https://insightiq.local)"}
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout, headers=headers
    ) as client:
        while queue and len(pages) < max_pages:
            url, level = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            try:
                resp = await client.get(url)
            except httpx.HTTPError:
                continue
            content_type = resp.headers.get("content-type", "")
            if resp.status_code != 200 or "html" not in content_type.lower():
                continue

            html = resp.text
            pages.append((url, html))
            if on_progress is not None:
                await on_progress(len(pages), max_pages)

            if level < depth:
                for link in _extract_links(url, html):
                    if link not in visited and _same_site(start_url, link):
                        queue.append((link, level + 1))

    return pages
