# InsightIQ v2 — Phase 6 Notes

## What was built

### Multi-tenancy & RBAC
- **`core/tenancy.py`**: `assert_tenant_match`, dashboard team-access checks (`user_can_access_dashboard`, `user_can_edit_dashboard`)
- **Dashboard API** enforces owner / team / admin access on list, get, edit, pin, share
- **`PATCH /dashboards/{id}/team-access`** to grant viewer/editor access by user id
- **Tenant isolation tests** in `tests/test_tenancy.py`

### Audit logging
- **`AuditEvent` model** + migration `0007_hardening`
- **`core/audit/service.py`**: persists audit rows + publishes to Redis Streams
- Dashboard mutations (create, pin, share, filters, team access) audited
- **`GET /admin/audit`** (admin role, tenant-scoped)

### Rate limiting
- **Redis-backed** sliding window per auth header + path (`RateLimitMiddleware`)
- Configurable via `INSIGHTIQ_RATE_LIMIT__REQUESTS_PER_MINUTE` (default 120)
- Graceful bypass when Redis unavailable

### Observability
- **Structured JSON logs** with `correlation_id` (`CorrelationIdMiddleware`, `X-Correlation-ID` response header)
- **OpenTelemetry** OTLP gRPC export to Jaeger (`INSIGHTIQ_TELEMETRY__OTLP_ENDPOINT`)
- **Prometheus metrics** at `/metrics` (request count + latency histogram)
- **Grafana** dashboard provisioned: `InsightIQ Gateway`

### Event bus
- **`core/events/bus.py`**: Redis Streams (`insightiq:events`) for audit + future async workflows

## Run

```bash
cd insightiq
docker compose up -d
cd backend
uv sync
uv run alembic upgrade head   # 0007_hardening
uv run uvicorn gateway.main:app --reload --port 8000
```

- Jaeger UI: http://localhost:16686
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

Set `INSIGHTIQ_TELEMETRY__ENABLED=false` to disable OTEL in local dev without Jaeger.

## Assumptions
- Rate limit key uses auth header prefix (not decoded JWT) for speed
- Prometheus scrapes gateway via `host.docker.internal:8000` (macOS/Windows Docker Desktop)
- Vault/KMS key rotation still TODO for production secrets

## TODO(phase7)
- PDF/PPT exporters via `IExporter` registry
- Scheduled card refresh + email report
- Conversation export
