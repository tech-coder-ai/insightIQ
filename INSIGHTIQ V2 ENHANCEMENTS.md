# InsightIQ — v2 Enhancement Pack

> **Purpose:** This document is a *delta* on top of the existing InsightIQ architecture. It replaces the “normal RAG”
> design with a **10-stage agentic RAG pipeline**, modernises the library stack to the best open-source tools as of
> mid-2026, adds **Oracle, S3 / object-store, and Hive** to Talk-to-Data as **first-class standalone connectors**
> (each queryable on its own, alongside the existing databases — no cross-source federation required), and
> hardens the whole platform around *generic, configurable, plugin-first* patterns.
> 
> Read it alongside the original design doc. Section numbers map 1:1 to the original where relevant.
> 
> **Version:** 2.0 · **Status:** Architecture (revised) · **Supersedes:** §4.2.2, §4.2.4, §9.3, parts of §4.1.4 / §5 / §7

-----

## 0. What Changed at a Glance

|Area                         |v1 (original)                                            |v2 (this pack)                                                                                                                    |Why                                                                                                           |
|-----------------------------|---------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
|RAG                          |Linear 5-step (embed → search → rerank → LLM → highlight)|**10-stage agentic graph** with routing, fusion, self-correction                                                                  |Multi-hop + financial math + groundedness need more than a straight line                                      |
|Doc extraction               |pdfplumber / docx / camelot / tabula / Tesseract         |**MarkItDown** (primary) + **Docling** (layout/scanned) + **Unstructured** (fallback)                                             |One normalised Markdown surface; far better table & layout fidelity                                           |
|Embeddings                   |OpenAI / MiniLM                                          |**BGE-M3** (default, MIT) · **Qwen3-Embedding** (max quality) · **nomic-embed-text** (local) — all behind the existing `IEmbedder`|OSS-first, multilingual, dense+sparse in one model                                                            |
|Reranker                     |“Cohere / cross-encoder” (vague)                         |**BGE-reranker-v2** / **Qwen3-Reranker** behind `IReranker`                                                                       |OSS cross-encoder, self-hostable                                                                              |
|Orchestration                |LangChain / LlamaIndex (implicit)                        |**LangGraph** state machine (loops + critic nodes) + LlamaIndex for ingestion helpers                                             |The 10 stages are a graph with cycles, not a chain                                                            |
|Talk-to-Data sources         |Per-DB Python drivers (Snowflake/MSSQL/Postgres/…)       |**+ Oracle, Hive, and S3/object-store as standalone `IDBConnector` plugins** (S3 queried via embedded **DuckDB**)                 |Each source registered & queried independently; new source = new connector file + `@ConnectorFactory.register`|
|Cross-source joins (optional)|—                                                        |**Trino** offered as an *opt-in* federation connector only if a tenant later wants to join across sources                         |Not required for the core ask; purely additive                                                                |
|Eval & tracing               |OTEL only                                                |**OTEL + LangSmith** traces, **Ragas / DeepEval** offline eval                                                                    |Every RAG stage is measurable                                                                                 |
|Config                       |Pydantic Settings                                        |Pydantic Settings **+ per-tenant DB overrides + YAML pipeline profiles + feature flags**                                          |Profiles: `naive                                                                                              |

-----

## 1. The 10-Stage Agentic RAG Pipeline

This replaces §9.3. It is implemented as a **LangGraph** state machine so stages can branch, loop, and self-correct.
Every stage is a registered node; the active set and their parameters come from a **pipeline profile** (YAML, see §5),
so a tenant can run anything from `naive` to full `agentic` without code changes.

### 1.1 Pipeline State Object

```python
# core/rag/state.py
@dataclass
class RagState:
    # Inputs
    raw_query: str
    conversation_history: list[Message]
    collection_ids: list[str]
    tenant_id: str
    profile: RagProfile                 # naive | advanced | graph | agentic

    # Stage 1–2 outputs
    intent: QueryIntent | None = None   # factual | summary | compare | financial_math | multi_hop
    language: str | None = None
    needs_retrieval: bool = True        # gating (skip retrieval for chit-chat / pure math)
    sub_queries: list[str] = field(default_factory=list)
    query_variations: list[str] = field(default_factory=list)
    hyde_doc: str | None = None

    # Stage 3 outputs
    route: RetrievalRoute | None = None # vector | hybrid | graph | sql_over_docs

    # Stage 4–7 outputs
    candidates: list[RetrievedChunk] = field(default_factory=list)  # carry char_start/char_end/page
    fused: list[RetrievedChunk] = field(default_factory=list)
    reranked: list[RetrievedChunk] = field(default_factory=list)
    context: CuratedContext | None = None

    # Stage 8–10 outputs
    draft_answer: str | None = None
    critic: CriticVerdict | None = None # groundedness, relevancy, missing_info
    retrieval_round: int = 0            # incremented on corrective loops
    final: HighlightedResponse | None = None

    # Telemetry (logged per node)
    trace: dict = field(default_factory=dict)
