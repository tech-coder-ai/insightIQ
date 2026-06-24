import uuid

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


def test_store_chunk_meta_indexes_composite():
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    class Doc:
        filename = "report.pdf"

    class Chunk:
        id = chunk_id
        document_id = doc_id
        chunk_index = 2
        text = "Sample chunk text"
        page_number = 4

    meta: dict[str, tuple[str, str, int | None]] = {}
    _store_chunk_meta(meta, Chunk(), Doc())  # type: ignore[arg-type]

    assert f"{doc_id}:2" in meta
    assert str(chunk_id) in meta
    assert meta[f"{doc_id}:2"][0] == "report.pdf"
