# InsightIQ v2 — Phase 1 Notes

## What was built

### Auth
- `POST /auth/register` — creates tenant + admin user, returns RS256 JWT
- `POST /auth/login` — returns JWT
- `RequestContext` dependency parses Bearer token for tenant/user/role
- `require_role()` RBAC helper

### Chat persistence (auto-save from message #1)
- `POST /chat/messages` — persist a message
- `GET /chat/messages?conversation_id=...` — list messages in a conversation
- Talk-to-Data `/ask` auto-persists user + assistant messages

### Talk to Data (Postgres)
- `POST /talk-to-data/sources` — register a Postgres datasource (tests connection)
- `GET /talk-to-data/sources` — list tenant datasources
- `POST /talk-to-data/ask` — NL→SQL (heuristic LLM) → validate → execute → `data_table` response

### Plugin-first plumbing
- `core/registry.py` — generic typed registry
- `core/data/connectors/*` — `IDBConnector` + auto-import factory
- `core/data/validators/*` — `ISQLValidator` + Postgres `EXPLAIN` validator
- `core/llm/*` — `ILLMProvider` + heuristic dev provider
- `core/response/*` — `ResponsePayload` + `data_table` formatter

## Local dev setup

```bash
cd insightiq
docker compose up -d

cd backend
uv sync
eval "$(python scripts/generate_dev_keys.py)"
uv run alembic upgrade head
uv run uvicorn gateway.main:app --reload --port 8000

cd ../frontend
npm install
npm start
```

## Assumptions (Phase 1)
- Datasource credentials stored in Postgres metadata DB (Vault integration TODO phase6).
- NL→SQL uses `heuristic` provider for offline dev; Anthropic provider TODO phase2.
- Single gateway process; service boundaries are package-level only.

## TODO(phase2)
- Anthropic `ILLMProvider` implementation
- Oracle / Hive / S3 connectors
- Schema introspection wizard + relationship editor + AI glossary
- Full Dynamic Response Renderer matrix in Angular
