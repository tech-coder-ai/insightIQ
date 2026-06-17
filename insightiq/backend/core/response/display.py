from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any


DEFAULT_DATE_FORMAT_NAME = "yyyy-mm-dd"


@dataclass(frozen=True)
class DateFormatSpec:
    name: str
    python: str
    postgres: str
    duckdb_strftime: str = "%Y-%m-%d"

    def format_date(self, value: dt.date) -> str:
        return value.strftime(self.python)


def detect_date_format(question: str) -> DateFormatSpec:
    """Pick display/SQL date format from the question, defaulting to yyyy-mm-dd."""
    q = question.lower()

    explicit = _extract_explicit_format_phrase(q)
    if explicit:
        spec = _spec_from_tokens(explicit)
        if spec:
            return spec

    if re.search(r"\byyyy[-/ ]mm[-/ ]dd\b|\biso\s+date\b", q):
        return _spec_yyyy_mm_dd()
    if re.search(r"\byyyy[-/ ]mm\b(?![-/]\d)|\byear[- ]month\b|\bmonthly\s+labels\b", q):
        return DateFormatSpec(name="yyyy-mm", python="%Y-%m", postgres="YYYY-MM", duckdb_strftime="%Y-%m")
    if re.search(r"\bmm[-/ ]dd[-/ ]yyyy\b|\bmm/dd/yyyy\b|\bus\s+date\b|\bamerican\s+date\b", q):
        return DateFormatSpec(name="mm/dd/yyyy", python="%m/%d/%Y", postgres="MM/DD/YYYY", duckdb_strftime="%m/%d/%Y")
    if re.search(r"\bdd[-/ ]mm[-/ ]yyyy\b|\bdd/mm/yyyy\b|\beu\s+date\b|\beuropean\s+date\b", q):
        return DateFormatSpec(name="dd/mm/yyyy", python="%d/%m/%Y", postgres="DD/MM/YYYY", duckdb_strftime="%d/%m/%Y")
    if re.search(r"\bdd[-/ ]mm[-/ ]yy\b|\bdd/mm/yy\b", q):
        return DateFormatSpec(name="dd/mm/yy", python="%d/%m/%y", postgres="DD/MM/YY", duckdb_strftime="%d/%m/%y")
    if re.search(r"\bmm[-/ ]dd[-/ ]yy\b|\bmm/dd/yy\b", q):
        return DateFormatSpec(name="mm/dd/yy", python="%m/%d/%y", postgres="MM/DD/YY", duckdb_strftime="%m/%d/%y")

    return _spec_yyyy_mm_dd()


def is_line_chart_question(question: str) -> bool:
    q = question.lower()
    if any(k in q for k in ("line chart", "line graph", "line plot", "line trend")):
        return True
    return "line" in q and any(k in q for k in ("chart", "graph", "plot", "trend"))


def is_chart_question(question: str) -> bool:
    q = question.lower()
    chart_keywords = (
        "chart",
        "graph",
        "plot",
        "trend",
        "month on month",
        "month-on-month",
        "mom",
        "over time",
        "time series",
        "timeseries",
    )
    return any(k in q for k in chart_keywords)


def format_chart_label(value: Any, *, question: str) -> str:
    """Format date/time bucket values for chart axis labels."""
    parsed = _parse_date_like(value)
    if parsed is None:
        return str(value)
    return detect_date_format(question).format_date(parsed)


def format_table_cell(value: Any, *, column_index: int, question: str) -> Any:
    """Format likely date columns in tabular output."""
    if column_index != 0:
        return value
    parsed = _parse_date_like(value)
    if parsed is None:
        return value
    return format_chart_label(value, question=question)


def sql_date_format_clause(dialect: str, question: str, *, date_expr: str, monthly: bool = False) -> str:
    """Return a dialect-specific expression that formats a date as text."""
    fmt = detect_date_format(question)
    d = dialect.lower()
    expr = f"DATE_TRUNC('month', {date_expr})" if monthly else date_expr

    if d in {"postgres", "tsql", "mssql"}:
        return f"TO_CHAR({expr}, '{fmt.postgres}')"
    if d == "duckdb":
        return f"strftime({expr}, '{fmt.duckdb_strftime}')"
    if d == "bigquery":
        return f"FORMAT_DATE('{_bigquery_pattern(fmt)}', {expr})"
    return f"CAST({expr} AS VARCHAR)"


