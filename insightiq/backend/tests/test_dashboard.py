from __future__ import annotations

import pytest
from fastapi import HTTPException

from core.dashboard.factory import CardRefresherFactory
from services.dashboards.api import _validate_refresh_mode


def test_card_refresher_registry() -> None:
    sql = CardRefresherFactory.create("sql")
    rag = CardRefresherFactory.create("rag")
    assert sql.__class__.__name__ == "SqlCardRefresher"
    assert rag.__class__.__name__ == "RagCardRefresher"


def test_validate_refresh_mode_accepts_known_values() -> None:
    _validate_refresh_mode("snapshot")
    _validate_refresh_mode("live")


def test_validate_refresh_mode_rejects_unknown() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_refresh_mode("streaming")
    assert exc.value.status_code == 400


def test_apply_filters_matches_region_column() -> None:
    from core.dashboard.refreshers.sql import _apply_filters
    from core.data.connectors.base import QueryResult

    result = QueryResult(
        columns=["region", "revenue"],
        rows=[["APAC", 100], ["EMEA", 200], ["apac", 50]],
    )
    filtered = _apply_filters(result, {"region": "APAC"})
    assert filtered.rows == [["APAC", 100], ["apac", 50]]


def test_apply_filters_matches_date_range() -> None:
    from core.dashboard.refreshers.sql import _apply_filters
    from core.data.connectors.base import QueryResult

    result = QueryResult(
        columns=["event_date", "count"],
        rows=[["2026-01-15", 1], ["2026-02-15", 2], ["2026-03-15", 3]],
    )
    filtered = _apply_filters(result, {"date_from": "2026-02-01", "date_to": "2026-02-28"})
    assert filtered.rows == [["2026-02-15", 2]]


def test_apply_filters_noop_when_no_matching_columns() -> None:
    from core.dashboard.refreshers.sql import _apply_filters
    from core.data.connectors.base import QueryResult

    result = QueryResult(columns=["name"], rows=[["a"], ["b"]])
    filtered = _apply_filters(result, {"region": "APAC"})
    assert filtered.rows == [["a"], ["b"]]


def test_apply_filters_returns_same_result_when_empty() -> None:
    from core.dashboard.refreshers.sql import _apply_filters
    from core.data.connectors.base import QueryResult

    result = QueryResult(columns=["name"], rows=[["a"]])
    assert _apply_filters(result, None) is result
    assert _apply_filters(result, {}) is result
