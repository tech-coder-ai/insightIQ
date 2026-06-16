# Cursor Build Prompt — InsightIQ v2

> **How to use this file.** Drop it into your repo root as `AGENTS.md` (or paste the top section into Cursor’s
> *Rules for AI* / `.cursorrules`). Then drive the build phase-by-phase: tell Cursor *“Implement Phase 1 from
> AGENTS.md. Stop at the acceptance criteria and show me the diff.”* Work one phase at a time, review, commit, repeat.
> Never let it implement more than one phase per turn.

-----

## SYSTEM ROLE (paste this as Cursor’s rule)

You are the lead engineer building **InsightIQ**, a modular, multi-tenant, AI-powered intelligence platform with five
products: **Talk to Data**, **Talk to Documents**, **Prompt Studio**, **Chat History**, and **Dashboard Manager**,
plus an **Extensibility Core** (plugin registry + event bus). Build it to be **generic, configurable, plugin-first,
and SOLID** so new databases, file formats, embedding models, RAG stages, and exporters are added as *config + a new
file*, never by editing existing code.

### Non-negotiable engineering rules

1. **Open/Closed via registries.** Every pluggable concern (DB connectors, SQL validators, extractors, chunkers,
   embedders, rerankers, retrievers, RAG nodes, LLM providers, exporters) is defined by an **interface**, implemented
   in its own file, and self-registers in a typed **Registry**. Selection is by **config key**. Adding a capability
   must not modify an existing file.
1. **Config over code.** Behaviour is driven by layered config: env vars → YAML defaults → tenant overrides →
   collection/conversation overrides → request-time overrides. The RAG pipeline is assembled from a **YAML profile**.
1. **Contract-first.** Define the OpenAPI 3.1 spec and shared TypeScript/Python types before implementing endpoints.
1. **Type-safe.** Python: full type hints, `mypy --strict`, Pydantic v2 models. Frontend: strict TypeScript.
1. **Tested.** Every use-case and every registry-backed component ships with unit tests. RAG quality is gated by an
   offline **Ragas/DeepEval** eval set in CI. Target ≥80% coverage on `core/` and `services/*/application/`.
1. **Observable.** Structured JSON logs with correlation IDs; OpenTelemetry spans on every request and every RAG node;
   LangSmith tracing for the RAG graph.
1. **Secure by default.** Read-only DB principals; no destructive SQL ever generated or executed; secrets in Vault;
   row-level tenant isolation on every query; JWT (RS256) + RBAC.
1. **Small, reviewable commits.** One concern per commit, conventional-commit messages, no giant dumps.
1. **No placeholders left behind.** If you stub something, mark it `# TODO(phaseN):` and list it in the phase summary.

### Definition of Done (every phase)

- Code compiles, `mypy --strict` + `ruff` + `eslint` clean.
- Tests written and passing; coverage not reduced.
- `docker compose up` brings the new pieces online.
- OpenAPI spec updated; types regenerated for the frontend.
- A short `PHASE_N_NOTES.md` listing what was built, decisions, and TODOs.

-----

## TECH STACK (pin these)

**Backend** — Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (async) + Alembic, Celery + Redis, `uv` for deps.
**Frontend** — Angular (latest stable, standalone components + Signals), NgRx (SignalStore where it fits), AG Grid,
Chart.js, Monaco editor, `ng2-pdf-viewer`, `angular-gridster2`.
**RAG / AI** —

- Orchestration: **LangGraph** (stateful graph, loops, critic nodes). LlamaIndex only for ingestion helpers.
- Doc extraction: **MarkItDown** (primary) → **Docling** (layout/scanned/tables) → **Unstructured** (fallback).
- Embeddings (behind `IEmbedder`): **BGE-M3** default, **Qwen3-Embedding** max-quality, **nomic-embed-text** local;
  OpenAI/Voyage/Gemini pluggable. Match index-time and query-time models.
- Reranker (behind `IReranker`): **BGE-reranker-v2** default, **Qwen3-Reranker** option.
- LLM providers (behind `ILLMProvider`): Anthropic Claude, OpenAI, Azure OpenAI, Ollama (local), HuggingFace.
  **Data** — PostgreSQL (metadata), **Qdrant** (vectors, hybrid dense+sparse), **Neo4j** (financial/graph RAG),
  Redis (cache/broker/event bus), **MinIO** (object storage + an S3 data source to demo against),
  **DuckDB** (embedded engine powering the S3/object-store connector and ad-hoc file uploads), Vault (secrets).
  Talk-to-Data connectors are **standalone per source** — Oracle (`python-oracledb`), Hive (`pyhive`/HiveServer2),
  S3/object-store (DuckDB), plus Snowflake/MSSQL/Postgres/BigQuery. **Trino is optional**, added only if cross-source
  joins are ever required.
  **Eval/observability** — OpenTelemetry, LangSmith, Ragas + DeepEval, Prometheus + Grafana + Jaeger + Loki.

