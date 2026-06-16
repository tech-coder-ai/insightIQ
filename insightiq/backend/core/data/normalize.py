from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from enum import Enum
from typing import Any


def json_safe_value(value: Any) -> Any:
    """Convert DB driver values to JSON-serializable Python types."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {k: json_safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_value(v) for v in value]
    return str(value)


def json_safe_row(row: list[Any]) -> list[Any]:
    return [json_safe_value(cell) for cell in row]
