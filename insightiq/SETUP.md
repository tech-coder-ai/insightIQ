# InsightIQ — New Machine Setup Guide

Use this document to install and run the full InsightIQ stack on a fresh laptop or server.

> **Setting up on Windows?** Jump to **[§ Windows setup](#windows-setup)** for Docker Desktop, PowerShell commands, WSL2 notes, and Postgres/Redis without Docker on Windows. Want to skip Docker entirely? See **[§ Fully native Windows setup (no Docker at all)](#fully-native-windows-setup-no-docker-at-all)**.

---

## 1. What you are setting up

InsightIQ is a monorepo with three main parts:

| Part | Path | Purpose |
|------|------|---------|
| **Backend (gateway)** | `insightiq/backend/` | FastAPI API — auth, Talk to Data, Talk to Docs, dashboards, prompts |
| **Frontend (SPA)** | `insightiq/frontend/` | Angular 18 web UI |
| **Infrastructure** | `insightiq/docker-compose.yml` | Postgres, Redis, Qdrant, MinIO, optional observability |

```text
Browser (4200) ──► Angular frontend
       │
       └──► FastAPI gateway (8000)
                 ├── PostgreSQL   (app metadata, users, conversations)
                 ├── Redis        (rate limits, event bus — optional in dev)
                 ├── Qdrant       (document vectors / RAG)
                 └── MinIO        (S3-compatible storage for connectors)
```

---

## 2. Prerequisites

### Required (minimum to run the app)

| Tool | Version | Why |
|------|---------|-----|
| **Git** | any recent | Clone the repository |
| **Docker Desktop** or **Docker Engine + Compose** | Docker 24+, Compose v2 | Easiest way to run Postgres, Redis, Qdrant, MinIO |
| **Python** | **3.12+** | Backend runtime |
| **[uv](https://docs.astral.sh/uv/)** | latest | Python dependency install & virtualenv |
| **Node.js** | **20 LTS+** (22 OK) | Frontend build & dev server |
| **npm** | 10+ (bundled with Node) | Frontend packages |

Install uv (macOS/Linux):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install uv (Windows PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Restart terminal, then:
uv --version
```

PowerShell env vars (Windows — use instead of `export`):

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_MODEL = "gpt-4o-mini"
$env:INSIGHTIQ_RATE_LIMIT__ENABLED = "false"   # if Redis is not running
```

### Strongly recommended

| Tool | Why |
|------|-----|
| **curl** | Health checks, Pagila sample DB download |
| **OpenAI API key** (or compatible endpoint) | LLM answers for Talk to Data / Talk to Docs (`OPENAI_API_KEY`) |

Optional LLM env vars:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"          # optional, default in code
export OPENAI_BASE_URL="https://..."       # optional, for Groq/Together/vLLM/etc.
```

### Optional (feature-specific)

| Tool | When you need it |
|------|------------------|
| **OCR extra** (`uv sync --extra ocr`) | Scanned/image PDF ingestion (Talk to Docs OCR fallback) — no system install needed, see below |
| **Enterprise DB drivers** | `uv sync --extra connectors` for MSSQL, Oracle, Snowflake, Hive, BigQuery |
| **Neo4j** (via Docker, or point at a remote instance) | Graph RAG profile only |
| **Jaeger / Prometheus / Grafana** | Local observability (already in `docker-compose.yml`) |

**OCR (all platforms, pip-only — no Tesseract binary required):**

```bash
cd insightiq/backend
uv sync --extra ocr
```

This installs [RapidOCR](https://github.com/RapidAI/RapidOCR) + ONNX Runtime. Unlike Tesseract, RapidOCR is a pure-Python package — the recognition models ship inside the wheel, so there's nothing to install at the OS level (no Homebrew, no apt package, no Windows `.exe` installer). It works identically on macOS/Linux/Windows.

`pytesseract` + a system Tesseract install is still supported as a legacy fallback (`_ocr_with_pytesseract` in `core/ingestion/extractors/ocr_pdf.py` runs if RapidOCR isn't installed or finds no text), but you don't need it — RapidOCR is tried first and is sufficient on its own. If you'd rather use Tesseract specifically (e.g. for a language RapidOCR doesn't cover well), see the Windows Tesseract link below or `brew install tesseract` / `apt install tesseract-ocr`, plus `uv add pytesseract`.

> Note: PyPI packages named `tesseract-ocr-data` / `tessdata` only bundle Tesseract's trained **language data files**, not the actual OCR engine binary. Since `pytesseract` just shells out to the `tesseract` executable, installing those packages alone does **not** avoid the system install — RapidOCR (above) is the real pip-only alternative.

---

## Windows setup

This section is for **Windows 10/11**. The recommended path is **Docker Desktop + native PowerShell** (or Windows Terminal). WSL2 is optional but works well if you already use Ubuntu daily. Docker isn't strictly required — see **[§ Fully native Windows setup (no Docker at all)](#fully-native-windows-setup-no-docker-at-all)** if you'd rather run Postgres/Qdrant/etc. as native Windows binaries.

### Windows prerequisites (install order)

| Tool | How to install | Notes |
|------|----------------|-------|
| **Git for Windows** | https://git-scm.com/download/win | Includes **Git Bash** (needed for Pagila shell script) |
| **Docker Desktop** *(optional)* | https://www.docker.com/products/docker-desktop/ | Enable **WSL2 backend** when prompted; requires virtualization in BIOS. Skip if going fully native — see below |
| **Python 3.12+** | https://www.python.org/downloads/ | Check **“Add python.exe to PATH”** during install |
| **uv** | `powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"` | Restart terminal after install |
| **Node.js 20 LTS** | https://nodejs.org/ | Includes npm |
| **OpenAI API key** | Platform dashboard | Set as env var before starting backend |

Optional:

| Tool | Install |
|------|---------|
| **Windows Terminal** | Microsoft Store — better tabs than cmd.exe |
| **WSL2 + Ubuntu** | `wsl --install` — optional; run the same Linux commands from SETUP.md inside Ubuntu |
| **OCR support** | `uv sync --extra ocr` (from `backend/`) — pip-only via RapidOCR, **no separate Windows installer needed**. Only install [Tesseract for Windows](https://github.com/UB-Mannheim/tesseract/wiki) if you specifically want the legacy engine instead. |

### Clone repo (PowerShell)

```powershell
cd C:\dev   # or your preferred folder
git clone <your-repo-url> insightIQ
cd insightIQ\insightiq
```

**Git line endings (recommended once per machine):**

```powershell
git config --global core.autocrlf true
```

### Step 1 — Start Docker services (PowerShell)

Open **PowerShell** or **Windows Terminal** in `insightIQ\insightiq`:

```powershell
docker compose up -d postgres redis qdrant
docker compose ps
```

Wait until `postgres`, `redis`, and `qdrant` show **running/healthy**.

If Docker fails:

- Ensure **Docker Desktop is running** (whale icon in system tray).
- Enable **Virtualization** in BIOS and **WSL2** in Windows Features.
- Restart after first Docker Desktop install.

**Health checks (PowerShell):**

```powershell
curl.exe http://localhost:8000/healthz          # after backend starts
curl.exe http://localhost:6333/healthz          # Qdrant
docker compose exec redis redis-cli ping        # should print PONG
```

### Step 2 — Backend (PowerShell)

```powershell
cd C:\dev\insightIQ\insightiq\backend
uv sync
uv run alembic upgrade head
```

Set environment variables for **this terminal session**:

```powershell
$env:INSIGHTIQ_ENV = "dev"
$env:OPENAI_API_KEY = "sk-your-key-here"
# Optional if Redis is not running:
# $env:INSIGHTIQ_RATE_LIMIT__ENABLED = "false"
```

Start API:

```powershell
uv run uvicorn gateway.main:app --reload --host 0.0.0.0 --port 8000
```

Verify in another terminal:

```powershell
curl.exe http://localhost:8000/healthz
```

**Persist env vars (optional):** System Settings → **Environment variables**, or add to your PowerShell profile:

```powershell
notepad $PROFILE
# Add lines like: $env:OPENAI_API_KEY = "sk-..."
```

JWT keys: **not required in dev** — the app auto-generates them when `INSIGHTIQ_ENV=dev`. For stable keys across restarts:

```powershell
# Git Bash (from backend folder):
eval "$(python scripts/generate_dev_keys.py)"
# Copy the export lines into PowerShell manually as $env:INSIGHTIQ_JWT__PRIVATE_KEY_PEM = "..."
```

### Step 3 — Frontend (PowerShell, new terminal)

```powershell
cd C:\dev\insightIQ\insightiq\frontend
npm install
npm start
```

Open http://localhost:4200 in Edge/Chrome.

### Pagila sample DB on Windows

**Option A — Fresh Docker Postgres volume:** Pagila loads automatically on first `docker compose up` (init script in `ops/postgres/init/`).

**Option B — Existing Postgres volume:** use **Git Bash** (from Git for Windows):

```bash
cd /c/dev/insightIQ/insightiq
./scripts/load_pagila_sample_db.sh
```

**Option C — Manual via Docker (PowerShell):**

```powershell
cd C:\dev\insightIQ\insightiq
docker compose exec -T postgres psql -U insightiq -d insightiq -c "CREATE DATABASE pagila"
docker compose exec -T postgres psql -U insightiq -d pagila -c "SELECT 1"
# If empty, run Git Bash script above or download pagila-schema.sql / pagila-data.sql from GitHub and pipe into psql
```

In the UI: **Datasources → PostgreSQL → Use Pagila sample**  
Host `localhost`, port `5432`, database `pagila`, user/password `insightiq`.

### If you don't have Redis on Windows

| Approach | Steps |
|----------|--------|
| **Docker (easiest)** | `docker compose up -d redis` |
| **Memurai (Redis-compatible)** | https://www.memurai.com/ — Windows-native Redis alternative; use `redis://localhost:6379/0` |
| **WSL Ubuntu** | `sudo apt install redis-server` inside WSL |
| **Skip Redis** | App still runs; set `$env:INSIGHTIQ_RATE_LIMIT__ENABLED = "false"` |

Test: `docker compose exec redis redis-cli ping` or `redis-cli ping` if installed locally.

### If you don't have PostgreSQL on Windows

| Approach | Steps |
|----------|--------|
| **Docker (easiest)** | `docker compose up -d postgres` then `uv run alembic upgrade head` |
| **Native installer** | https://www.postgresql.org/download/windows/ — Stack Builder optional; create user `insightiq` / password `insightiq`, database `insightiq` |
| **Cloud** | Set `$env:INSIGHTIQ_DATABASE__URL = "postgresql+asyncpg://user:pass@host:5432/dbname"` |

After native Postgres install, ensure port **5432** is not blocked by Windows Firewall for local connections.

### Fully native Windows setup (no Docker at all)

Yes — every service InsightIQ needs has a native Windows build, so Docker Desktop is **not required**. This is a good option if you can't install Docker (BIOS virtualization disabled, corporate policy, low RAM, etc.).

| Service | Required? | Native Windows option |
|---------|-----------|------------------------|
| **PostgreSQL** | Yes | Official Windows installer |
| **Qdrant** | Yes — Talk to Docs (RAG) | Standalone `qdrant.exe` (no install needed) |
| **Redis** | Optional | [Memurai](https://www.memurai.com/) (Redis-compatible for Windows), or just skip it |
| **MinIO** | Optional — only if you want a *local* S3-compatible bucket for demos; app file uploads default to local disk | Standalone `minio.exe`, **or skip it and point at any remote S3-compatible endpoint you already have** |
| **Neo4j** | Optional — only for the Graph RAG profile | **Point at a remote/managed Neo4j instance (Aura, your own server, etc.) — no local install needed at all** |

**1. PostgreSQL** — see [§ If you don't have PostgreSQL on Windows](#if-you-dont-have-postgresql-on-windows) above, "Native installer" row. Create user/db `insightiq`/`insightiq`.

**2. Qdrant (no installer needed):**

```powershell
mkdir C:\dev\qdrant
cd C:\dev\qdrant
# Download qdrant-x86_64-pc-windows-msvc.zip from https://github.com/qdrant/qdrant/releases/latest
# Extract it here, then:
.\qdrant.exe
```

- Requires the [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) (install it if `qdrant.exe` closes instantly with no error).
- Don't double-click `qdrant.exe` in Explorer — always launch it from a PowerShell/terminal window so it stays attached and you can see logs.
- Always launch it from the **same folder** so it reuses the same `./storage` data directory (or set `$env:QDRANT__STORAGE__STORAGE_PATH` explicitly).
- Verify: `curl.exe http://localhost:6333/healthz`.
- To run it in the background permanently, wrap it as a Windows service with [NSSM](https://nssm.cc/) or [WinSW](https://github.com/winsw/winsw), or just leave a terminal tab open for local dev.

**3. Redis (optional):**

- Easiest: install [Memurai Developer Edition](https://www.memurai.com/get-memurai) (free), which listens on `localhost:6379` just like Redis — no code changes needed.
- Or skip it entirely: `$env:INSIGHTIQ_RATE_LIMIT__ENABLED = "false"`. Rate limiting and the event bus are the only things that use Redis; login, Talk to Data, and Talk to Docs all work without it.

**4. S3 / MinIO (optional, only relevant to the `s3_object_store` datasource type):**

The S3 connector (`insightiq/backend/core/data/connectors/s3_object_store.py`) is a thin wrapper around DuckDB's `httpfs` extension — it talks to **any S3-compatible endpoint**, not specifically MinIO. When you add an S3 datasource in the UI you fill in `endpoint`, `region`, `access_key`, `secret_key`, and `url_style`, so:

- **Already have a bucket** (real AWS S3, Cloudflare R2, Backblaze B2, DigitalOcean Spaces, or a MinIO/other S3 server running elsewhere)? **You don't need MinIO at all.** Just point `endpoint` at that service (e.g. `s3.amazonaws.com` for AWS, `us-east-1` region, `url_style: vhost`) and use its real access/secret keys.
- **Want a free local bucket for demos** with no cloud account? Then run MinIO — yes, it's available on Windows as a plain `.exe`, no Docker needed:

  ```powershell
  mkdir C:\dev\minio-data
  # Download https://dl.min.io/server/minio/release/windows-amd64/minio.exe into C:\dev\minio
  cd C:\dev\minio
  .\minio.exe server C:\dev\minio-data --console-address ":9001"
  ```

  Default credentials are `minioadmin` / `minioadmin`; console is at http://localhost:9001. In the datasource form, use `endpoint: localhost:9000`, `url_style: path`.

**5. Neo4j (optional, only for the Graph RAG profile):** if you already have a remote or managed Neo4j instance (e.g. [Neo4j Aura](https://neo4j.com/product/auradb/), a server elsewhere, or one running for another project), just point the backend at it — **no local install required**:

```powershell
$env:INSIGHTIQ_NEO4J__URI = "bolt://your-remote-host:7687"   # or "neo4j+s://xxxx.databases.neo4j.io" for Aura
$env:INSIGHTIQ_NEO4J__USERNAME = "neo4j"
$env:INSIGHTIQ_NEO4J__PASSWORD = "your-password"
```

Only install **Neo4j Desktop** locally if you don't already have a remote instance to use.

**6. Backend and frontend** — identical to [§ Step 2 — Backend](#step-2--backend-powershell) and [§ Step 3 — Frontend](#step-3--frontend-powershell-new-terminal) above; `uv` and `npm` already run natively on Windows, Docker was only ever used for the infra containers.

With Postgres and Qdrant running natively and `INSIGHTIQ_RATE_LIMIT__ENABLED=false` (if skipping Redis), you have a fully Docker-free InsightIQ dev environment on Windows.

### Windows troubleshooting

| Symptom | Fix |
|---------|-----|
| `docker` not recognized | Install/start Docker Desktop; reopen terminal |
| Port 5432/6379/6333 in use | Stop local Postgres/Redis services or change ports in `docker-compose.yml` |
| `uv` not recognized | Reopen terminal after uv install; check `%USERPROFILE%\.local\bin` or uv docs |
| `python` not found | Reinstall Python with **Add to PATH**; try `py -3.12` instead |
| npm scripts fail on paths | Avoid spaces in clone path (e.g. not `C:\Users\You\My Projects\`) |
| Pagila script won't run | Use **Git Bash**, not cmd.exe — or use Docker manual steps above |
| Backend can't reach Docker DB | Use `localhost`, not `127.0.0.1` issues — try both; ensure Docker publishes ports |
| CORS / login works but API fails | Windows Defender Firewall — allow Python/uvicorn on private network |
| Slow file watching on frontend | Normal on Windows; `ng serve` still works; WSL2 can be faster for large repos |

### Windows daily workflow (three terminals)

```powershell
# Terminal 1 — infra
cd C:\dev\insightIQ\insightiq
docker compose up -d postgres redis qdrant

# Terminal 2 — backend
cd C:\dev\insightIQ\insightiq\backend
$env:OPENAI_API_KEY = "sk-..."
uv run uvicorn gateway.main:app --reload --port 8000

# Terminal 3 — frontend
cd C:\dev\insightIQ\insightiq\frontend
npm start
```

### Using WSL2 instead (optional)

Many teams run the **Linux flow** inside WSL2 Ubuntu:

1. Install WSL: `wsl --install` (reboot)
2. Clone repo inside Linux home: `~/insightIQ`
3. Install Docker Desktop → Settings → Resources → WSL integration → enable your distro
4. Follow **§4 Recommended setup** bash commands from inside WSL

Code in `/mnt/c/...` is slower — prefer cloning under `~/` in WSL.

---

## 3. Clone the repository

```bash
git clone <your-repo-url> insightIQ
cd insightIQ
```

All commands below assume you are in the **`insightIQ/insightiq/`** directory unless noted.

---

## 4. Recommended setup (Docker for infrastructure)

This is the path most developers should follow.

### Step 1 — Start infrastructure

```bash
cd insightiq
docker compose up -d
```

Wait until core services are healthy:

```bash
docker compose ps
```

**Minimum services for the product to work:**

| Service | Port | Required? |
|---------|------|-----------|
| **postgres** | 5432 | **Yes** — app database |
| **qdrant** | 6333 | **Yes** — Talk to Docs RAG |
| **redis** | 6379 | Recommended (see §6) |
| **minio** | 9000 / 9001 | Optional — S3/MinIO datasource demos |
| neo4j | 7474 / 7687 | Optional — graph RAG profile |
| jaeger, prometheus, grafana, vault, loki | various | Optional — ops/dev only |

Default Postgres credentials (from `docker-compose.yml`):

| Setting | Value |
|---------|-------|
| Host | `localhost` |
| Port | `5432` |
| Database | `insightiq` |
| User | `insightiq` |
| Password | `insightiq` |

**Pagila sample DB (Talk to Data demos):** loads automatically on a **fresh** Postgres Docker volume. If you already had a Postgres volume before Pagila was added, run:

```bash
chmod +x scripts/load_pagila_sample_db.sh
./scripts/load_pagila_sample_db.sh
```

Pagila connection: database **`pagila`**, same user/password **`insightiq`**.

### Step 2 — Backend

```bash
cd backend
uv sync
```

Run database migrations:

```bash
uv run alembic upgrade head
```

JWT keys (optional in dev — the app auto-generates ephemeral keys when `INSIGHTIQ_ENV=dev`):

```bash
eval "$(python scripts/generate_dev_keys.py)"
```

Start the API:

```bash
uv run uvicorn gateway.main:app --reload --host 0.0.0.0 --port 8000
```

Verify:

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

### Step 3 — Frontend

New terminal:

```bash
cd insightiq/frontend
npm install
npm start
```

Open:

| URL | Purpose |
|-----|---------|
| http://localhost:4200 | Web UI |
| http://localhost:8000/docs | Swagger API docs |

### Step 4 — First login

1. Go to http://localhost:4200/login  
2. **Create account** (register) — creates tenant + user  
3. **Datasources** → add Postgres (or use **Use Pagila sample**)  
4. **Talk to Data** / **Talk to Docs** — start chatting  

**Talk to Docs extras (after migration `0012`):**

- **Document versioning** — re-uploading the same filename in a collection creates a new version; only the current version is searched. Identical file content (SHA-256) is skipped.
- **Collection admin** — in Talk to Docs, select a collection → **Admin** tab: overview stats, document versions/metadata, chunk browser.
- **Citation preview** — click a reference or **View in document**; toggle **Extracted text** (indexed markdown) vs **Original document** (PDF canvas with bbox highlights, or Word HTML highlight) when the original file was stored at upload.
- **Raw vector inspection** — Qdrant dashboard at http://localhost:6333/dashboard (collections named `insightiq_docs_*`).

Ensure `OPENAI_API_KEY` is set in the same shell (or systemd env) where uvicorn runs, or LLM features will fall back to heuristics / error messages.

---

## 5. Environment variables (reference)

All backend settings use prefix **`INSIGHTIQ_`** and nested **`__`**.

| Variable | Default | Notes |
|----------|---------|-------|
| `INSIGHTIQ_ENV` | `dev` | In dev, auth can be relaxed; JWT keys auto-generated if missing |
| `INSIGHTIQ_DATABASE__URL` | `postgresql+asyncpg://insightiq:insightiq@localhost:5432/insightiq` | App metadata DB — PostgreSQL (default) or SQLite |
| `INSIGHTIQ_REDIS__URL` | `redis://localhost:6379/0` | See §6 if Redis unavailable |
| `INSIGHTIQ_QDRANT__URL` | `http://localhost:6333` | Required for Talk to Docs |
| `INSIGHTIQ_JWT__PRIVATE_KEY_PEM` | auto in dev | Use `generate_dev_keys.py` for stable keys across restarts |
| `INSIGHTIQ_JWT__PUBLIC_KEY_PEM` | auto in dev | Pair with private key |
| `INSIGHTIQ_RATE_LIMIT__ENABLED` | `true` | Set `false` if Redis is down and you hit issues |
| `INSIGHTIQ_TELEMETRY__ENABLED` | `true` | Set `false` if Jaeger/OTLP not running |

Example `.env` snippet (export manually or use direnv):

```bash
export INSIGHTIQ_ENV=dev
export INSIGHTIQ_DATABASE__URL="postgresql+asyncpg://insightiq:insightiq@localhost:5432/insightiq"
export INSIGHTIQ_REDIS__URL="redis://localhost:6379/0"
export INSIGHTIQ_QDRANT__URL="http://localhost:6333"
export OPENAI_API_KEY="sk-..."
```

Frontend API URL: edit `frontend/src/app/core/api.config.ts` if the gateway is not on `http://localhost:8000`.

### SQLite instead of PostgreSQL (local dev)

If you do not have PostgreSQL, the app metadata database can run on **SQLite** via the async driver:

```bash
export INSIGHTIQ_DATABASE__URL="sqlite+aiosqlite:///./insightiq.dev.db"
cd insightiq/backend
uv run alembic upgrade head
uv run uvicorn gateway.main:app --reload --port 8000
```

Notes:

- PostgreSQL remains the recommended choice for production and team deployments.
- SQLite uses the same SQLAlchemy models and Alembic migrations (portable UUID/JSON types).
- Qdrant, Redis, and Neo4j are still required for full Talk to Docs / GraphRAG features — only the **app DB** can be SQLite.
- Use `sqlite+aiosqlite:///:memory:` in tests for an ephemeral database.

---

## 6. If you don't have Redis

### Option A — Use Docker (recommended)

```bash
cd insightiq
docker compose up -d redis
```

Or start only infra you need:

```bash
docker compose up -d postgres redis qdrant
```

### Option B — Install Redis locally

**macOS:**

```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian:**

```bash
sudo apt update && sudo apt install -y redis-server
sudo systemctl enable --now redis-server
```

**Verify:** `redis-cli ping` → `PONG`

Point the app at it (default already correct):

```bash
export INSIGHTIQ_REDIS__URL="redis://localhost:6379/0"
```

### Option C — Run without Redis

The gateway **starts without Redis**. When Redis is unavailable:

- **Rate limiting** is skipped (requests still work)
- **Event bus** degrades to no-op (see `core/events/bus.py`)

To avoid connection noise, you can disable rate limiting:

```bash
export INSIGHTIQ_RATE_LIMIT__ENABLED=false
```

You do **not** need Redis for basic login, Talk to Data SQL, or Talk to Docs RAG.

---

## 7. If you don't have PostgreSQL

PostgreSQL is **required**. The app stores users, tenants, conversations, datasources, documents metadata, dashboards, and prompts there.

### Option A — Use Docker (recommended)

```bash
cd insightiq
docker compose up -d postgres
# wait for healthy
docker compose exec postgres pg_isready -U insightiq -d insightiq
```

Then run migrations:

```bash
cd backend && uv run alembic upgrade head
```

### Option B — Install PostgreSQL locally

**macOS:**

```bash
brew install postgresql@16
brew services start postgresql@16
createuser -s insightiq || true
psql postgres -c "ALTER USER insightiq WITH PASSWORD 'insightiq';"
createdb -O insightiq insightiq
```

**Ubuntu/Debian:**

```bash
sudo apt install -y postgresql postgresql-contrib
sudo -u postgres createuser -s insightiq
sudo -u postgres psql -c "ALTER USER insightiq WITH PASSWORD 'insightiq';"
sudo -u postgres createdb -O insightiq insightiq
```

Set the connection URL:

```bash
export INSIGHTIQ_DATABASE__URL="postgresql+asyncpg://insightiq:insightiq@localhost:5432/insightiq"
cd insightiq/backend && uv run alembic upgrade head
```

### Option C — Use a cloud Postgres

Any Postgres 14+ with async access works. Set `INSIGHTIQ_DATABASE__URL` to your provider's connection string (use `postgresql+asyncpg://...` scheme).

---

## 8. If you don't have Qdrant

**Talk to Docs requires Qdrant** for vector search.

```bash
cd insightiq
docker compose up -d qdrant
curl http://localhost:6333/healthz
```

Without Qdrant, document ingestion and RAG chat will fail when searching embeddings.

---

## 9. Minimal Docker profiles

Start only what you need to save RAM:

```bash
# Core product (Postgres + Redis + Qdrant)
docker compose up -d postgres redis qdrant

# Add object storage demos
docker compose up -d minio

# Full stack including observability
docker compose up -d
```

---

## 10. Python dependencies

Installed automatically by `uv sync` from `backend/pyproject.toml`.

**Core stack:** FastAPI, SQLAlchemy (async), Alembic, LangGraph, Qdrant client, Redis, OpenAI SDK, DuckDB, document extractors (MarkItDown, PyMuPDF), etc.

**Enterprise database connectors (optional):**

```bash
cd insightiq/backend
uv sync --extra connectors
```

Adds: pymssql, oracledb, snowflake-connector-python, PyHive, google-cloud-bigquery.

**OCR for scanned PDFs (optional):**

```bash
cd insightiq/backend
uv sync --extra ocr
```

Adds: RapidOCR + ONNX Runtime — pure pip, no system Tesseract install required (see [§ 2. Prerequisites](#2-prerequisites)).

---

## 11. Frontend dependencies

Installed by `npm install` from `frontend/package.json`.

**Key libraries:** Angular 18, Gridster (dashboards), Marked + Mermaid (markdown answers), DOMPurify, pdfjs-dist + mammoth (original PDF/Word citation preview).

**Build for production:**

```bash
cd insightiq/frontend
npm ci
npm run build
# output: dist/insightiq/
```

---

## 12. Verification checklist

Run after setup:

```bash
# Infrastructure
docker compose ps                    # postgres, redis, qdrant Up
curl -s http://localhost:6333/healthz
redis-cli ping                       # PONG (if local/docker redis)

# Backend
curl -s http://localhost:8000/healthz
cd insightiq/backend && uv run pytest tests/ -q

# Frontend
cd insightiq/frontend && npm run build
```

Manual UI checks:

- [ ] Register / login at http://localhost:4200  
- [ ] Add or select a datasource (Pagila sample)  
- [ ] Ask a question in **Talk to Data**  
- [ ] Create a collection, upload a PDF, ask in **Talk to Docs**  
- [ ] Open **Admin** on a collection — verify document list, version badges, chunk browser  
- [ ] Click a citation → switch **Original document** — PDF page highlight or Word excerpt highlight  

---

## 12.1 Talk to Docs — versioning, metadata, and admin

After `uv run alembic upgrade head` (migration `0012_document_versioning`), Talk to Docs stores enterprise metadata and supports document versions.

### Versioning behavior

| Event | Result |
|-------|--------|
| First upload of `report.pdf` | Version 1, `is_current=true`, indexed in Qdrant |
| Re-upload same filename, new content | Old version superseded (`is_current=false`); new version indexed; search uses current only |
| Re-upload identical bytes (same SHA-256) | Skipped — no duplicate index |

Original files are kept on disk under `uploads/{tenant_id}/{collection_id}/` and linked from Postgres (`documents.storage_path`).

### Enterprise metadata (`metadata_json`)

Each document stores structured fields including: `document_type`, `tags`, `source`, `extractor_used`, `confidence`, `graph_sync_status`, `version_number`, `content_hash`, `mime_type`, `file_size_bytes`, `page_count`, `indexed_at`, and `confidentiality` (default `internal`). Optional upload fields: **Document type** and **Tags** in the sidebar.

### Admin UI

In **Talk to Docs**, select a collection → **Admin**:

- **Overview** — document/chunk counts, embedding model, vector estimate  
- **Documents** — all versions, status, hash, size, metadata; expand **Version history** per registry  
- **Chunks** — searchable chunk list with page, char offsets, Qdrant point id, bbox/highlight metadata  

REST endpoints (Swagger: `/docs`): `GET /talk-to-docs/collections/{id}/admin/summary`, `.../admin/documents`, `.../admin/chunks`, `GET /talk-to-docs/documents/registry/{registry_id}/versions`.

### Citation preview modes

When answering, citations include `view_modes`:

- **`extracted`** — markdown text from the vector index (default)  
- **`original_pdf`** / **`original_word`** — rendered original file with highlights when stored at upload  

PDF highlights use bounding boxes from PyMuPDF structured extraction. Word highlights match the cited text snippet in converted HTML.

For low-level vector/payload inspection, use the **Qdrant dashboard**: http://localhost:6333/dashboard

---

## 13. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `connection refused` on 5432 | Start Postgres: `docker compose up -d postgres` |
| Alembic migration fails | DB reachable? URL correct? User can create tables? |
| 401 on all API calls | Clear browser `localStorage`; re-login; check JWT env in non-dev |
| Talk to Docs empty / errors | Qdrant running? Documents ingested? Run `uv run alembic upgrade head` for versioning schema |
| Scrape fails at indexing | Large sites (e.g. docs.crewai.com × 100 pages) need the web-scrape chunker (auto). Ensure Qdrant is up; check job error for the failing URL. Run `uv run alembic upgrade head` if DB columns are missing |
| Original preview unavailable | Re-upload PDF/DOCX after upgrade so `storage_path` is populated; only file uploads store originals |
| LLM "not available" | Set `OPENAI_API_KEY`; restart uvicorn |
| Rate limit 429 | Start Redis or set `INSIGHTIQ_RATE_LIMIT__ENABLED=false` |
| Pagila not found | Run `./scripts/load_pagila_sample_db.sh` (Git Bash on Windows) — see **§ Windows setup** |
| Port already in use | Change ports in `docker-compose.yml` or stop conflicting services |
| CORS errors from frontend | Gateway allows `http://localhost:4200` by default (`gateway/main.py`) |
| Windows: Docker/WSL issues | See **§ Windows setup** troubleshooting table |

---

## 14. Daily dev workflow

```bash
# Terminal 1 — infra (once per reboot)
cd insightiq && docker compose up -d postgres redis qdrant

# Terminal 2 — backend
cd insightiq/backend
export OPENAI_API_KEY="sk-..."
uv run uvicorn gateway.main:app --reload --port 8000

# Terminal 3 — frontend
cd insightiq/frontend && npm start
```

---

## 15. Related docs

- [DEPLOYMENT.md](./DEPLOYMENT.md) — production topology, secrets, scaling  
- [README.md](../README.md) — feature overview and quick start  
- [CURSOR BUILD PROMPT.md](../CURSOR%20BUILD%20PROMPT.md) — architecture & build spec  
