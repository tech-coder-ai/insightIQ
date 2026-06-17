from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.export.base import EXPORTERS, ExportPayload, ExportResult, IExporter
from core.export.response_render import format_response_text, response_table_matrix


@EXPORTERS.register("pdf")
class PdfExporter(IExporter):
    async def export(self, *, payload: ExportPayload) -> ExportResult:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=0.6 * inch,
            rightMargin=0.6 * inch,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch,
        )
        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        heading_style = styles["Heading2"]
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
        )

        story: list[Any] = [Paragraph(payload.title[:120], title_style), Spacer(1, 16)]

        if payload.content_type == "conversation":
            for msg in payload.data.get("messages", []):
                role = str(msg.get("role", "user")).upper()
                content = str(msg.get("content", ""))
                story.append(Paragraph(f"{role}", heading_style))
                story.extend(_paragraph_lines(content, body_style))
                story.append(Spacer(1, 10))
        else:
            for card in payload.data.get("cards", []):
                title = str(card.get("title", "Card"))
                response = card.get("response") or {}
                story.append(Paragraph(title[:120], heading_style))
                story.extend(_render_card(response=response, body_style=body_style))
                story.append(Spacer(1, 16))

        doc.build(story)
        safe = payload.title.replace(" ", "_")[:40]
        return ExportResult(
            filename=f"{safe}.pdf",
            media_type="application/pdf",
            data=buffer.getvalue(),
        )


def _render_card(*, response: dict[str, Any], body_style: ParagraphStyle) -> list[Any]:
    blocks: list[Any] = []
    matrix = response_table_matrix(response)
    if matrix:
        table = Table(matrix, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#94a3b8")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        blocks.append(table)
        return blocks

    rtype = str(response.get("response_type", ""))
    data = response.get("data") or {}

    if rtype == "kpi_card":
        label = str(data.get("label", "Value"))
        value = str(data.get("value", ""))
        blocks.append(Paragraph(f"<b>{label}</b>: {value}", body_style))
        return blocks

    text = format_response_text(response)
    blocks.extend(_paragraph_lines(text, body_style))
    return blocks


def _paragraph_lines(text: str, style: ParagraphStyle) -> list[Any]:
    lines: list[Any] = []
    for raw in text.splitlines() or [""]:
        safe = (
            raw.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        lines.append(Paragraph(safe or "&nbsp;", style))
    return lines