```

### 1.2 The Ten Stages

```
                ┌──────────────────────────────────────────────────────────────┐
                │                    LangGraph RAG Engine                        │
                └──────────────────────────────────────────────────────────────┘

 (1) QUERY UNDERSTANDING ──► (2) QUERY TRANSFORMATION ──► (3) ADAPTIVE ROUTING
       intent + lang              rewrite / decompose          pick strategy
       retrieval gate             HyDE + N variations          + index per query
            │                                                        │
            │ needs_retrieval == false ───────────────► (8) GENERATION (no-context path)
            ▼                                                        ▼
 (4) HYBRID RETRIEVAL ──► (5) FUSION (RRF) ──► (6) RERANK ──► (7) CONTEXT CURATION
   dense + sparse +          merge result        cross-encoder    dedupe + compress +
   metadata filters,         sets per query      top-k, attach    token budget,
   per sub-query             into one list       rerank_score     preserve char offsets
                                                                        │
                                                                        ▼
                                              (8) GROUNDED GENERATION  ◄─── financial?
                                              answer + [SOURCE:id]          │
                                              markers                       ▼
                                                    │            GRAPH RAG (Neo4j Cypher)
                                                    │            + Math engine (SymPy)
                                                    ▼
                                       (9) SELF-REFLECTION / CORRECTIVE  (CRAG / Self-RAG)
                                          grade groundedness + relevancy
                                          ├─ pass ─────────────────────────┐
                                          └─ fail → corrective retrieval ──┘
                                             (re-query / web / graph,
                                              loop back to (4), max 2 rounds)
                                                    │
                                                    ▼
                                       (10) HIGHLIGHT RESOLUTION & ASSEMBLY
                                          markers → HighlightSpan[], per-doc colors,
                                          answer_html with <cite>, typed ResponsePayload,
                                          persist + stream, emit OTEL/LangSmith trace
