from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.data.connectors.base import IDBConnector, QueryResult, ValidationResult
from core.data.connectors.factory import CONNECTORS
from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta
from core.data.validators.factory import ValidatorFactory


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
        tables: list[TableMeta] = []
        for (table_name,) in tables_res.fetchall():
            cols_res = await self._session.execute(
                text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table "
                    "ORDER BY ordinal_position"
                ),
                {"table": table_name},
            )
            columns = [
                ColumnMeta(name=row[0], data_type=row[1], nullable=row[2] == "YES")
                for row in cols_res.fetchall()
            ]
            tables.append(TableMeta(name=table_name, columns=columns))
        return SchemaMetadata(tables=tables)

    async def validate_sql(self, sql: str) -> ValidationResult:
        validator = ValidatorFactory.create("postgres", session=self._session)
        res = await validator.validate(sql)
        return ValidationResult(ok=res.ok, error=res.error)

    async def execute_query(self, sql: str) -> QueryResult:
        result = await self._session.execute(text(sql))
        rows = result.fetchall()
        cols = list(result.keys())
        return QueryResult(columns=cols, rows=[list(r) for r in rows])