-----

## MONOREPO LAYOUT (create this)

```
insightiq/
├── AGENTS.md                      # this file
├── docker-compose.yml
├── openapi/insightiq.yaml         # contract-first spec
├── backend/
│   ├── pyproject.toml             # uv, ruff, mypy
│   ├── gateway/                   # FastAPI gateway: auth, rate-limit, routing, SSE/WS
│   ├── core/                      # shared kernel — NO feature-specific code
│   │   ├── registry.py            # generic typed Registry
│   │   ├── rag/                   # 10-stage LangGraph engine (see SPEC A)
│   │   ├── retrieval/             # IRetriever, IReranker, hybrid/graph/sql_over_docs
│   │   ├── embeddings/            # IEmbedder impls
│   │   ├── ingestion/             # IExtractor + pipeline_router (MarkItDown→Docling→…)
│   │   ├── llm/                   # ILLMProvider + provider_factory
│   │   ├── response/              # ResponseType, classifier, formatter
│   │   ├── data/connectors/       # IDBConnector + ConnectorFactory: oracle, hive,
│   │   │                          #   s3_object_store (DuckDB), snowflake, mssql, postgres,
│   │   │                          #   bigquery, duckdb_files; trino_federated (OPTIONAL)
│   │   ├── events/                # Redis Streams event bus
│   │   ├── plugins/               # PluginRegistry
│   │   ├── export/                # IExporter registry (PDF/PPT later)
│   │   └── telemetry/             # OTEL + LangSmith
│   ├── services/                  # bounded contexts (DDD): domain/application/infrastructure/api
│   │   ├── talk_to_data/
│   │   ├── talk_to_docs/
│   │   ├── prompt_studio/
│   │   ├── chat_history/
│   │   ├── dashboards/
│   │   └── auth/
│   ├── config/
│   │   ├── rag_profiles/          # naive.yaml advanced.yaml graph.yaml agentic.yaml
│   │   ├── connectors/            # per-source connection templates + dialect notes
│   │   │                          #   (Trino catalogs only if the optional federation connector is used)
│   │   └── settings.py            # Pydantic Settings + SettingsResolver (layered)
│   ├── migrations/                # Alembic
│   └── tests/                     # unit + eval harness (Ragas/DeepEval)
└── frontend/
    └── src/app/{core,shared,features}/   # features lazy-loaded per product
```

-----

## SPEC A — The 10-Stage Agentic RAG Engine (`core/rag/`)

Implement a **LangGraph** state machine over a `RagState` dataclass. Each stage is a node implementing `IRagNode`,
registered in `RAG_NODES`, and assembled from a YAML profile. Stages:

1. **Query Understanding & Gating** — intent (`factual|summary|compare|financial_math|multi_hop`), language,
   `needs_retrieval` gate (skip retrieval for chit-chat/pure-math), coreference from history.
1. **Query Transformation** — rewrite, decompose into `sub_queries`, generate N `query_variations` (RAG-Fusion),
   optional **HyDE**.
1. **Adaptive Routing** — pick route per sub-query: `vector | hybrid | graph | sql_over_docs`; match query
   complexity to pipeline complexity.
1. **Hybrid Retrieval** — dense (BGE-M3/Qwen3) + sparse (BM25/BGE-M3 sparse) + metadata filters (tenant, collection,
   ACL, freshness); each chunk carries `char_start/char_end/page/relevance_score`.
1. **Fusion (RRF)** — reciprocal rank fusion across all result sets → one deduped candidate list.
1. **Reranking** — cross-encoder (`BGE-reranker-v2`), keep `top_k`, attach `rerank_score`; flag low scores.
1. **Context Curation & Compression** — dedupe, contextual compression, token budget; **preserve char offsets**.
1. **Grounded Generation** — answer with `[SOURCE:chunk_id]` markers; if `financial_math`, branch to Graph RAG
   (LLM→Cypher over Neo4j) + math engine (SymPy/NumPy) for exact numerics.
1. **Self-Reflection / Corrective Loop** — critic grades groundedness + relevancy; on fail, corrective retrieval
   (requery/graph/web) loops back to Stage 4; **max 2 rounds**; log LLM-as-judge faithfulness.
