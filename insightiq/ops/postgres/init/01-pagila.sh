#!/bin/bash
# Load Pagila (PostgreSQL port of Sakila) on first Postgres container init.
set -euo pipefail

PAGILA_BASE="https://raw.githubusercontent.com/devrimgunduz/pagila/master"

echo "Creating Pagila sample database…"
psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE pagila" >/dev/null 2>&1 || true

# Pagila dumps reference the default "postgres" role for object ownership.
psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
DO $$ BEGIN
  CREATE ROLE postgres WITH SUPERUSER LOGIN PASSWORD 'insightiq';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
EOSQL

echo "Loading Pagila schema…"
curl -fsSL "${PAGILA_BASE}/pagila-schema.sql" | psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pagila

echo "Loading Pagila data (this may take a minute)…"
curl -fsSL "${PAGILA_BASE}/pagila-data.sql" | psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname pagila

echo "Pagila sample database ready (database: pagila, user: ${POSTGRES_USER})."
