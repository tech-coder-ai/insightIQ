import hashlib

from core.documents.versioning import build_enterprise_metadata, compute_content_hash, guess_mime_type
from core.ingestion.span_mapper import assign_chunk_highlight_metadata


def test_compute_content_hash_is_stable():
    text = "hello world"
    assert compute_content_hash(text) == hashlib.sha256(text.encode()).hexdigest()


def test_guess_mime_type_from_filename():
    assert guess_mime_type("report.pdf") == "application/pdf"
    assert guess_mime_type("memo.docx").endswith("wordprocessingml.document")


def test_assign_chunk_highlight_metadata_sets_page_and_regions():
    chunks = [{"char_start": 0, "char_end": 20, "text": "hello"}]
    spans = [
        {
            "char_start": 0,
            "char_end": 10,
            "page": 1,
            "bbox": [10, 20, 100, 40],
            "page_width": 595,
            "page_height": 842,
            "text": "hello",
        }
    ]
    assign_chunk_highlight_metadata(chunks, spans)
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["highlight_regions"]
    assert chunks[0]["bbox_json"]["page"] == 1


def test_assign_chunk_highlight_metadata_clips_partial_line_overlap():
    chunks = [{"char_start": 5, "char_end": 10, "text": "world"}]
    spans = [
        {
            "char_start": 0,
            "char_end": 11,
            "page": 1,
            "bbox": [0.0, 10.0, 110.0, 20.0],
            "page_width": 595,
            "page_height": 842,
            "text": "hello world",
        }
    ]
    assign_chunk_highlight_metadata(chunks, spans)
    box = chunks[0]["highlight_regions"][0]["boxes"][0]
    assert box[0] > 0.0
    assert box[2] < 110.0


def test_assign_chunk_highlight_metadata_merges_adjacent_boxes():
    chunks = [{"char_start": 0, "char_end": 20, "text": "hello there"}]
    spans = [
        {
            "char_start": 0,
            "char_end": 5,
            "page": 1,
            "bbox": [0.0, 10.0, 40.0, 20.0],
            "page_width": 595,
            "page_height": 842,
            "text": "hello",
        },
        {
            "char_start": 6,
            "char_end": 11,
            "page": 1,
            "bbox": [42.0, 10.0, 90.0, 20.0],
            "page_width": 595,
            "page_height": 842,
            "text": "there",
        },
    ]
    assign_chunk_highlight_metadata(chunks, spans)
    boxes = chunks[0]["highlight_regions"][0]["boxes"]
    assert len(boxes) == 1
    assert boxes[0][0] == 0.0
    assert boxes[0][2] == 90.0


def test_build_enterprise_metadata_includes_version_fields():
    meta = build_enterprise_metadata(
        base={"document_type": "policy", "tags": ["finance"]},
        source="upload",
        extractor_used="pdf_structured",
        confidence=0.8,
        graph_sync_status="skipped",
        version_number=3,
        content_hash="abc",
        mime_type="application/pdf",
        file_size_bytes=100,
        page_count=5,
    )
    assert meta["version_number"] == 3
    assert meta["document_type"] == "policy"
    assert meta["confidentiality"] == "internal"
    assert "indexed_at" in meta