```

#### Stage 1 — Query Understanding & Retrieval Gating

- Classify **intent** (`factual | summary | compare | financial_math | multi_hop`) and detect **language**.
- **Gate retrieval** (RAGate-style): chit-chat, clarifications, and pure-math follow-ups skip straight to Stage 8. Saves latency and cost.
- Pull the last *N* turns from conversation history for coreference (“what about *its* APAC numbers?”).

#### Stage 2 — Query Transformation

- **Rewrite** vague / conversational queries into retrieval-friendly form (resolve pronouns against history).
- **Decompose** multi-hop questions into ordered `sub_queries`.
- **Expand**: generate 2–4 `query_variations` (RAG-Fusion) and an optional **HyDE** hypothetical answer to embed for recall.

#### Stage 3 — Adaptive Routing

- Match query complexity to pipeline complexity (cheap path for easy queries, full arsenal for hard ones).
- Choose **index/route** per sub-query: `vector` (semantic), `hybrid` (dense+sparse), `graph` (Neo4j, relationships / financial), or `sql_over_docs` (structured tables extracted into DuckDB/Trino).
- Route is itself profile-driven and overridable per collection.

#### Stage 4 — Hybrid Retrieval

- **Dense** (BGE-M3 / Qwen3) + **sparse** (BM25 or BGE-M3 sparse vectors) + **metadata filters** (tenant, collection, freshness, ACL).
- Runs once per `sub_query` × `query_variation`; each retrieved chunk carries `char_start`, `char_end`, `page_number`, `relevance_score` (feeds the highlight feature — unchanged contract from v1 §4.2.6).

#### Stage 5 — Fusion (Reciprocal Rank Fusion)

- Merge all result sets from Stage 4 into a single deduplicated candidate list via **RRF**, so a chunk that ranks well across variations floats up.

#### Stage 6 — Reranking

- **Cross-encoder** (`BGE-reranker-v2` default, `Qwen3-Reranker` for max quality) scores true query↔chunk relevance.
- Keep `top_k` (profile default 5); attach `rerank_score`. If top score < `min_relevance_threshold`, flag for the corrective loop.

#### Stage 7 — Context Curation & Compression

- Dedupe near-identical chunks, **contextually compress** (drop sentences irrelevant to the query), order by rerank score, enforce a **token budget**.
- **Critically: preserve `char_start`/`char_end` through compression** so highlighting still maps to the original document.

#### Stage 8 — Grounded Generation with Citations

- LLM generates the answer with `[SOURCE:chunk_id]` markers inline (unchanged marker contract).
- **Financial branch:** if intent == `financial_math`, route numeric reasoning to **Graph RAG** (LLM→Cypher over Neo4j) + a **math engine** (SymPy/NumPy) for exact percentages/ratios, then compose the narrative answer with citations.

#### Stage 9 — Self-Reflection / Corrective Loop (CRAG + Self-RAG)

- A **critic/grader** node scores the draft on **groundedness** (is every claim supported by context?) and **relevancy** (does it answer the question?), and lists `missing_info`.
- **Pass** → continue. **Fail** → **corrective retrieval**: re-write the query toward the gap, optionally widen to graph or an external/web tool, loop back to Stage 4. Hard cap: **2 corrective rounds** (`retrieval_round`) to bound latency/cost.
- LLM-as-judge **faithfulness** score is logged for every answer.

#### Stage 10 — Highlight Resolution & Response Assembly

- `HighlightResolver` parses `[SOURCE:chunk_id]` → `HighlightSpan[]` (doc, page, offsets, relevance + rerank scores), assigns **per-document colours**, strips markers, injects `<cite data-chunk-id="…">` into `answer_html`.
- Emits a typed `ResponsePayload` (reuses the v1 Dynamic Response Renderer), persists `highlight_spans_json`, streams to the client, and writes a full **per-stage OTEL + LangSmith trace** (`intent`, `retrieval_round`, `avg_chunk_score`, `critic_score`, `token_budget_used`, cost).

### 1.3 Per-Stage Metrics (logged every run)

|Metric                                    |Stage  |Use                            |
|------------------------------------------|-------|-------------------------------|
|`intent`, `needs_retrieval`               |1      |Routing audit, gate hit-rate   |
|`retrieval_miss_rate`                     |4–6    |Rounds that triggered a rewrite|
|`avg_chunk_score` (pre/post rerank)       |5–6    |Is initial retrieval noisy?    |
|`context_tokens`, `compression_ratio`     |7      |Budget tuning                  |
|`critic_score`, `corrective_rounds`       |9      |Quality + cost trade-off       |
|`faithfulness`, `answer_relevancy` (Ragas)|offline|Regression gating in CI        |

-----

## 2. Modernised Open-Source Library Stack

All choices slot **behind the interfaces already defined in v1** (`IEmbedder`, `IChunker`, `IExtractor`,
`IIngestionPipeline`, `IReranker` [new], `IDBConnector`, `ILLMProvider`). Swapping a library is a new file + a registry entry.

### 2.1 Document Ingestion

|Concern                                |Library                                         |License                |Role                                                                       |
|---------------------------------------|------------------------------------------------|-----------------------|---------------------------------------------------------------------------|
|Universal file → Markdown              |**MarkItDown** (`microsoft/markitdown`, v0.1.6+)|MIT                    |Primary normaliser for PDF/DOCX/PPTX/XLSX/HTML/CSV/images/audio            |
|Layout-aware / scanned / complex tables|**Docling** (`docling-project/docling`)         |MIT                    |Reading-order, table structure, OCR; used when MarkItDown confidence is low|
|Long-tail formats / fallback           |**Unstructured**                                |Apache-2.0             |Partitioning fallback for odd formats                                      |
|Hi-fi OCR (optional)                   |**RapidOCR** / Azure Document Intelligence      |Apache-2.0 / commercial|MarkItDown can delegate to Azure DI for hard scans                         |
|Tables → DataFrame                     |**Polars** (+ pandas compat)                    |MIT                    |Fast table handling, feeds `sql_over_docs` route                           |


> **Pipeline router rule:** MarkItDown first → if document has complex multi-column layout, scanned pages, or
> dense financial tables, escalate to Docling → Unstructured as last resort. The choice is recorded in
> `documents.metadata_json.extractor_used` for reproducibility.

### 2.2 Embeddings & Reranking (behind `IEmbedder` / `IReranker`)

|Tier                  |Model                                                  |License         |Dim          |When                                                                                                                 |
|----------------------|-------------------------------------------------------|----------------|-------------|---------------------------------------------------------------------------------------------------------------------|
|Default OSS           |**BGE-M3**                                             |MIT             |1024         |Self-hosted production; dense **+ sparse + multi-vector** in one model, 100+ langs (no separate keyword index needed)|
|Max quality OSS       |**Qwen3-Embedding** (0.6B / 4B / 8B)                   |Apache-2.0      |32–1024 (MRL)|Instruction-aware, top of open-weight MTEB v2                                                                        |
|Local / edge          |**nomic-embed-text** (Ollama) / **all-MiniLM-L6-v2**   |Apache-2.0 / MIT|768 / 384    |Laptop / CPU dev                                                                                                     |
|Multimodal (PDF+image)|**Qwen3-VL-Embedding** / Granite-vision                |Apache-2.0      |—            |Visual pipeline                                                                                                      |
|Hosted (optional)     |OpenAI `text-embedding-3`, Voyage 4, Gemini Embedding 2|commercial      |—            |Kept pluggable via provider factory                                                                                  |
|Reranker              |**BGE-reranker-v2** (default) / **Qwen3-Reranker**     |MIT / Apache-2.0|—            |Stage 6 cross-encoder                                                                                                |


> **Hard rule:** the embedding model used at query time **must** match the one used at index time. Store
> `embedding_model` + `dimension` on every Qdrant collection and refuse cross-model search.

### 2.3 Orchestration, Storage, Eval

|Concern          |Choice                                      |License           |Notes                                                                          |
|-----------------|--------------------------------------------|------------------|-------------------------------------------------------------------------------|
|RAG orchestration|**LangGraph**                               |MIT               |Stateful graph w/ loops & critic nodes (the 10 stages)                         |
|Ingestion helpers|**LlamaIndex**                              |MIT               |Node parsers, readers — used inside pipelines, not as the orchestrator         |
|Vector DB        |**Qdrant** (keep)                           |Apache-2.0        |Native hybrid (dense+sparse) search, payload filters; **Milvus** acceptable alt|
|Graph DB         |**Neo4j** (keep)                            |GPLv3/Comm.       |Financial Graph RAG + cross-doc knowledge graph                                |
|Keyword/sparse   |Qdrant sparse vectors **or** OpenSearch BM25|Apache-2.0        |Behind `IRetriever`                                                            |
|Tracing          |**OpenTelemetry** + **LangSmith**           |Apache-2.0 / comm.|Per-node spans, cost attribution                                               |
|Offline eval     |**Ragas** + **DeepEval**                    |Apache-2.0        |Faithfulness/relevancy/context-precision in CI                                 |
|Async work       |**Celery** (keep) + Redis                   |BSD               |Ingestion + corrective web tools                                               |

-----

## 3. Talk-to-Data: Oracle, S3 & Hive as Standalone Connectors

This **extends** the v1 connector model (§4.1.4 / §5.2) — it does **not** replace it with a federation layer. Each
data source stays independent: you register it, introspect it, and query it on its own, exactly like Snowflake or
Postgres today. We simply add **three new `IDBConnector` implementations** — Oracle, Hive, and S3/object-store —
that self-register with the existing `ConnectorFactory`. Adding any future source is the same one-file move.

> **Why no federation by default.** A federation engine (Trino/Presto) only earns its weight when you need to *join
> across* heterogeneous sources in a single query. That isn’t the requirement here, and it adds a cluster to operate.
> So federation is demoted to an **optional, opt-in connector** (§3.5) for tenants who later want cross-source joins.

### 3.1 The Connector Model (unchanged interface, more implementations)

```
                         IDBConnector  (unchanged interface from v1 §5.2)
            test_connection / introspect_schema / execute_query / validate_sql
                                       │
        ┌──────────┬──────────┬────────┼────────┬──────────┬──────────┬──────────┐
        ▼          ▼          ▼        ▼        ▼          ▼          ▼          ▼
   Snowflake   Postgres    MSSQL   ★ Oracle  ★ Hive    ★ S3 /     BigQuery   DuckDB
   (native)    (psycopg)   (pyodbc)  (oracledb)(HiveServer2) object    (native)   (files /
                                                          store               uploads)
                                                       (DuckDB
                                                        httpfs)
        │          │          │        │        │          │          │          │
        └──────────┴──────────┴────────┴────────┴──────────┴──────────┴──────────┘
                    each registered via @ConnectorFactory.register(DBType.X)
                    each pairs with its own ISQLValidator (per-dialect, v1 §9.4)
        ★ = added in v2
