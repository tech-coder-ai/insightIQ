# InsightIQ v2 — Phase 7 Notes

## What was built

### IExporter plugin registry
- **`core/export/base.py`**: `IExporter`, `ExportPayload`, `EXPORTERS` registry
- **`ExporterFactory`**: auto-imports exporter modules by convention
- **Exporters** (each a single file + `@EXPORTERS.register`):
  - `markdown` — conversation + dashboard text export
  - `pdf` — ReportLab PDF
  - `pptx` — python-pptx slide deck

Adding a new format = one new file under `core/export/exporters/` + factory import line.

### Export API
| Endpoint | Purpose |
|---|---|
| `GET /export/formats` | List registered exporters |
| `GET /export/conversations/{id}?format=` | Download conversation (markdown/pdf/pptx) |
| `GET /export/dashboards/{id}?format=` | Download dashboard (pdf/pptx/markdown) |

### Scheduled reports
- **`ScheduledReport` model** + migration `0008_extensions`
- **Background scheduler** (`core/jobs/report_scheduler.py`) — refreshes live cards, exports PDF/PPT, emails recipient
- **Dev email notifier** logs + publishes `email_report` event to Redis
- **API**: `POST/GET/DELETE /reports/schedules`, `POST .../run-now`

### Frontend
- **Chat sidebar**: Export MD / PDF for active conversation
- **Dashboard canvas**: Export PDF/PPT, schedule hourly email report

## Run

```bash
cd insightiq/backend
uv sync
uv run alembic upgrade head   # 0008_extensions
```

## Assumptions
- Email delivery is dev-stub (logs + event bus); wire SMTP/SES in production
- Scheduler runs in-process via asyncio (Celery worker optional later)
- PPT export for conversations maps each message to a slide

## Plugin model proof
A new exporter requires only:
1. `core/export/exporters/myformat.py` with `@EXPORTERS.register("myformat")`
2. One line in `ExporterFactory` module list (convention bootstrap)

No changes to export API or dashboard/chat services.
