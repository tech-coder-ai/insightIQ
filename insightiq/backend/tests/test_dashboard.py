from __future__ import annotations

import pytest
from fastapi import HTTPException

from core.dashboard.factory import CardRefresherFactory
from services.dashboards.api import _validate_refresh_mode


def test_card_refresher_registry() -> None:
    sql = CardRefresherFactory.create("sql")
    rag = CardRefresherFactory.create("rag")
    assert sql.__class__.__name__ == "SqlCardRefresher"
    assert rag.__class__.__name__ == "RagCardRefresher"


def test_validate_refresh_mode_accepts_known_values() -> None:
    _validate_refresh_mode("snapshot")
    _validate_refresh_mode("live")


def test_validate_refresh_mode_rejects_unknown() -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_refresh_mode("streaming")
    assert exc.value.status_code == 400