```

Nothing about registration, schema explorer, relationship editor, AI glossary, query interface, or the Dynamic
Response Renderer changes. A new connector just has to satisfy the four `IDBConnector` methods and ship a matching
`ISQLValidator`.

### 3.2 The Three New Connectors

|Source                       |Driver / engine                                                                                             |License   |Auth                                                    |Schema introspection                                                                                   |SQL dialect (LLM target)  |Validation                 |
|-----------------------------|------------------------------------------------------------------------------------------------------------|----------|--------------------------------------------------------|-------------------------------------------------------------------------------------------------------|--------------------------|---------------------------|
|**★ Oracle**                 |`python-oracledb` (thin mode, no Oracle client needed)                                                      |Apache-2.0|user/pwd, wallet/TLS, TNS or service name               |`ALL_TABLES` / `ALL_TAB_COLUMNS` / `ALL_CONS_COLUMNS` (PK/FK)                                          |Oracle SQL                |`EXPLAIN PLAN FOR <sql>`   |
|**★ Hive**                   |`pyhive[hive]` or `impyla` over **HiveServer2** (Thrift)                                                    |Apache-2.0|NOSASL / LDAP / Kerberos                                |`SHOW DATABASES`, `SHOW TABLES`, `DESCRIBE FORMATTED` (via metastore)                                  |HiveQL                    |`EXPLAIN <sql>`            |
|**★ S3 / MinIO object store**|**DuckDB** embedded (`httpfs` + `s3` secret) — reads Parquet/CSV/JSON/Iceberg/Delta directly, **no cluster**|MIT       |access key/secret or IAM role; custom endpoint for MinIO|per-object schema via `DESCRIBE SELECT * FROM read_parquet('s3://…')`; “tables” = registered file globs|DuckDB SQL (Postgres-like)|`EXPLAIN <sql>` (dry parse)|

Notes:

- **Oracle** is a conventional relational connector — closest in shape to the existing Postgres/MSSQL ones.
- **Hive** talks to **HiveServer2** directly; no Trino, no MapReduce knowledge needed on our side — we send HiveQL and
  read results. Schema comes from the Hive metastore via `DESCRIBE`/`SHOW`.
- **S3** is the interesting one: object stores aren’t SQL databases, so the connector embeds **DuckDB** as a tiny
  in-process query engine that reads files straight from S3/MinIO. No standing cluster, no metastore required. A
  “table” in this source is a registered **file glob** (e.g. `s3://bucket/sales/year=*/*.parquet`) that the user
  names during registration; DuckDB infers the columns. Partitioned Hive-style paths, Iceberg, and Delta are all
  readable through DuckDB extensions.

