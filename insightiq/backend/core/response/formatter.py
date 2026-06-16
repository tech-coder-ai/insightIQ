from __future__ import annotations

from core.data.connectors.base import QueryResult
from core.response.types import ResponsePayload, ResponseType


def format_data_table(result: QueryResult, *, title: str | None = None) -> ResponsePayload:
    return ResponsePayload(
        response_type=ResponseType.data_table,
        title=title,
        data={"columns": result.columns, "rows": result.rows},
    )


def format_error(message: str) -> ResponsePayload:
    return ResponsePayload(response_type=ResponseType.error, data={"message": message})
