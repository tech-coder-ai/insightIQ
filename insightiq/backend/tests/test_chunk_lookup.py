import uuid
from pathlib import Path

from services.talk_to_docs.api import _parse_chunk_key, _store_chunk_meta


def test_parse_chunk_key_composite():
    doc_id = uuid.uuid4()
    db_id, pair = _parse_chunk_key(f"{doc_id}:3")
    assert db_id is None
    assert pair == (doc_id, 3)


def test_parse_chunk_key_uuid():
    doc_id = uuid.uuid4()
    db_id, pair = _parse_chunk_key(str(doc_id))
    assert db_id == doc_id
    assert pair is None


def test_store_chunk_meta_indexes_composite(tmp_path: Path):
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    original = tmp_path / "report.pdf"
    original.write_text("pdf bytes", encoding="utf-8")

    class Doc:
        filename = "report.pdf"
        mime_type = "application/pdf"
        storage_path = str(original)
        version_number = 2

    class Chunk:
        id = chunk_id
        document_id = doc_id
        chunk_index = 2
        text = "Sample chunk text"
        page_number = 4
        version_number = 2
        highlight_regions = [{"page": 4, "boxes": [[1, 2, 3, 4]]}]

    meta: dict[str, dict[str, object]] = {}
    _store_chunk_meta(meta, Chunk(), Doc())  # type: ignore[arg-type]

    assert f"{doc_id}:2" in meta
    assert str(chunk_id) in meta
    assert meta[f"{doc_id}:2"]["filename"] == "report.pdf"
    assert meta[f"{doc_id}:2"]["page_number"] == 4
    assert "original_pdf" in meta[f"{doc_id}:2"]["view_modes"]
