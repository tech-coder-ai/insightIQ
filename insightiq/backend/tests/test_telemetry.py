from __future__ import annotations

import pytest

from core.telemetry.logging import get_correlation_id, set_correlation_id


def test_correlation_id_context() -> None:
    assert get_correlation_id() is None
    set_correlation_id("abc-123")
    assert get_correlation_id() == "abc-123"
