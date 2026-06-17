from __future__ import annotations

from core.data.connectors.base import QueryResult
from core.response.display import (
    format_chart_label,
    format_table_cell,
    is_chart_question,
    is_line_chart_question,
)
from core.response.formatter import (
    format_chart_bar,
    format_chart_line,
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

    if is_chart_question(q) and len(result.columns) >= 2 and result.rows:
        labels = [format_chart_label(row[0], question=question) for row in result.rows]
        values = [row[1] for row in result.rows]
        if is_line_chart_question(q):
            return format_chart_line(title=question, labels=labels, values=values)
        return format_chart_bar(title=question, labels=labels, values=values)

    payload = format_data_table(result, title=question)
    payload.data["rows"] = [
        [format_table_cell(cell, column_index=i, question=question) for i, cell in enumerate(row)]
        for row in result.rows
    ]
    return payload