### 3.3 Connector Skeletons (drop-in, behind `IDBConnector`)

```python
# core/data/connectors/oracle.py
@ConnectorFactory.register(DBType.ORACLE)
class OracleConnector(IDBConnector):
    def __init__(self, cfg: DataSourceConfig):
        import oracledb                       # thin mode → no native client
        self._pool = oracledb.create_pool(user=cfg.user, password=cfg.secret,
                                          dsn=cfg.dsn, min=1, max=4)
    async def test_connection(self) -> bool: ...
    async def introspect_schema(self) -> SchemaMetadata:
        # ALL_TABLES / ALL_TAB_COLUMNS / ALL_CONSTRAINTS for PK/FK
        ...
    async def execute_query(self, sql: str) -> QueryResult: ...           # read-only user
    async def validate_sql(self, sql: str) -> ValidationResult:           # EXPLAIN PLAN FOR
        ...

# core/data/connectors/hive.py
@ConnectorFactory.register(DBType.HIVE)
class HiveConnector(IDBConnector):
    def __init__(self, cfg: DataSourceConfig):
        from pyhive import hive
        self._conn = hive.connect(host=cfg.host, port=cfg.port,
                                  username=cfg.user, auth=cfg.auth_mode)  # LDAP/KERBEROS/NOSASL
    async def introspect_schema(self) -> SchemaMetadata:
        # SHOW DATABASES → SHOW TABLES → DESCRIBE FORMATTED <t>
        ...
    async def validate_sql(self, sql: str) -> ValidationResult:           # EXPLAIN <sql>
        ...

# core/data/connectors/s3_object_store.py
@ConnectorFactory.register(DBType.S3_OBJECT_STORE)
class S3ObjectStoreConnector(IDBConnector):
    """Query files in S3/MinIO via an embedded DuckDB engine — no cluster."""
    def __init__(self, cfg: DataSourceConfig):
        import duckdb
        self._db = duckdb.connect()
        self._db.execute("INSTALL httpfs; LOAD httpfs;")
        self._db.execute(f"""
            CREATE SECRET s3 (TYPE S3, KEY_ID '{cfg.access_key}',
              SECRET '{cfg.secret}', ENDPOINT '{cfg.endpoint}',
              REGION '{cfg.region}', URL_STYLE 'path');   -- path style for MinIO
        """)
        self._globs = cfg.table_globs   # {logical_table_name: "s3://bucket/path/*.parquet"}
    async def introspect_schema(self) -> SchemaMetadata:
        # for each glob: DESCRIBE SELECT * FROM read_parquet('<glob>')  → columns/types
        ...
    async def execute_query(self, sql: str) -> QueryResult:
        # rewrite logical table names → read_parquet/read_csv_auto(glob) views, then run
        ...
    async def validate_sql(self, sql: str) -> ValidationResult:           # EXPLAIN <sql>
        ...
```

