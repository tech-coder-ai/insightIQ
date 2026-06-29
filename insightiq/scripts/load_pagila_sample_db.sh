#!/usr/bin/env bash
# Load Pagila sample DB into the local InsightIQ Postgres (docker compose or localhost).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAGILA_BASE="https://raw.githubusercontent.com/devrimgunduz/pagila/master"

PGUSER="${PGUSER:-insightiq}"
PGPASSWORD="${PGPASSWORD:-insightiq}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
MAINT_DB="${PGMAINTDB:-insightiq}"

run_psql() {
  if command -v docker >/dev/null 2>&1 && docker compose -f "${ROOT}/docker-compose.yml" ps postgres 2>/dev/null | grep -qE 'Up|running'; then
    docker compose -f "${ROOT}/docker-compose.yml" exec -T -e PGPASSWORD="${PGPASSWORD}" postgres \
      psql -v ON_ERROR_STOP=1 -U "${PGUSER}" "$@"
  else
    PGPASSWORD="${PGPASSWORD}" psql -v ON_ERROR_STOP=1 -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" "$@"
  fi
}

if run_psql -d pagila -tAc "SELECT 1 FROM information_schema.tables WHERE table_name = 'film' LIMIT 1" 2>/dev/null | grep -q 1; then
  echo "✓ Pagila already loaded (database: pagila)."
  exit 0
fi

echo "→ Creating database pagila (if missing)…"
run_psql -d "${MAINT_DB}" -c "CREATE DATABASE pagila" >/dev/null 2>&1 || true

echo "→ Ensuring postgres role (required by Pagila dump)…"
run_psql -d "${MAINT_DB}" -c "DO \$\$ BEGIN CREATE ROLE postgres WITH SUPERUSER LOGIN PASSWORD 'insightiq'; EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;"

echo "→ Downloading Pagila schema…"
curl -fsSL "${PAGILA_BASE}/pagila-schema.sql" | run_psql -d pagila

echo "→ Downloading Pagila data (~16k rentals, 2k films)…"
curl -fsSL "${PAGILA_BASE}/pagila-data.sql" | run_psql -d pagila

echo ""
echo "✓ Pagila sample database loaded."
echo "  Host: ${PGHOST}  Port: ${PGPORT}  Database: pagila"
echo "  User: ${PGUSER}  Password: ${PGPASSWORD}"
echo ""
echo "Register in InsightIQ → Datasources → PostgreSQL, or click 'Use Pagila sample' in the UI."
