# InsightIQ v2

Modular, multi-tenant AI intelligence platform: **Talk to Data**, **Talk to Documents**, **Prompt Studio**, **Chat History**, and **Dashboard Manager** — built on a plugin-first extensibility core.

## Features

| Product | Description |
|---|---|
| **Talk to Data** | NL→SQL against Postgres, S3/MinIO (DuckDB), and ad-hoc files; schema introspection, glossary, chart/KPI responses |
| **Talk to Documents** | 10-stage LangGraph RAG with citation highlights; profiles: naive, advanced, graph, agentic |
| **Prompt Studio** | Jinja2 templates, version history, LLM-as-judge eval, pin outputs to dashboards |
| **Dashboard Manager** | Gridster canvas, live card refresh, team access, public share links, scheduled email reports |
| **Extensibility** | Typed registries for connectors, LLMs, embedders, RAG nodes, card refreshers, exporters |

## Architecture

```
insightiq/
├── backend/          # FastAPI gateway + core kernel + services
├── frontend/         # Angular 18 standalone app
├── openapi/          # OpenAPI 3.1 contract
├── ops/              # Prometheus + Grafana provisioning
└── docker-compose.yml
```

**Stack:** Python 3.12 · FastAPI · SQLAlchemy (async) · LangGraph · Qdrant · Redis · PostgreSQL · Angular 18

## Quick start

**Prerequisites:** Docker, [uv](https://docs.astral.sh/uv/), Node.js 20+

```bash
cd insightiq
docker compose up -d

cd backend
uv sync
eval "$(python scripts/generate_dev_keys.py)"
uv run alembic upgrade head
uv run uvicorn gateway.main:app --reload --port 8000

# new terminal
cd frontend
npm install
npm start
```

Open http://localhost:4200 · API http://localhost:8000 · Docs http://localhost:8000/docs

### Sample PostgreSQL database (Pagila)

A realistic **Pagila DVD rental** dataset (~16k rentals, 2k films, customers, payments) is available for Talk to Data demos.

**First-time Docker setup** — Pagila loads automatically when Postgres initializes (fresh volume).

**Existing Postgres volume** — run once:

```bash
cd insightiq
chmod +x scripts/load_pagila_sample_db.sh
./scripts/load_pagila_sample_db.sh
```

Connection: `localhost:5432` · database **`pagila`** · user **`insightiq`** · password **`insightiq`**

In the UI: **Datasources → PostgreSQL → Use Pagila sample**, then continue to register.

1. Register at `/login`
2. Register a Postgres datasource under **Talk to Data**
3. Upload documents under **Talk to Documents**
4. Build prompts in **Prompt Studio**
5. Pin responses to **Dashboards**

## Observability (local)

| Service | URL |
|---|---|
| Jaeger | http://localhost:16686 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |
| MinIO console | http://localhost:9001 (minio/minio123456) |

## Documentation

- **[New machine setup guide](insightiq/SETUP.md)** — prerequisites, Docker, Postgres/Redis without Docker, env vars, troubleshooting
- [Deployment guide](insightiq/DEPLOYMENT.md) — production setup, env vars, secrets
- [Build spec](CURSOR%20BUILD%20PROMPT.md) — phased plan and engineering rules
- [Enhancements spec](INSIGHTIQ%20V2%20ENHANCEMENTS.md) — RAG and platform design
- Phase notes: `insightiq/PHASE_0_NOTES.md` … `insightiq/PHASE_7_NOTES.md`

## Development

```bash
# Backend
cd insightiq/backend
uv run ruff check .
uv run pytest tests/ -q
uv run mypy gateway core services   # optional strict check

# Frontend
cd insightiq/frontend
npm run build
```

## Plugin model

New capabilities are added as **config + a new file** — no edits to existing plugins:

```python
# core/export/exporters/myformat.py
from core.export.base import EXPORTERS, IExporter

@EXPORTERS.register("myformat")
class MyFormatExporter(IExporter):
    async def export(self, *, payload): ...
```

Same pattern for DB connectors, LLM providers, RAG nodes, card refreshers, and exporters.

## License

MIT / Apache-2.0 dependencies only. See `backend/pyproject.toml` for pinned packages.
