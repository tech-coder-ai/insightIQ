from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from core.export.base import EXPORTERS, ExportPayload, ExportResult, IExporter


@EXPORTERS.register("pdf")
class PdfExporter(IExporter):
    async def export(self, *, payload: ExportPayload) -> ExportResult:
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        y = height - 50
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, payload.title[:80])
        y -= 30
        c.setFont("Helvetica", 10)

        if payload.content_type == "conversation":
            blocks = payload.data.get("messages", [])
            for msg in blocks:
                header = f"{str(msg.get('role', 'user')).upper()}:"
                body = str(msg.get("content", ""))
                for line in _wrap(f"{header} {body}", 95):
                    if y < 60:
                        c.showPage()
                        y = height - 50
                        c.setFont("Helvetica", 10)
                    c.drawString(50, y, line[:110])
                    y -= 14
                y -= 6
        else:
            for card in payload.data.get("cards", []):
                title = str(card.get("title", "Card"))
                summary = str(card.get("summary", ""))
                for line in _wrap(f"{title}: {summary}", 95):
                    if y < 60:
                        c.showPage()
                        y = height - 50
                        c.setFont("Helvetica", 10)
                    c.drawString(50, y, line[:110])
                    y -= 14
                y -= 8

        c.save()
        safe = payload.title.replace(" ", "_")[:40]
        return ExportResult(
            filename=f"{safe}.pdf",
            media_type="application/pdf",
            data=buffer.getvalue(),
        )


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
