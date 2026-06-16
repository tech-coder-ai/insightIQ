from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ResponseType(StrEnum):
    kpi_card = "kpi_card"
    data_table = "data_table"
    chart_bar = "chart_bar"
    chart_line = "chart_line"
    chart_pie = "chart_pie"
    chart_scatter = "chart_scatter"
    chart_heatmap = "chart_heatmap"
    multi_panel = "multi_panel"
    explanation = "explanation"
    combined = "combined"
    error = "error"


class ResponsePayload(BaseModel):
    response_type: ResponseType
    title: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
