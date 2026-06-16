# InsightIQ v2 — Phase 4 Notes

## What was built

### Dashboard Manager backend
- **Models**: `Dashboard`, `DashboardCard`, `DashboardShare`
- **Migration**: `0005_dashboards`
- **`ICardRefresher`** plugin registry with `sql` and `rag` refreshers
- Live refresh re-runs SQL or RAG using snapshotted `source_config_json`

### API
| Endpoint | Purpose |
|---|---|
| `POST /dashboards` | Create dashboard |
| `GET /dashboards` | List dashboards |
| `GET /dashboards/{id}` | Dashboard + cards |
| `PATCH /dashboards/{id}/filters` | Global filter bar state |
| `POST /dashboards/{id}/cards` | Pin a response card |
| `PATCH /dashboards/{id}/cards/{cardId}` | Update grid layout |
| `POST /dashboards/{id}/cards/{cardId}/refresh` | Live refresh |
| `POST /dashboards/{id}/share` | Generate read-only share token |
| `GET /public/dashboards/{token}` | Public read-only view |

### Frontend
- **Dashboard list** (`/dashboards`)
- **Dashboard canvas** with `angular-gridster2` (drag + resize)
- **Global filter bar** (region, date range)
- **Pin to dashboard** from Talk to Data
- **Public view** (`/d/{token}`)

## Run

```bash
cd insightiq/backend
uv run alembic upgrade head   # 0005_dashboards
```

## Assumptions
- Team access stored as `team_access_json` (enforcement TODO phase6)
- Prompt card refresher deferred to Phase 5 Prompt Studio
- Auto-refresh uses minimum interval across live cards on canvas

## TODO(phase5)
- Pin from Talk to Documents (RAG cards)
- Prompt Studio card refresher
