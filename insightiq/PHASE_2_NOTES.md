# InsightIQ v2 — Phase 2 Notes

## What was built

### Connectors (plugin-first, standalone)
- **S3 / MinIO** (`s3_object_store`) — embedded DuckDB + `httpfs`, file globs as logical tables
- **DuckDB files** (`duckdb_files`) — local CSV/Parquet uploads
- **Postgres** — extended with `introspect_schema()`
- Unified **`open_connector()`** runner for SQLAlchemy vs DuckDB connectors

### Schema & metadata
- `GET /talk-to-data/sources/{id}/schema` — introspect + cache snapshot
- `PUT/GET /talk-to-data/sources/{id}/relationships` — relationship editor data
- `POST/GET /talk-to-data/sources/{id}/glossary` — AI glossary generation (heuristic from schema)

### Response system
- Expanded `ResponseType` enum (kpi_card, chart_bar, data_table, …)
- `classify_and_format()` picks response shape from query result + question

### Chat history
- `conversations` table with title, folder, tags, starred
- `GET /chat/conversations` — search + filter
- `PATCH /chat/conversations/{id}` — rename, folder, tags, star
- `POST /chat/conversations/{id}/fork` — fork conversation + messages

### Frontend
- **Dynamic Response Renderer** (kpi, bar chart, table)
- **Schema tree** component
- **Chat sidebar** with search + star
- **S3 registration** form alongside Postgres

## Migration
```bash
cd insightiq/backend
uv run alembic upgrade head   # applies 0003_phase2
```

## TODO(phase3)
- Oracle / Hive connectors
- Anthropic LLM provider for real NL→SQL
- 10-stage LangGraph RAG pipeline
- Full chart.js integration for all chart types