1. **Highlight Resolution & Assembly** — markers → `HighlightSpan[]`, per-doc colours, `<cite>` HTML, typed
   `ResponsePayload`, persist `highlight_spans_json`, stream, emit full per-stage OTEL/LangSmith trace.

Profiles (`config/rag_profiles/*.yaml`) declare which nodes run and their params; `build_graph(profile)` wires the
graph including the conditional corrective edge. Implement `naive`, `advanced`, `graph`, `agentic`. Selectable per
tenant/collection; snapshot the effective profile onto every message for reproducibility.

**Acceptance:** golden-query eval set runs in CI via Ragas; switching a collection’s profile from `naive`→`agentic`
changes behaviour with **zero code change**; corrective loop demonstrably re-retrieves on a planted low-relevance query.

-----

## SPEC B — Talk to Data: Standalone Per-Source Connectors

Use the v1 connector model: an `IDBConnector` interface (`test_connection / introspect_schema / execute_query / validate_sql`) with one implementation **per source**, each self-registering via `@ConnectorFactory.register(DBType.X)`
and pairing with its own `ISQLValidator`. Sources are registered and queried **independently** — no federation, no
cross-source joins required. Adding a source = one new connector file + one validator file + a `DBType` enum value.

Implement these connectors:

- **Oracle** — `python-oracledb` (thin mode, no native client). Introspect via `ALL_TABLES` / `ALL_TAB_COLUMNS` /
  `ALL_CONSTRAINTS` (PK/FK). Dialect: Oracle SQL. Validate with `EXPLAIN PLAN FOR <sql>`.
- **Hive** — `pyhive[hive]` (or `impyla`) over **HiveServer2** (Thrift); auth NOSASL/LDAP/Kerberos. Introspect via
  `SHOW DATABASES` / `SHOW TABLES` / `DESCRIBE FORMATTED`. Dialect: HiveQL. Validate with `EXPLAIN <sql>`.
- **S3 / MinIO object store** — embed **DuckDB** (`INSTALL httpfs; LOAD httpfs;` + an S3 `CREATE SECRET`, path-style
  for MinIO). A “table” is a user-registered **file glob** (e.g. `s3://bucket/sales/year=*/*.parquet`); infer columns
  with `DESCRIBE SELECT * FROM read_parquet('<glob>')`. At query time rewrite logical table names to
  `read_parquet`/`read_csv_auto` views. Dialect: DuckDB SQL. Validate with `EXPLAIN <sql>`. **No cluster, no metastore.**
- Keep/add the relational ones (Snowflake, MSSQL, Postgres, BigQuery) and **DuckDB** for ad-hoc CSV/Parquet uploads.

**S3 registration flow:** endpoint/region/bucket/credentials (+ path-style toggle for MinIO) → user names logical
tables as file globs → DuckDB infers schema per glob → reuse the existing relationship-review → AI-glossary → save
flow. Offer auto-registration of Hive-style partitioned prefixes as one partitioned table.

**SQL generation:** build the system prompt per source from `datasource.dialect` (Oracle SQL / HiveQL / DuckDB SQL) so
the LLM targets the correct dialect for whichever single source the conversation is bound to.

**Safety (every connector):** read-only principal; `validate_sql` rejects `INSERT/UPDATE/DELETE/DROP/TRUNCATE/MERGE/ CALL/ALTER`; per-dialect `EXPLAIN`-style validation before execution with the max-3-retry LLM feedback loop;
per-tenant source allow-list; secrets in Vault; never log S3 keys.

**Optional (do NOT build unless asked):** a `TrinoFederatedConnector` registering sources as Trino catalogs, for
tenants who later need to *join across* Oracle + S3 + Hive in one query. It is just another `IDBConnector`; the
standalone connectors remain the default and independent path.

**Acceptance:** Oracle, Hive, and S3 can each be registered, introspected, and queried **on their own**;
“Show me revenue by region” against a Parquet dataset in MinIO returns a rendered chart end-to-end via the DuckDB
connector; adding a hypothetical new source touches only new files (no edits to existing connectors).

-----

## SPEC C — Generic plumbing

- `core/registry.py`: one generic `Registry[T]` reused by all subsystems (see enhancement pack §4.1).
- `config/settings.py`: `SettingsResolver` merging env → YAML → tenant → collection → request, producing an effective
  snapshot per request.
- `core/events/bus.py`: Redis Streams event bus; ingestion-complete, card-refresh, audit events published here.
- `core/response/`: `ResponseType` enum + classifier + formatter feeding the Angular **Dynamic Response Renderer**
  (strategy map keyed by `ResponseType`). Response types: kpi_card, data_table, chart_{bar,line,pie,scatter,heatmap},
  multi_panel, explanation, combined, error.

