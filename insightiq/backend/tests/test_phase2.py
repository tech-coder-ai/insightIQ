import pytest

from core.data.validators.duckdb_validator import DESTRUCTIVE
from core.response.classifier import classify_and_format
from core.data.connectors.base import QueryResult


def test_duckdb_destructive_sql_blocked() -> None:
    assert DESTRUCTIVE.search("DROP TABLE sales")


def test_classifier_kpi_for_scalar() -> None:
    result = QueryResult(columns=["count"], rows=[[42]])
    payload = classify_and_format(result, question="how many users")
    assert payload.response_type == "kpi_card"


def test_classifier_chart_for_chart_question() -> None:
    result = QueryResult(columns=["region", "revenue"], rows=[["APAC", 100], ["EMEA", 200]])
    payload = classify_and_format(result, question="revenue by region chart")
    assert payload.response_type == "chart_bar"
