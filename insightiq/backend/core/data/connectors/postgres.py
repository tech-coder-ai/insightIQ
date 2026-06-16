from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.data.connectors.base import IDBConnector, QueryResult, ValidationResult
from core.data.connectors.factory import CONNECTORS
from core.data.normalize import json_safe_row
from core.data.schema import ColumnMeta, IndexMeta, RelationshipMeta, SchemaMetadata, TableMeta
from core.data.validators.factory import ValidatorFactory
from core.data.validators.readonly import check_readonly_select


@CONNECTORS.register("postgres")
class PostgresConnector(IDBConnector):
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def test_connection(self) -> bool:
        await self._session.execute(text("SELECT 1"))
        return True

    async def introspect_schema(self) -> SchemaMetadata:
        tables_res = await self._session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        )
        table_names = [row[0] for row in tables_res.fetchall()]

        primary_keys = await self._introspect_primary_keys()
        indexes_by_table = await self._introspect_indexes()
        relationships = await self._introspect_relationships()
        indexed_columns: dict[str, set[str]] = {}
        for tbl, idxs in indexes_by_table.items():
            cols: set[str] = set()
            for idx in idxs:
                cols.update(idx.columns)
            indexed_columns[tbl] = cols

        tables: list[TableMeta] = []
        for table_name in table_names:
            cols_res = await self._session.execute(
                text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table "
                    "ORDER BY ordinal_position"
                ),
                {"table": table_name},
            )
            pk_cols = primary_keys.get(table_name, set())
            idx_cols = indexed_columns.get(table_name, set())
            columns = [
                ColumnMeta(
                    name=row[0],
                    data_type=row[1],
                    nullable=row[2] == "YES",
                    is_primary_key=row[0] in pk_cols,
                    is_indexed=row[0] in idx_cols or row[0] in pk_cols,
                )
                for row in cols_res.fetchall()
            ]
            tables.append(
                TableMeta(
                    name=table_name,
                    columns=columns,
                    indexes=indexes_by_table.get(table_name, []),
                )
            )
        return SchemaMetadata(tables=tables, relationships=relationships)

    async def _introspect_primary_keys(self) -> dict[str, set[str]]:
        res = await self._session.execute(
            text(
                "SELECT tc.table_name, kcu.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "  AND tc.table_schema = kcu.table_schema "
                "WHERE tc.constraint_type = 'PRIMARY KEY' "
                "  AND tc.table_schema = 'public'"
            )
        )
        out: dict[str, set[str]] = {}
        for table_name, column_name in res.fetchall():
            out.setdefault(table_name, set()).add(column_name)
        return out

    async def _introspect_indexes(self) -> dict[str, list[IndexMeta]]:
        res = await self._session.execute(
            text(
                "SELECT t.relname AS table_name, i.relname AS index_name, "
                "       a.attname AS column_name, ix.indisunique AS is_unique "
                "FROM pg_class t "
                "JOIN pg_index ix ON t.oid = ix.indrelid "
                "JOIN pg_class i ON i.oid = ix.indexrelid "
                "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey) "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE t.relkind = 'r' AND n.nspname = 'public' "
                "ORDER BY t.relname, i.relname"
            )
        )
        # (table, index) -> IndexMeta
        accum: dict[tuple[str, str], IndexMeta] = {}
        for table_name, index_name, column_name, is_unique in res.fetchall():
            key = (table_name, index_name)
            if key not in accum:
                accum[key] = IndexMeta(name=index_name, columns=[], unique=bool(is_unique))
            accum[key].columns.append(column_name)
        out: dict[str, list[IndexMeta]] = {}
        for (table_name, _index_name), idx in accum.items():
            out.setdefault(table_name, []).append(idx)
        return out

    async def _introspect_relationships(self) -> list[RelationshipMeta]:
        res = await self._session.execute(
            text(
                "SELECT tc.table_name AS from_table, kcu.column_name AS from_column, "
                "       ccu.table_name AS to_table, ccu.column_name AS to_column "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "  AND tc.table_schema = kcu.table_schema "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON ccu.constraint_name = tc.constraint_name "
                "  AND ccu.table_schema = tc.table_schema "
                "WHERE tc.constraint_type = 'FOREIGN KEY' "
                "  AND tc.table_schema = 'public'"
            )
        )
        return [
            RelationshipMeta(
                from_table=row[0],
                from_column=row[1],
                to_table=row[2],
                to_column=row[3],
                source="introspected",
            )
            for row in res.fetchall()
        ]

    async def validate_sql(self, sql: str) -> ValidationResult:
        validator = ValidatorFactory.create("postgres", session=self._session)
        res = await validator.validate(sql)
        return ValidationResult(ok=res.ok, error=res.error)

    async def execute_query(self, sql: str) -> QueryResult:
        guard = check_readonly_select(sql)
        if not guard.ok:
            raise ValueError(guard.error or "destructive SQL is not allowed")
        result = await self._session.execute(text(sql))
        rows = result.fetchall()
        cols = list(result.keys())
        return QueryResult(columns=cols, rows=[json_safe_row(list(r)) for r in rows])
