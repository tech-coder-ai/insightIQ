from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from config.settings import get_settings_resolver
from core.dashboard.factory import CardRefresherFactory
from core.deps import get_app_sessionmaker
from core.export.base import ExportPayload
from core.export.factory import ExporterFactory
from core.models import Dashboard, DashboardCard, ScheduledReport
from core.notifications.email import send_report_email

logger = logging.getLogger(__name__)

_task: asyncio.Task[None] | None = None


def _card_summary(card: DashboardCard) -> str:
    snap = card.snapshot_response_json or {}
    data = snap.get("data", {})
    if isinstance(data, dict):
        if "output" in data:
            return str(data["output"])[:500]
        if "value" in data:
            return str(data["value"])
    return str(snap.get("response_type", card.card_type))


async def build_dashboard_export_payload(
    db: Any, *, dashboard: Dashboard, tenant_id: uuid.UUID
) -> ExportPayload:
    cards_res = await db.execute(select(DashboardCard).where(DashboardCard.dashboard_id == dashboard.id))
    cards = cards_res.scalars().all()
    refreshed: list[dict[str, str]] = []
    for card in cards:
        snapshot = dict(card.snapshot_response_json or {})
        if card.refresh_mode == "live":
            try:
                refresher = CardRefresherFactory.create(card.source_type)
                result = await refresher.refresh(
                    source_config=card.source_config_json, tenant_id=str(tenant_id)
                )
                snapshot = result.response
                card.snapshot_response_json = snapshot
            except Exception:
                logger.exception("failed to refresh card %s", card.id)
        refreshed.append({"title": card.title, "summary": _card_summary(card)})
    await db.flush()
    return ExportPayload(
        title=dashboard.name,
        content_type="dashboard",
        data={"cards": refreshed},
    )


async def run_scheduled_report(report_id: uuid.UUID) -> None:
    sessionmaker = get_app_sessionmaker()
    async with sessionmaker() as db:
        report = await db.get(ScheduledReport, report_id)
        if report is None or not report.enabled:
            return
        dash = await db.get(Dashboard, report.dashboard_id)
        if dash is None:
            return
        payload = await build_dashboard_export_payload(db, dashboard=dash, tenant_id=report.tenant_id)
        exporter = ExporterFactory.create(report.export_format)
        result = await exporter.export(payload=payload)
        await send_report_email(
            to=report.recipient_email,
            subject=f"InsightIQ report: {dash.name}",
            body=f"Attached: {result.filename}",
            attachment=result.data,
            filename=result.filename,
        )
        now = datetime.now(UTC)
        report.last_run_at = now
        report.next_run_at = now + timedelta(seconds=report.interval_seconds)
        await db.commit()


async def _scheduler_loop() -> None:
    settings = get_settings_resolver().resolve()
    sessionmaker = get_app_sessionmaker()
    while True:
        try:
            now = datetime.now(UTC)
            async with sessionmaker() as db:
                res = await db.execute(
                    select(ScheduledReport).where(
                        ScheduledReport.enabled.is_(True),
                        ScheduledReport.next_run_at <= now,
                    )
                )
                due = res.scalars().all()
            for report in due:
                await run_scheduled_report(report.id)
        except Exception:
            logger.exception("scheduler tick failed")
        await asyncio.sleep(settings.scheduler.poll_interval_seconds)


def start_report_scheduler() -> None:
    global _task
    settings = get_settings_resolver().resolve()
    if not settings.scheduler.enabled or _task is not None:
        return
    _task = asyncio.create_task(_scheduler_loop())
    logger.info("report scheduler started")


def stop_report_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
