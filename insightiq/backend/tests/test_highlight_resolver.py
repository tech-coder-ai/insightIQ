from core.rag.highlight_resolver import resolve_highlights
from core.rag.state import RetrievedChunk


def test_resolve_highlights_numbered_refs():
    chunks = [
        RetrievedChunk(
            chunk_id="abc-123",
            document_id="doc-1",
            text="Monthly cost increased by 12% in Q1.",
            char_start=10,
            char_end=50,
            page_number=2,
            relevance_score=0.9,
        )
    ]
    answer = "Costs rose in Q1. [SOURCE:abc-123]"
    result = resolve_highlights(answer, chunks)

    assert "[1]" in result.answer
    assert "[SOURCE:" not in result.answer
    assert len(result.highlight_spans) == 1
    assert result.highlight_spans[0].ref_index == 1
    assert "Monthly cost" in result.highlight_spans[0].text_snippet
