from __future__ import annotations

from core.ingestion.chunkers.factory import CHUNKERS


@CHUNKERS.register("recursive")
class RecursiveChunker(IChunker):
    def __init__(self, *, chunk_size: int = 800, overlap: int = 100) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, text: str, *, document_id: str) -> list[dict]:
        chunks: list[dict] = []
        start = 0
        idx = 0
        while start < len(text):
            end = min(start + self._chunk_size, len(text))
            chunk_text = text[start:end]
            chunks.append(
                {
                    "chunk_id": f"{document_id}:{idx}",
                    "document_id": document_id,
                    "text": chunk_text,
                    "char_start": start,
                    "char_end": end,
                    "page_number": None,
                    "chunk_index": idx,
                }
            )
            if end >= len(text):
                break
            start = end - self._overlap
            idx += 1
        return chunks
