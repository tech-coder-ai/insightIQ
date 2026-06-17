from __future__ import annotations

from typing import Any

from core.data.connectors.base import QueryResult
from core.response.types import ResponsePayload, ResponseType


def format_data_table(result: QueryResult, *, title: str | None = None) -> ResponsePayload:
    return ResponsePayload(
        response_type=ResponseType.data_table,
        title=title,
        data={"columns": result.columns, "rows": result.rows},
    )


def format_kpi_card(*, label: str, value: Any, title: str | None = None) -> ResponsePayload:
    return ResponsePayload(
        response_type=ResponseType.kpi_card,
        title=title,
        data={"label": label, "value": value},
    )


def format_chart_bar(*, title: str, labels: list[str], values: list[Any]) -> ResponsePayload:
    return ResponsePayload(
        response_type=ResponseType.chart_bar,
        title=title,
        data={"labels": labels, "values": values},
    )


def format_chart_line(*, title: str, labels: list[str], values: list[Any]) -> ResponsePayload:
    return ResponsePayload(
        response_type=ResponseType.chart_line,
        title=title,
        data={"labels": labels, "values": values},
    )


def format_explanation(*, output: str, title: str | None = None) -> ResponsePayload:
    return ResponsePayload(
        response_type=ResponseType.explanation,
        title=title,
        data={"output": output},
    )


def format_error(message: str) -> ResponsePayload:
    return ResponsePayload(response_type=ResponseType.error, data={"message": message})
