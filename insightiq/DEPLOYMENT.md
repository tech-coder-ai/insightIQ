# InsightIQ v2 — Deployment Guide

## Overview

InsightIQ runs as:

1. **Gateway** — single FastAPI process (`gateway.main:app`) serving all APIs
2. **Angular SPA** — static files behind nginx/CDN or `ng serve` in dev
3. **Infrastructure** — Postgres (metadata), Redis (cache/rate-limit/events), Qdrant (vectors), MinIO (object storage)

Optional: Neo4j (graph RAG), Jaeger/Prometheus/Grafana (observability), Vault (secrets).

---

## Local development

```bash
cd insightiq
docker compose up -d

cd backend
uv sync
eval "$(python scripts/generate_dev_keys.py)"
uv run alembic upgrade head
uv run uvicorn gateway.main:app --reload --host 0.0.0.0 --port 8000

cd ../frontend
npm install && npm start
```

Verify: `curl http://localhost:8000/healthz` → `{"status":"ok"}`

---

## Environment variables

All settings use prefix `INSIGHTIQ_` with nested `__` delimiter.

| Variable | Default | Description |
|---|---|---|
| `INSIGHTIQ_ENV` | `dev` | Environment name |
| `INSIGHTIQ_DATABASE__URL` | `postgresql+asyncpg://insightiq:insightiq@localhost:5432/insightiq` | Async Postgres URL |
| `INSIGHTIQ_JWT__PRIVATE_KEY_PEM` | *(required)* | RS256 private key PEM |
| `INSIGHTIQ_JWT__PUBLIC_KEY_PEM` | *(required)* | RS256 public key PEM |
| `INSIGHTIQ_JWT__ISSUER` | `insightiq` | JWT issuer |
| `INSIGHTIQ_JWT__AUDIENCE` | `insightiq` | JWT audience |
| `INSIGHTIQ_REDIS__URL` | `redis://localhost:6379/0` | Redis for rate limit + event bus |
| `INSIGHTIQ_QDRANT__URL` | `http://localhost:6333` | Qdrant vector store |
| `INSIGHTIQ_STORAGE__UPLOAD_DIR` | `uploads` | Document upload directory |
| `INSIGHTIQ_TELEMETRY__ENABLED` | `true` | OpenTelemetry export |
| `INSIGHTIQ_TELEMETRY__OTLP_ENDPOINT` | `http://localhost:4317` | Jaeger OTLP gRPC |
| `INSIGHTIQ_TELEMETRY__LOG_JSON` | `true` | Structured JSON logs |
| `INSIGHTIQ_RATE_LIMIT__ENABLED` | `true` | Per-tenant rate limiting |
| `INSIGHTIQ_RATE_LIMIT__REQUESTS_PER_MINUTE` | `120` | Rate limit threshold |
| `INSIGHTIQ_SCHEDULER__ENABLED` | `true` | Dashboard email scheduler |
| `INSIGHTIQ_EMAIL__ENABLED` | `true` | Email notifier (dev: logs only) |

Generate dev JWT keys:

```bash
cd insightiq/backend
python scripts/generate_dev_keys.py
```

---

## Database migrations

```bash
cd insightiq/backend
uv run alembic upgrade head
```

Migration chain: `0001_init` → … → `0008_extensions`

---

## Docker Compose stack

`docker compose up -d` starts:

| Service | Port | Purpose |
|---|---|---|
| postgres | 5432 | Metadata DB |
| redis | 6379 | Cache, rate limit, events |
| qdrant | 6333 | Vector search |
| minio | 9000/9001 | S3-compatible storage |
| neo4j | 7474/7687 | Graph RAG (optional) |
| vault | 8200 | Secrets (dev mode) |
| jaeger | 16686 | Trace UI |
| prometheus | 9090 | Metrics |
| grafana | 3000 | Dashboards |

**Production:** do not use Vault dev mode or default MinIO credentials.

---

## Production deployment

### Recommended topology

```
                    ┌─────────────┐
   Users ──────────►│ CDN / nginx │──► Angular static
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Gateway    │  (uvicorn × N behind load balancer)
                    │  :8000      │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
      PostgreSQL        Redis           Qdrant
      (managed)       (managed)       (managed)
```

### Gateway process

```bash
cd insightiq/backend
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --workers 4
```

For production, prefer a process manager (systemd, Kubernetes Deployment) with health checks on `/healthz`.

### Frontend build

```bash
cd insightiq/frontend
npm ci   # or npm install
npm run build
# Serve dist/ via nginx with fallback to index.html for Angular routes
```

Update `API_BASE` in `frontend/src/app/core/api.config.ts` (or use build-time environment replacement) to point at your gateway URL.

### Secrets

| Secret | Storage |
|---|---|
| JWT RS256 key pair | Vault / KMS / K8s Secret |
| Datasource passwords | Vault (Phase 6+ hardening path) |
| MinIO/S3 keys | Vault or cloud IAM |

Never commit `.pem` files or `.env` with production values.

### CORS

Edit `gateway/main.py` `allow_origins` for your frontend domain, or inject via settings in a future config pass.

### Observability

1. Set `INSIGHTIQ_TELEMETRY__OTLP_ENDPOINT` to your collector (Jaeger, Grafana Alloy, Datadog agent)
2. Scrape `/metrics` with Prometheus (see `ops/prometheus/prometheus.yml`)
3. Import Grafana dashboard from `ops/grafana/provisioning/dashboards/insightiq-gateway.json`

### Scheduled reports

The in-process asyncio scheduler (`core/jobs/report_scheduler.py`) is suitable for single-node dev/staging. For production at scale:

- Run multiple gateway replicas with **only one scheduler leader**, or
- Move report jobs to Celery/Redis queue (future extension)

### Horizontal scaling notes

| Component | Scale strategy |
|---|---|
| Gateway | Stateless; scale replicas behind LB |
| Postgres | Read replicas for analytics; single writer for metadata |
| Qdrant | Qdrant cluster mode for large collections |
| Redis | Redis Cluster or Sentinel |
| Uploads | Shared volume or S3 for `uploads/` |

---

## Health checks

| Endpoint | Use |
|---|---|
| `GET /healthz` | Liveness |
| `GET /metrics` | Prometheus scrape |

---

## Backup

- **Postgres:** daily logical dumps (`pg_dump`) — tenants, conversations, dashboards, audit events
- **Qdrant:** snapshot API per collection
- **MinIO:** bucket replication or lifecycle policies

---

## Troubleshooting

| Symptom | Check |
|---|---|
| 401 on all APIs | JWT keys set? Token in `localStorage` key `insightiq_token` |
| Rate limit 429 | Redis up? Lower traffic or raise `REQUESTS_PER_MINUTE` |
| RAG returns empty | Qdrant running? Collection ingested? |
| No traces in Jaeger | `TELEMETRY__ENABLED=true`, port 4317 reachable |
| Scheduled emails missing | Dev mode logs only — check gateway stdout for `email report` |

---

## CI/CD

GitHub Actions workflow at `.github/workflows/ci.yml` runs backend lint/tests and frontend build on every push/PR to `main`.
