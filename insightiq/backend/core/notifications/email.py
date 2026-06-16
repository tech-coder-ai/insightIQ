from __future__ import annotations

import logging
from typing import Any

from core.events.bus import get_event_bus
from config.settings import get_settings_resolver

logger = logging.getLogger(__name__)


async def send_report_email(
    *,
    to: str,
    subject: str,
    body: str,
    attachment: bytes | None = None,
    filename: str | None = None,
) -> None:
    settings = get_settings_resolver().resolve()
    if not settings.email.enabled:
        return
    logger.info(
        "email report to=%s subject=%s attachment=%s bytes=%s",
        to,
        subject,
        filename,
        len(attachment) if attachment else 0,
    )
    bus = get_event_bus()
    await bus.publish(
        "email_report",
        {
            "to": to,
            "subject": subject,
            "filename": filename,
            "body_preview": body[:200],
        },
    )