### 3.4 S3 / Object-Store Registration Flow (standalone, no metastore needed)

```
Register S3 / MinIO source
        │
        ▼
1. Enter endpoint, region, bucket, credentials (encrypted via Vault)
   └── "path-style" toggle for MinIO / S3-compatible stores
        │
        ▼
2. Define logical tables = file globs
   ├── sales      →  s3://dw/sales/year=*/month=*/*.parquet
   └── customers  →  s3://dw/dim/customers/*.parquet
        │
        ▼
3. DuckDB infers columns/types per glob (DESCRIBE SELECT * FROM read_parquet(...))
        │
        ▼
4. Reuse v1 flow unchanged: relationship review → AI glossary → save datasource record
```

Auto-discovery option: if a folder follows Hive-style partitioning, offer to register the whole prefix as one
partitioned table and surface partition keys as columns.

### 3.5 Optional: Trino as an opt-in *federation* connector

If a tenant later needs to **join across** sources (e.g. Oracle customers ⋈ S3 events in one query), register a
`TrinoFederatedConnector` as just *another* `IDBConnector` whose catalogs point at the same sources. It’s purely
additive — the standalone Oracle/Hive/S3 connectors above remain the default, independent path. Don’t build it unless
the cross-source-join requirement actually appears.

### 3.6 Safety (per connector, unchanged from v1)

- Every connector uses a **read-only DB principal**; `validate_sql` rejects `INSERT/UPDATE/DELETE/DROP/TRUNCATE/MERGE/CALL/ALTER`.
- Per-dialect validation (`EXPLAIN PLAN FOR` Oracle, `EXPLAIN` Hive/DuckDB) runs before execution, with the
  max-3-retry LLM feedback loop from v1 §4.1.3.
- Per-tenant source allow-list; credentials in Vault; S3 keys never logged.

-----

## 4. Generic / Extensible / Configurable Hardening

### 4.1 One Pattern Everywhere: Interface → Registry → Factory → Config

Every pluggable concern follows the same shape (v1 already does this for connectors; v2 makes it universal):

```python
# core/registry.py  — generic, reused by all subsystems
T = TypeVar("T")

class Registry(Generic[T]):
    def __init__(self, kind: str): self._kind, self._items = kind, {}
    def register(self, key: str):
        def deco(cls): self._items[key] = cls; return cls
        return deco
    def create(self, key: str, **kw) -> T:
        if key not in self._items:
            raise UnknownPluginError(self._kind, key)
        return self._items[key](**kw)

EMBEDDERS   = Registry[IEmbedder]("embedder")
CHUNKERS    = Registry[IChunker]("chunker")
EXTRACTORS  = Registry[IExtractor]("extractor")
RERANKERS   = Registry[IReranker]("reranker")        # NEW
RETRIEVERS  = Registry[IRetriever]("retriever")      # NEW (vector/hybrid/graph/sql_over_docs)
RAG_NODES   = Registry[IRagNode]("rag_node")         # NEW (the 10 stages)
CONNECTORS  = Registry[IDBConnector]("connector")
VALIDATORS  = Registry[ISQLValidator]("validator")
LLM_PROVIDERS = Registry[ILLMProvider]("llm")
EXPORTERS   = Registry[IExporter]("exporter")
```

