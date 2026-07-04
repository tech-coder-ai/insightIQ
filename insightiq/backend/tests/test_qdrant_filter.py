from qdrant_client.http import models as qmodels

from core.retrieval.qdrant_store import QdrantStore


def test_build_filter_uses_valid_is_empty_condition():
    store = QdrantStore()
    filt = store._build_filter("tenant-1", None)
    assert filt.must is not None
    current_only = filt.must[1]
    assert isinstance(current_only, qmodels.Filter)
    empty_cond = current_only.should[1]
    assert isinstance(empty_cond, qmodels.IsEmptyCondition)
    assert empty_cond.is_empty.key == "is_current"


def test_build_filter_allows_untagged_documents_when_tags_filter_present():
    store = QdrantStore()
    filt = store._build_filter("tenant-1", {"tags": ["RAG"]})
    tag_filter = filt.must[2]
    assert isinstance(tag_filter, qmodels.Filter)
    assert isinstance(tag_filter.should[1], qmodels.IsEmptyCondition)
