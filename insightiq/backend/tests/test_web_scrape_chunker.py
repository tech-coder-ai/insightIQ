import core.ingestion.chunkers.markdown_aware  # noqa: F401 — register chunkers
from core.ingestion.chunkers.factory import CHUNKERS


def test_web_scrape_chunker_produces_fewer_chunks_than_default():
    text = ("## Section\n\n" + ("Paragraph with some content. " * 40 + "\n\n") * 200).strip()
    doc_id = "00000000-0000-0000-0000-000000000001"
    default_chunks = CHUNKERS.create("markdown_aware").chunk(text, document_id=doc_id)
    web_chunks = CHUNKERS.create("web_scrape").chunk(text, document_id=doc_id)
    assert len(web_chunks) < len(default_chunks)
    assert len(web_chunks) > 0