> Adding a capability = implement the interface, decorate with `@REGISTRY.register("key")`, reference the key in
> config. **No existing file is edited** (Open/Closed).

### 4.2 Config-Driven RAG Profiles (YAML)

The 10-stage pipeline is assembled from config. A profile names which nodes run and with what params; profiles are
selectable **per tenant and per collection**, with DB overrides on top of the YAML defaults.

```yaml
# config/rag_profiles/agentic.yaml
profile: agentic
gating: true                       # Stage 1 retrieval gate on
transform:
  rewrite: true
  decompose: true
  variations: 3
  hyde: true
routing:
  strategy: adaptive               # vector | hybrid | graph | sql_over_docs | adaptive
retrieval:
  embedder: bge-m3                 # registry key
  retriever: hybrid
  top_k: 20
  filters: [tenant, collection, acl]
fusion: rrf
rerank:
  reranker: bge-reranker-v2
  top_k: 5
  min_relevance_threshold: 0.6
curation:
  compress: true
  token_budget: 6000
generation:
  llm: claude                      # provider key
  financial_graph: true
reflection:
  critic: true
  max_corrective_rounds: 2
  corrective_tools: [requery, graph, web]
highlight:
  resolve: true
```

```yaml
# config/rag_profiles/naive.yaml  — cheap path for simple FAQ collections
profile: naive
gating: false
transform: { rewrite: false, decompose: false, variations: 1, hyde: false }
routing: { strategy: vector }
retrieval: { embedder: bge-m3, retriever: vector, top_k: 5 }
fusion: none
rerank: { reranker: none }
curation: { compress: false, token_budget: 4000 }
generation: { llm: claude, financial_graph: false }
reflection: { critic: false, max_corrective_rounds: 0 }
highlight: { resolve: true }
```

Loading a profile builds the LangGraph dynamically:

```python
def build_graph(profile: RagProfile) -> CompiledGraph:
    g = StateGraph(RagState)
    g.add_node("understand", RAG_NODES.create("understand", cfg=profile.gating))
    if profile.transform.enabled: g.add_node("transform", RAG_NODES.create("transform", cfg=profile.transform))
    g.add_node("route", RAG_NODES.create("route", cfg=profile.routing))
    g.add_node("retrieve", RAG_NODES.create("retrieve", cfg=profile.retrieval))
    # ... fusion, rerank, curate, generate
    if profile.reflection.critic:
        g.add_node("critic", RAG_NODES.create("critic", cfg=profile.reflection))
        g.add_conditional_edges("critic", route_on_verdict,
                                {"pass": "highlight", "retry": "retrieve"})  # corrective loop
    g.add_node("highlight", RAG_NODES.create("highlight"))
    return g.compile()
```

### 4.3 Layered Configuration Resolution

```
ENV vars (12-factor)  ◄─ lowest precedence
        ▼
config/*.yaml defaults (pipeline profiles, model registry, Trino catalogs)
        ▼
tenant_settings table (per-tenant overrides)
        ▼
collection / conversation overrides (per-collection profile, per-conversation highlight mode)
        ▼
request-time toolbar overrides  ◄─ highest precedence
```

A single `SettingsResolver` merges these into an effective config snapshot stored on each message
(`rag_profile_snapshot_json`) for full reproducibility — re-running a dashboard card uses the exact profile it was
created with.

### 4.4 Data-Model Additions (delta on v1 §7)

```sql
-- Profiles
rag_profiles (id, tenant_id, name, scope, config_yaml, is_default, created_at)
-- scope: 'tenant' | 'collection'

-- Per-source connection config (drives Oracle, Hive, S3/object-store, and the rest)
data_source_connectors (
  id, datasource_id,
  db_type,                -- 'oracle' | 'hive' | 's3_object_store' | 'snowflake' | 'postgres' | ...
  driver,                 -- 'oracledb' | 'pyhive' | 'duckdb' | 'psycopg' | ...
  connection_config_json, -- host/port/dsn OR endpoint/region/bucket  (secrets in Vault)
  auth_mode,              -- 'password' | 'wallet' | 'ldap' | 'kerberos' | 'access_key' | 'iam'
  table_globs_json,       -- S3 only: {logical_table_name: "s3://bucket/path/*.parquet"}
  dialect,                -- 'oracle' | 'hiveql' | 'duckdb' | ... (selects the ISQLValidator)
  created_at
)

-- Reranker + retrieval provenance already covered by highlight_spans_json;
-- extend the chunk payload (Qdrant) with rerank_score + retriever_source.

-- Per-message reproducibility
ALTER TABLE tts_messages ADD COLUMN rag_profile_snapshot_json jsonb;
ALTER TABLE tts_messages ADD COLUMN retrieval_round int DEFAULT 0;
ALTER TABLE tts_messages ADD COLUMN critic_score numeric;
```

