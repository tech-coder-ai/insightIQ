from __future__ import annotations

import pytest

from core.export.base import ExportPayload
from core.export.factory import ExporterFactory
from core.registry import UnknownPluginError


@pytest.mark.asyncio
async def test_markdown_conversation_export() -> None:
    exporter = ExporterFactory.create("markdown")
    result = await exporter.export(
        payload=ExportPayload(
            title="Sales Q&A",
            content_type="conversation",
            data={"messages": [{"role": "user", "content": "revenue?"}, {"role": "assistant", "content": "$1M"}]},
        )
    )
    assert result.filename.endswith(".md")
    assert b"revenue" in result.data


@pytest.mark.asyncio
async def test_pdf_dashboard_export() -> None:
    exporter = ExporterFactory.create("pdf")
    result = await exporter.export(
        payload=ExportPayload(
            title="Ops Dashboard",
            content_type="dashboard",
            data={
                "cards": [
                    {
                        "title": "Customers",
                        "response": {
                            "response_type": "data_table",
                            "data": {
                                "columns": ["id", "name"],
                                "rows": [[1, "Alice"], [2, "Bob"]],
                            },
                        },
                    }
                ]
            },
        )
    )
    assert result.filename.endswith(".pdf")
    assert result.data.startswith(b"%PDF")
    assert len(result.data) > 500


@pytest.mark.asyncio
async def test_format_response_text_data_table() -> None:
    from core.export.response_render import format_response_text

    text = format_response_text(
        {
            "response_type": "data_table",
            "data": {"columns": ["region", "total"], "rows": [["APAC", 100]]},
        }
    )
    assert "region" in text
    assert "APAC" in text
    assert "data_table" not in text


@pytest.mark.asyncio
async def test_pptx_exporter_registered() -> None:
    exporter = ExporterFactory.create("pptx")
    result = await exporter.export(
        payload=ExportPayload(
            title="Deck",
            content_type="dashboard",
            data={"cards": [{"title": "Slide 1", "summary": "hello"}]},
        )
    )
    assert result.filename.endswith(".pptx")
    assert len(result.data) > 100


def test_exporter_registry_keys() -> None:
    keys = ExporterFactory.keys()
    assert "markdown" in keys
    assert "pdf" in keys
    assert "pptx" in keys
    with pytest.raises(UnknownPluginError):
        ExporterFactory.create("docx")
