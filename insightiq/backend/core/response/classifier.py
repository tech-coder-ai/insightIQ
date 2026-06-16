from __future__ import annotations

from core.data.connectors.base import QueryResult
from core.response.formatter import (
    format_chart_bar,
    format_data_table,
    format_kpi_card,
)
from core.response.types import ResponsePayload


def classify_and_format(result: QueryResult, *, question: str) -> ResponsePayload:
    q = question.lower()
    if len(result.columns) == 1 and len(result.rows) == 1:
        value = result.rows[0][0]
        label = result.columns[0]
        return format_kpi_card(label=label, value=value, title=question)

    chart_keywords = ("chart", "graph", "plot", "by region", "by category", "breakdown", "trend")
    if any(k in q for k in chart_keywords) and len(result.columns) >= 2 and result.rows:
        labels = [str(row[0]) for row in result.rows]
        values = [row[1] for row in result.rows]
        return format_chart_bar(title=question, labels=labels, values=values)

    return format_data_table(result, title=question)
