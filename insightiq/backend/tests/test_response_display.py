from core.response.display import (
    chart_date_sql_rules,
    detect_date_format,
    format_chart_label,
    is_line_chart_question,
)


def test_format_chart_label_monthly():
    label = format_chart_label("2024-01-01T00:00:00", question="month on month cost line chart")
    assert label == "2024-01-01"


def test_format_chart_label_daily():
    label = format_chart_label("2024-03-15T12:00:00", question="daily trend chart")
    assert label == "2024-03-15"


def test_format_chart_label_user_requested_format():
    label = format_chart_label(
        "2024-03-15T12:00:00",
        question="show month on month cost as line chart, format as mm/dd/yyyy",
    )
    assert label == "03/15/2024"


def test_detect_date_format_defaults_to_iso():
    assert detect_date_format("month on month cost line chart").name == "yyyy-mm-dd"


def test_detect_date_format_explicit_phrase():
    assert detect_date_format("format dates as dd/mm/yyyy").name == "dd/mm/yyyy"


def test_chart_date_sql_rules_uses_requested_format():
    rules = chart_date_sql_rules("postgres", "format as mm/dd/yyyy")
    assert "MM/DD/YYYY" in rules
    assert "user requested" in rules


def test_is_line_chart_question():
    assert is_line_chart_question("show month on month cost as line chart")
