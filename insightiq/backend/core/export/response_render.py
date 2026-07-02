from __future__ import annotations

import re
from typing import Any

_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize_filename(name: str, *, max_length: int = 60, default: str = "export") -> str:
    """Produce a filesystem/HTTP-header-safe filename stem (no extension)."""
    stem = _FILENAME_UNSAFE.sub("_", name.strip()).strip("_.")
    stem = re.sub(r"_+", "_", stem)
    if not stem:
        stem = default
    return stem[:max_length]


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

    if rtype in ("chart_bar", "chart_line", "chart_pie"):
        labels = data.get("labels") or []
        values = data.get("values") or []
        lines = [f"{label}: {value}" for label, value in zip(labels, values, strict=False)]
        return "\n".join(lines) if lines else "Empty chart"

    if rtype == "chart_scatter":
        points = _scatter_points(data)
        if not points:
            return "Empty chart"
        return "\n".join(f"({x:g}, {y:g})" for x, y in points)

    if rtype in ("multi_panel", "combined"):
        parts = []
        for panel in iter_sub_panels(response) or []:
            title = panel.get("title") or panel.get("response_type", "Panel")
            parts.append(f"{title}\n{format_response_text(panel, max_rows=max_rows)}")
        return "\n\n".join(parts) if parts else "No panels"

    if rtype == "explanation":
        return str(data.get("output", ""))

    if rtype == "error":
        return str(data.get("message", ""))

    title = response.get("title")
    if title:
        return str(title)
    return rtype or "Card"


def response_table_matrix(response: dict[str, Any] | None, *, max_rows: int = 200) -> list[list[str]] | None:
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
        matrix = [cols, *[[str(cell) for cell in row] for row in rows[:max_rows]]]
        if len(rows) > max_rows:
            matrix.append([f"+{len(rows) - max_rows} more rows", *["" for _ in cols[1:]]])
        return matrix

    if rtype == "chart_bar":
        labels = data.get("labels") or []
        values = data.get("values") or []
        if not labels:
            return None
        return [["Category", "Value"], *[[str(label), str(value)] for label, value in zip(labels, values, strict=False)]]

    return None


_CHART_KINDS = {"chart_bar": "bar", "chart_line": "line", "chart_pie": "pie"}


def response_chart_spec(response: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize labels/values charts into a {kind, labels, values} spec for native chart rendering."""
    if not response:
        return None
    rtype = str(response.get("response_type", ""))
    kind = _CHART_KINDS.get(rtype)
    if not kind:
        return None
    data = response.get("data") or {}
    labels = [str(lbl) for lbl in (data.get("labels") or [])]
    raw_values = data.get("values") or []
    values: list[float] = []
    for v in raw_values:
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            values.append(0.0)
    if not labels or not values:
        return None
    return {"kind": kind, "labels": labels, "values": values, "title": response.get("title") or ""}


def _scatter_points(data: dict[str, Any]) -> list[tuple[float, float]]:
    raw_points = data.get("points")
    points: list[tuple[float, float]] = []
    if isinstance(raw_points, list):
        for p in raw_points:
            try:
                points.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError, IndexError):
                continue
        return points
    xs = data.get("x") or []
    ys = data.get("y") or []
    for x, y in zip(xs, ys, strict=False):
        try:
            points.append((float(x), float(y)))
        except (TypeError, ValueError):
            continue
    return points


def response_scatter_spec(response: dict[str, Any] | None) -> dict[str, Any] | None:
    if not response or str(response.get("response_type", "")) != "chart_scatter":
        return None
    data = response.get("data") or {}
    points = _scatter_points(data)
    if not points:
        return None
    return {"kind": "scatter", "points": points, "title": response.get("title") or ""}


def iter_sub_panels(response: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """For multi_panel/combined responses, return the list of nested response payloads."""
    if not response:
        return None
    rtype = str(response.get("response_type", ""))
    if rtype not in ("multi_panel", "combined"):
        return None
    data = response.get("data") or {}
    panels = data.get("panels") or data.get("sections") or data.get("cards") or []
    normalized: list[dict[str, Any]] = []
    for panel in panels:
        if isinstance(panel, dict):
            normalized.append(panel)
    return normalized
