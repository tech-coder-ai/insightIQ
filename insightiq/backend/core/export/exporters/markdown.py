from __future__ import annotations

from core.export.base import EXPORTERS, ExportPayload, ExportResult, IExporter


@EXPORTERS.register("markdown")
class MarkdownExporter(IExporter):
    async def export(self, *, payload: ExportPayload) -> ExportResult:
        if payload.content_type == "conversation":
            lines = [f"# {payload.title}", ""]
            for msg in payload.data.get("messages", []):
                role = str(msg.get("role", "user")).upper()
                lines.append(f"## {role}")
                lines.append(str(msg.get("content", "")))
                lines.append("")
            body = "\n".join(lines).encode("utf-8")
        else:
            lines = [f"# {payload.title}", ""]
            for card in payload.data.get("cards", []):
                lines.append(f"## {card.get('title', 'Card')}")
                lines.append(str(card.get("summary", "")))
                lines.append("")
            body = "\n".join(lines).encode("utf-8")
        safe = payload.title.replace(" ", "_")[:40]
        return ExportResult(filename=f"{safe}.md", media_type="text/markdown", data=body)