-----

## PHASED BUILD PLAN

Implement **one phase per turn**. After each, stop at acceptance criteria and present the diff + `PHASE_N_NOTES.md`.

### Phase 0 — Scaffold

Monorepo, docker-compose (postgres, redis, qdrant, neo4j, **minio** [S3 source to demo against], vault, jaeger,
prometheus, grafana, loki), `pyproject.toml` (uv/ruff/mypy), Angular app shell, CI (lint+type+test+ragas-smoke),
empty OpenAPI spec, `core/registry.py`. (No Trino/metastore — connectors are standalone and embedded.)
**Done:** `docker compose up` healthy; `mypy --strict` passes on empty `core`.

### Phase 1 — Foundation

Auth service (JWT RS256, tenants, users, RBAC viewer/editor/admin/super-admin), shared Angular component library
(data-table, chart, file-upload, chat-bubble, kpi-card, schema-tree), `ILLMProvider` + Anthropic provider,
`IDBConnector` + `ConnectorFactory` + **PostgresConnector** (`psycopg`) + a per-dialect `ISQLValidator`,
basic Talk-to-Data (NL→Postgres SQL→table response), **chat auto-save from message #1**.
**Done:** log in, register a Postgres source, ask a question, see a table; every message persisted.

### Phase 2 — Talk to Data complete

All sources as Trino catalogs (**Oracle, Hive, Iceberg/Delta on S3/MinIO**, Snowflake, MSSQL, BigQuery) + DuckDB for
uploads; schema introspection wizard; relationship editor; **AI glossary** generation + review; all response types +
classifier + Dynamic Response Renderer; object-store registration flow; Chat History sidebar (folders, tags, star,
search, rename, fork, share).
**Done:** SPEC B acceptance met; full response-type matrix renders.

### Phase 3 — Talk to Documents + 10-stage RAG (SPEC A)

Ingestion router (MarkItDown→Docling→Unstructured) with `extractor_used` provenance; chunkers; `IEmbedder`
(BGE-M3 default) + Qdrant hybrid index storing `char_start/char_end`; the **full 10-stage LangGraph** with profiles
(`naive/advanced/graph/agentic`); `IReranker` (BGE-reranker-v2); **Context Source Highlighting** (resolver, SVG PDF
overlay, side panel, relevance scores) per v1 §4.2.6; financial pipeline + Neo4j Graph RAG + SymPy math; summarization,
insights, cross-doc Q&A; Ragas eval harness in CI.
**Done:** SPEC A acceptance met; highlights map to exact source spans; profile switch changes behaviour with no code edit.

### Phase 4 — Dashboard Manager

Pin-to-dashboard from any response; `angular-gridster2` canvas; card types; live vs snapshot refresh (`ICardRefresher`:
sql/rag/prompt); global filter bar; share via token; team access; auto-refresh; public read-only view. Card refresh
re-runs using the snapshotted RAG profile / SQL.
**Done:** pin a chart, resize, refresh-live, share a read-only link.

### Phase 5 — Prompt Studio

Template editor (`{{vars}}`, Jinja2), datasource/document/file binding, version control + run history, LLM-as-judge
eval scorecard, prompt library + sharing, pin prompt-run output to dashboard.
**Done:** create/version/run a prompt; eval scores show; pin output.

### Phase 6 — Hardening

Multi-tenancy + RBAC enforcement everywhere, audit logging, rate limiting, full observability stack wired, perf passes
against the §14.1 targets.
**Done:** tenant isolation tests pass; traces visible in Jaeger/LangSmith; dashboards in Grafana.

### Phase 7 — First extensions (prove the plugin model)

PDF + PPT exporters (`IExporter`), scheduled card refresh + email report, conversation export to Markdown/PDF — each
added **without editing core**.
**Done:** a new exporter is a single new file + registry entry.

-----

## GUARDRAILS (repeat to the agent often)

- Never generate or execute destructive SQL. Trino principal is read-only.
- Never embed at query time with a different model than the index was built with.
- Preserve `char_start/char_end` through chunking, compression, and reranking — highlighting depends on it.
- Keep `core/` free of feature-specific code; cross-feature talk goes through the event bus.
- Don’t add a dependency without pinning it and noting the license (prefer MIT/Apache-2.0).
- If a requirement is ambiguous, propose the generic/configurable option and note the assumption in `PHASE_N_NOTES.md`.

-----

*Build phase by phase. Review every diff. Commit small.*