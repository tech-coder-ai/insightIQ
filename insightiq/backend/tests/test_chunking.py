from __future__ import annotations

import pytest

from core.ingestion.chunkers.markdown_aware import MarkdownAwareChunker


def test_chunker_returns_empty_for_blank_text() -> None:
    chunker = MarkdownAwareChunker()
    assert chunker.chunk("   \n\n  ", document_id="doc-1") == []


def test_chunker_splits_on_headers_and_records_parent_offsets() -> None:
    text = (
        "# Section One\n\nSome intro paragraph about section one.\n\n"
        "## Section Two\n\nMore detail goes here about section two, "
        "with enough text to exercise a second chunk in this section "
        "since it exceeds the default child chunk size threshold of "
        "roughly three hundred and eighty characters when repeated.\n\n"
        "Another paragraph in section two to push past the child size limit "
        "and force at least one additional chunk boundary within this section."
    )
    chunker = MarkdownAwareChunker(child_size=120, child_overlap=20, max_parent_size=1800)
    chunks = chunker.chunk(text, document_id="doc-1")

    assert len(chunks) >= 2
    for c in chunks:
        assert c["document_id"] == "doc-1"
        assert c["chunk_id"].startswith("doc-1:")
        # Parent range must fully enclose the child range.
        assert c["parent_char_start"] <= c["char_start"]
        assert c["parent_char_end"] >= c["char_end"]
        assert text[c["char_start"] : c["char_end"]].strip("\n") == c["text"]

    # Chunks from different headers should carry different parent ranges.
    parent_starts = {c["parent_char_start"] for c in chunks}
    assert len(parent_starts) >= 2


def test_chunker_never_ends_a_chunk_inside_fenced_code_block() -> None:
    code = "def f():\n    return 1\n" * 10
    text = f"# Title\n\nIntro text.\n\n```python\n{code}```\n\nOutro text."
    chunker = MarkdownAwareChunker(child_size=40, child_overlap=5, max_parent_size=2000)
    chunks = chunker.chunk(text, document_id="doc-2")

    fence_start = text.index("```")
    fence_end = text.index("```", fence_start + 3) + 3
    for c in chunks:
        # A chunk boundary may re-enter the fence via overlap, but a chunk
        # must never *end* strictly inside the fenced block (which would
        # otherwise emit a truncated code fence).
        if fence_start < c["char_end"] < fence_end:
            pytest.fail(f"chunk ended mid-fence at {c['char_end']} (fence spans {fence_start}-{fence_end})")


def test_chunker_never_ends_a_chunk_inside_markdown_table() -> None:
    table = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n"
    text = f"# Title\n\nIntro.\n\n{table}\nOutro paragraph after the table."
    chunker = MarkdownAwareChunker(child_size=20, child_overlap=5, max_parent_size=2000)
    chunks = chunker.chunk(text, document_id="doc-3")

    table_start = text.index("| A |")
    table_end = table_start + len(table)
    for c in chunks:
        if table_start < c["char_end"] < table_end:
            pytest.fail(f"chunk ended mid-table at {c['char_end']} (table spans {table_start}-{table_end})")


def test_chunker_emits_one_chunk_for_short_sections_without_overlap() -> None:
    text = "# Alpha\n\nShort body.\n\n## Beta\n\nAnother tiny section.\n"
    chunker = MarkdownAwareChunker(child_size=380, child_overlap=60, max_parent_size=1800)
    chunks = chunker.chunk(text, document_id="doc-5")
    assert len(chunks) == 2
    assert "Short body." in chunks[0]["text"]
    assert "Another tiny section." in chunks[1]["text"]


def test_chunker_caps_parent_range_to_max_parent_size() -> None:
    body = "word " * 1000
    text = f"# Big Section\n\n{body}"
    chunker = MarkdownAwareChunker(child_size=200, child_overlap=20, max_parent_size=500)
    chunks = chunker.chunk(text, document_id="doc-4")
    assert chunks
    for c in chunks:
        assert c["parent_char_end"] - c["parent_char_start"] <= 500