### 4.5 Qdrant payload (delta on v1 §7.2)

```
payload (additions):
  rerank_score:     float | null   # from cross-encoder
  retriever_source: string         # 'dense' | 'sparse' | 'graph' | 'sql_over_docs'
  embedding_model:  string         # guards against cross-model search
  extractor_used:   string         # 'markitdown' | 'docling' | 'unstructured'
```

-----

## 5. Updated Backend Layout (delta on v1 §5.1)

```
core/
├── rag/                      # NEW — the 10-stage engine
│   ├── state.py              # RagState, RagProfile, verdicts
│   ├── graph_builder.py      # build_graph(profile) -> LangGraph
│   ├── nodes/
│   │   ├── base.py           # IRagNode
│   │   ├── understand.py     # Stage 1
│   │   ├── transform.py      # Stage 2 (rewrite/decompose/HyDE/variations)
│   │   ├── route.py          # Stage 3 (adaptive routing)
│   │   ├── retrieve.py       # Stage 4 (hybrid)
│   │   ├── fuse.py           # Stage 5 (RRF)
│   │   ├── rerank.py         # Stage 6 (cross-encoder)
│   │   ├── curate.py         # Stage 7 (compress + budget, preserve offsets)
│   │   ├── generate.py       # Stage 8 (+ financial graph branch)
│   │   ├── critic.py         # Stage 9 (CRAG/Self-RAG corrective loop)
│   │   └── highlight.py      # Stage 10 (reuses highlight_resolver)
│   └── profiles.py           # YAML profile loader + SettingsResolver
├── retrieval/
│   ├── base.py               # IRetriever, IReranker
│   ├── hybrid_retriever.py   # dense+sparse+filters (Qdrant)
│   ├── graph_retriever.py    # Neo4j
│   ├── sql_over_docs.py      # DuckDB/Trino over extracted tables
│   └── rerankers/
│       ├── bge_reranker.py
│       └── qwen3_reranker.py
├── embeddings/
│   ├── bge_m3.py  qwen3.py  nomic.py  openai.py  (all IEmbedder)
├── ingestion/
│   ├── extractors/ markitdown.py  docling.py  unstructured.py  (IExtractor)
│   └── pipeline_router.py    # confidence-based escalation
└── data/
    └── connectors/
        ├── base.py               # IDBConnector + ConnectorFactory (v1, unchanged)
        ├── oracle.py             # ★ new — python-oracledb (thin)
        ├── hive.py               # ★ new — pyhive/impyla over HiveServer2
        ├── s3_object_store.py    # ★ new — embedded DuckDB over S3/MinIO files
        ├── duckdb_files.py       # ad-hoc CSV/Parquet uploads
        ├── snowflake.py  mssql.py  postgres.py  bigquery.py
        └── trino_federated.py    # OPTIONAL — only if cross-source joins are needed
    └── validators/               # one ISQLValidator per dialect (v1 §9.4)
        ├── oracle_validator.py   # EXPLAIN PLAN FOR
        ├── hiveql_validator.py   # EXPLAIN
        ├── duckdb_validator.py   # EXPLAIN  (S3 + file sources)
        └── ...
```

-----

## 6. Updated Roadmap Notes (delta on v1 §15)

- **Phase 1** add: `IDBConnector` + `ConnectorFactory` with Postgres first; per-dialect `ISQLValidator` from day one (no federation engine to stand up).
- **Phase 2** add: the three new standalone connectors — **Oracle** (`python-oracledb`), **Hive** (`pyhive`/HiveServer2), **S3/object-store** (embedded DuckDB over MinIO) — each with its dialect validator and the S3 file-glob registration flow.
- **Phase 3** becomes the **10-stage LangGraph** build: nodes 1–10, profile loader, Ragas eval harness in CI, MarkItDown→Docling→Unstructured router, BGE-M3 + BGE-reranker-v2.
- **Optional later**: `TrinoFederatedConnector` only if a cross-source-join requirement appears.

-----

*v2 enhancement pack. Pair with `CURSOR_BUILD_PROMPT.md` to scaffold the implementation.*