def chart_date_sql_rules(dialect: str, question: str = "") -> str:
    fmt = detect_date_format(question)
    requested = " (user requested)" if fmt.name != DEFAULT_DATE_FORMAT_NAME else " (default)"
    d = dialect.lower()

    if d in {"postgres", "tsql", "mssql"}:
        monthly_expr = f"TO_CHAR(DATE_TRUNC('month', <date_col>), '{fmt.postgres}')"
        daily_expr = f"TO_CHAR(<date_col>, '{fmt.postgres}')"
    elif d == "duckdb":
        monthly_expr = f"strftime(date_trunc('month', <date_col>), '{fmt.duckdb_strftime}')"
        daily_expr = f"strftime(<date_col>, '{fmt.duckdb_strftime}')"
    else:
        monthly_expr = f"format month bucket from <date_col> as text {fmt.name}"
        daily_expr = f"format <date_col> as text {fmt.name}"

    return (
        "Time-series / chart output rules:\n"
        f"- Use date text format {fmt.name}{requested} for the FIRST selected column (never raw date/timestamp).\n"
        f"- Month-over-month / monthly buckets: {monthly_expr} AS period.\n"
        f"- Daily buckets: {daily_expr} AS period.\n"
        "- If the user asked for a specific date format, you MUST use that format exactly.\n"
        "- Put the aggregated metric as the SECOND column (e.g. SUM(amount) AS total_cost).\n"
        "- ORDER BY the time bucket ascending for line/trend charts."
    )


def _spec_yyyy_mm_dd() -> DateFormatSpec:
    return DateFormatSpec(
        name=DEFAULT_DATE_FORMAT_NAME,
        python="%Y-%m-%d",
        postgres="YYYY-MM-DD",
        duckdb_strftime="%Y-%m-%d",
    )


def _extract_explicit_format_phrase(q: str) -> str | None:
    patterns = [
        r"(?:format|formatted|display|show\s+dates?)\s+(?:as|in|like)\s+['\"]?([^'\"?\n]+?)['\"]?(?:\?|$|\s+as\s|\s+for\s|\s+with\s|\s+in\s)",
        r"date\s+format\s+(?:as|of|:)?\s*['\"]?([^'\"?\n]+?)['\"]?(?:\?|$|\s+as\s|\s+for\s|\s+with\s|\s+in\s)",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            return match.group(1).strip()
    return None


def _spec_from_tokens(text: str) -> DateFormatSpec | None:
    normalized = text.lower().strip().strip(".")
    mapping = {
        "yyyy-mm-dd": _spec_yyyy_mm_dd(),
        "yyyy/mm/dd": _spec_yyyy_mm_dd(),
        "iso": _spec_yyyy_mm_dd(),
        "yyyy-mm": DateFormatSpec(name="yyyy-mm", python="%Y-%m", postgres="YYYY-MM", duckdb_strftime="%Y-%m"),
        "yyyy/mm": DateFormatSpec(name="yyyy-mm", python="%Y-%m", postgres="YYYY-MM", duckdb_strftime="%Y-%m"),
        "mm/dd/yyyy": DateFormatSpec(name="mm/dd/yyyy", python="%m/%d/%Y", postgres="MM/DD/YYYY", duckdb_strftime="%m/%d/%Y"),
        "mm-dd-yyyy": DateFormatSpec(name="mm/dd/yyyy", python="%m/%d/%Y", postgres="MM/DD/YYYY", duckdb_strftime="%m/%d/%Y"),
        "dd/mm/yyyy": DateFormatSpec(name="dd/mm/yyyy", python="%d/%m/%Y", postgres="DD/MM/YYYY", duckdb_strftime="%d/%m/%Y"),
        "dd-mm-yyyy": DateFormatSpec(name="dd/mm/yyyy", python="%d/%m/%Y", postgres="DD/MM/YYYY", duckdb_strftime="%d/%m/%Y"),
        "us": DateFormatSpec(name="mm/dd/yyyy", python="%m/%d/%Y", postgres="MM/DD/YYYY", duckdb_strftime="%m/%d/%Y"),
        "eu": DateFormatSpec(name="dd/mm/yyyy", python="%d/%m/%Y", postgres="DD/MM/YYYY", duckdb_strftime="%d/%m/%Y"),
    }
    if normalized in mapping:
        return mapping[normalized]
    for key, spec in mapping.items():
        if key in normalized.replace(" ", ""):
            return spec
    return None


def _bigquery_pattern(fmt: DateFormatSpec) -> str:
    return {
        "yyyy-mm-dd": "%Y-%m-%d",
        "yyyy-mm": "%Y-%m",
        "mm/dd/yyyy": "%m/%d/%Y",
        "dd/mm/yyyy": "%d/%m/%Y",
        "mm/dd/yy": "%m/%d/%y",
        "dd/mm/yy": "%d/%m/%y",
    }.get(fmt.name, "%Y-%m-%d")


def _parse_date_like(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value

    text = str(value).strip()
    if not text:
        return None

    if re.fullmatch(r"\d{4}-\d{2}", text):
        return dt.date(int(text[:4]), int(text[5:7]), 1)

    normalized = text.replace("Z", "+00:00")
    try:
        if "T" in normalized or "+" in normalized[10:] or normalized.endswith("00:00"):
            return dt.datetime.fromisoformat(normalized).date()
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y"):
        try:
            return dt.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None
