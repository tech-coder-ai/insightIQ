## Phase 0 — Scaffold (completed)

### What was added
- **Monorepo skeleton** under `insightiq/` matching `CURSOR BUILD PROMPT.md`.
- **docker-compose** bringing up core dependencies: Postgres, Redis, Qdrant, Neo4j, MinIO, Vault (dev), Jaeger, Prometheus, Grafana, Loki.
- **Backend bootstrap** (Python 3.12) with `uv`-style `pyproject.toml`, FastAPI gateway `GET /healthz`.
- **Core typed plugin registry** (`backend/core/registry.py`) as the foundation for all registries.
- **OpenAPI skeleton** at `openapi/insightiq.yaml`.

### Assumptions
- Vault is started in **dev mode** for Phase 0; production hardening comes later.
- Observability config is minimal in Phase 0 (health/bring-up focus).

### TODO(phase1)
- Add auth + tenants/RBAC, and wire OTEL tracing into the gateway.
- Add database migrations, metadata models, and `SettingsResolver`.
