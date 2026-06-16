from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

from config.settings import AppSettings, get_settings_resolver

logger = logging.getLogger(__name__)

_redis: Redis | None = None


async def get_redis() -> Redis | None:
    global _redis
    if _redis is not None:
        return _redis
    settings = get_settings_resolver().resolve()
    try:
        client: Redis = Redis.from_url(settings.redis.url, decode_responses=True)
        await client.ping()
        _redis = client
        return _redis
    except Exception:
        logger.warning("redis unavailable; event bus degraded to no-op")
        return None


class EventBus:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        client = await get_redis()
        if client is None:
            return
        body = {"type": event_type, **payload}
        try:
            await client.xadd(
                self._settings.redis.events_stream,
                {"data": json.dumps(body, default=str)},
                maxlen=10_000,
                approximate=True,
            )
        except Exception:
            logger.exception("failed to publish event %s", event_type)


def get_event_bus() -> EventBus:
    return EventBus(get_settings_resolver().resolve())
