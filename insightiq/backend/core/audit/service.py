from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.events.bus import get_event_bus
from core.models import AuditEvent
from core.telemetry.logging import get_correlation_id

logger = logging.getLogger(__name__)


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=get_correlation_id(),
        metadata_json=metadata or {},
        ip_address=ip_address,
    )
    db.add(event)
    await db.flush()

    bus = get_event_bus()
    await bus.publish(
        "audit",
        {
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "user_id": str(user_id) if user_id else None,
            "correlation_id": get_correlation_id(),
        },
    )
    logger.info(
        json.dumps(
            {
                "event": "audit",
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "correlation_id": get_correlation_id(),
            }
        )
    )
    return event
