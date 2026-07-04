from core.rag.nodes import _clean_chunk_text, _extract_relevant_sentences, _synthesize_from_chunks
from core.rag.state import RetrievedChunk


def test_clean_chunk_text_strips_markdown_tables():
    raw = "## Title\n\nSome prose here.\n\n| col | val |\n| --- | --- |\n| a | b |\n\nMore text."
    cleaned = _clean_chunk_text(raw)
    assert "| --- |" not in cleaned
    assert "Some prose here." in cleaned
    assert "a b" in cleaned or "a" in cleaned
    assert "More text." in cleaned


def test_clean_chunk_text_flattens_table_cells_to_prose():
    raw = "| import hashlib | def compute_hash(text): return hashlib.sha256(text.encode()).hexdigest() |"
    cleaned = _clean_chunk_text(raw)
    assert "hashlib" in cleaned
    assert "|" not in cleaned


def test_synthesize_from_chunks_produces_markdown_bullets():
    chunks = [
        RetrievedChunk(
            chunk_id="doc:1",
            document_id="doc",
            text=(
                "## Key Concept: Deduplication\n\n"
                "A hash function converts any text into a short, unique fingerprint. "
                "If two documents have the same fingerprint, they are identical."
            ),
            char_start=0,
            char_end=100,
        )
    ]
    answer = _synthesize_from_chunks(chunks, query="explain deduplication")
    assert answer.startswith("## Explain deduplication")
    assert "hash function" in answer.lower()
    assert "| --- |" not in answer
    assert "[SOURCE:doc:1]" in answer


def test_extract_relevant_sentences_prefers_query_overlap():
    text = (
        "Chunking splits documents into smaller pieces. "
        "Deduplication removes identical documents using a content hash. "
        "Embeddings capture semantic meaning."
    )
    sentences = _extract_relevant_sentences(text, "explain deduplication", max_sentences=2)
    assert any("deduplication" in s.lower() or "hash" in s.lower() for s in sentences)
