from __future__ import annotations

from io import BytesIO

from pptx import Presentation
from pptx.util import Pt

from core.export.base import EXPORTERS, ExportPayload, ExportResult, IExporter


@EXPORTERS.register("pptx")
class PptxExporter(IExporter):
    async def export(self, *, payload: ExportPayload) -> ExportResult:
        prs = Presentation()
        title_slide = prs.slides.add_slide(prs.slide_layouts[0])
        title_slide.shapes.title.text = payload.title
        title_slide.placeholders[1].text = "InsightIQ dashboard export"

        cards = payload.data.get("cards", [])
        if not cards and payload.content_type == "conversation":
            cards = [
                {
                    "title": f"{m.get('role', 'user')}",
                    "summary": str(m.get("content", ""))[:500],
                }
                for m in payload.data.get("messages", [])
            ]

        for card in cards:
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = str(card.get("title", "Card"))[:80]
            body = slide.placeholders[1].text_frame
            body.clear()
            p = body.paragraphs[0]
            p.text = str(card.get("summary", ""))[:1200]
            p.font.size = Pt(14)

        buffer = BytesIO()
        prs.save(buffer)
        safe = payload.title.replace(" ", "_")[:40]
        return ExportResult(
            filename=f"{safe}.pptx",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            data=buffer.getvalue(),
        )
