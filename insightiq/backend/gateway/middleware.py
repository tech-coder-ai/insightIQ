from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from config.settings import get_settings_resolver
from core.events.bus import get_redis
from core.telemetry.logging import set_correlation_id

REQUEST_COUNT = Counter(
    "insightiq_http_requests_total",
    "HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "insightiq_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        set_correlation_id(cid)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings_resolver().resolve()
        if not settings.rate_limit.enabled or request.url.path in {"/healthz", "/metrics"}:
            return await call_next(request)

        client = await get_redis()
        if client is None:
            return await call_next(request)

        tenant_key = request.headers.get("authorization", "anon")[:32]
        key = f"ratelimit:{tenant_key}:{request.url.path}"
        limit = settings.rate_limit.requests_per_minute
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, 60)
            if count > limit:
                return Response(status_code=429, content='{"detail":"rate limit exceeded"}', media_type="application/json")
        except Exception:
            pass
        return await call_next(request)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        path = request.url.path
        REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
        return response
