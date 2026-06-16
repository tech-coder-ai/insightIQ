# InsightIQ v2 — Phase 3 Notes

## What was built

### 10-stage LangGraph RAG engine (`core/rag/`)
- **Profiles**: `naive`, `advanced`, `graph`, `agentic` YAML configs
- **Nodes**: understand → transform → route → retrieve → fuse → rerank → curate → generate → critic → highlight
- **Corrective loop**: critic failure re-routes to retrieve (bounded by `max_corrective_rounds`)
- **Financial branch**: SymPy percentage helper in generate node when intent is `financial_math`

### Ingestion
- **Extractor router**: MarkItDown → Docling → Unstructured escalation
- **Recursive chunker** with `char_start` / `char_end` preserved
- **Hash dev embedder** (deterministic; swap to BGE-M3 for production)
- **Qdrant** hybrid vector store with tenant + collection filters

### Talk to Documents API
- `POST /talk-to-docs/collections` — create collection with RAG profile
- `POST /talk-to-docs/collections/{id}/upload` — ingest file → chunk → embed → Qdrant
- `POST /talk-to-docs/ask` — run LangGraph pipeline, return answer + highlights + profile snapshot

### Highlighting
- `[SOURCE:chunk_id]` markers resolved to `HighlightSpan[]` with per-document colors
- `answer_html` with `<cite data-chunk-id="…">` tags

### Tests
- `tests/test_rag.py` — RRF, highlight resolver, profile diff, engine smoke
- `tests/eval/ragas_smoke.py` — CI golden-query smoke gate

### Frontend
- Talk to Documents page: collection create, upload, ask, highlight panel

## Run

```bash
cd insightiq/backend
uv run alembic upgrade head   # 0004_documents
uv run uvicorn gateway.main:app --reload --port 8000
```

Ensure Qdrant is up (`docker compose up -d qdrant`).

## Assumptions
- BGE-M3 / BGE-reranker-v2 deferred — dev uses `hash-dev` embedder + heuristic reranker
- Docling/Unstructured escalate paths reuse MarkItDown until full libs are wired
- Neo4j Graph RAG stubbed via `financial_math` intent routing flag

## TODO(phase4+)
- Wire BGE-M3 + BGE-reranker-v2 behind registries
- PDF SVG overlay for source highlighting
- Full Ragas faithfulness/relevancy metrics in CI
- Dashboard Manager pin-from-RAG-response
