from __future__ import annotations

from typing import Any


def format_response_text(response: dict[str, Any] | None, *, max_rows: int = 100) -> str:
    """Plain-text rendering of a dashboard card response payload."""
    if not response:
        return ""

    data = response.get("data") or {}
    rtype = str(response.get("response_type", ""))

    if rtype == "data_table":
        cols = [str(c) for c in (data.get("columns") or [])]
        rows = data.get("rows") or []
        if not cols:
            return "Empty table"
        header = " | ".join(cols)
        sep = "-+-".join("-" * max(len(c), 3) for c in cols)
        body = [" | ".join(str(cell) for cell in row) for row in rows[:max_rows]]
        if len(rows) > max_rows:
            body.append(f"... {len(rows) - max_rows} more rows")
        return "\n".join([header, sep, *body])

    if rtype == "kpi_card":
        label = data.get("label", "Value")
        value = data.get("value", "")
        return f"{label}: {value}"

    if rtype == "chart_bar":
        labels = data.get("labels") or []
        values = data.get("values") or []
        lines = [f"{label}: {value}" for label, value in zip(labels, values, strict=False)]
        return "\n".join(lines) if lines else "Empty chart"

    if rtype == "explanation":
        return str(data.get("output", ""))

    if rtype == "error":
        return str(data.get("message", ""))

    title = response.get("title")
    if title:
        return str(title)
    return rtype or "Card"


def response_table_matrix(response: dict[str, Any] | None) -> list[list[str]] | None:
    """Return header + rows for tabular PDF/PPT rendering, or None if not tabular."""
    if not response:
        return None

    data = response.get("data") or {}
    rtype = str(response.get("response_type", ""))

    if rtype == "data_table":
        cols = [str(c) for c in (data.get("columns") or [])]
        rows = data.get("rows") or []
        if not cols:
            return None
        return [cols, *[[str(cell) for cell in row] for row in rows]]

    if rtype == "chart_bar":
        labels = data.get("labels") or []
        values = data.get("values") or []
        if not labels:
            return None
        return [["Category", "Value"], *[[str(label), str(value)] for label, value in zip(labels, values, strict=False)]]

    return None
