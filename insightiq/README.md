## InsightIQ (v2 scaffold)

This repository is scaffolded from:
- `INSIGHTIQ V2 ENHANCEMENTS.md`
- `CURSOR BUILD PROMPT.md`

### Quick start (Phase 0)

Bring up infrastructure:

```bash
cd insightiq
docker compose up -d
```

Backend (local):

```bash
cd insightiq/backend
uv sync
uv run uvicorn gateway.main:app --reload --host 0.0.0.0 --port 8000
```

### Notes

- Phase 0 focuses on scaffolding and docker-compose health, not product features.
