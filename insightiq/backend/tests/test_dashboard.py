from __future__ import annotations

from core.dashboard.factory import CardRefresherFactory


def test_card_refresher_registry() -> None:
    sql = CardRefresherFactory.create("sql")
    rag = CardRefresherFactory.create("rag")
    assert sql.__class__.__name__ == "SqlCardRefresher"
    assert rag.__class__.__name__ == "RagCardRefresher"
