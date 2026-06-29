from __future__ import annotations

from pathlib import Path
from typing import Any

CONNECTION_SECRET_MASK = "********"
SECRET_CONNECTION_KEYS = frozenset({"password", "secret_key", "credentials_json", "access_key"})


def mask_connection(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of connection settings safe to expose to clients."""
    if not config:
        return {}
    out = dict(config)
    for key in SECRET_CONNECTION_KEYS:
        if out.get(key):
            out[key] = CONNECTION_SECRET_MASK
    files = out.get("files")
    if isinstance(files, dict):
        out["files"] = {name: Path(str(path)).name for name, path in files.items()}
    return out


def merge_connection(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    """Apply incoming connection edits, preserving stored secrets when omitted or masked."""
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if key in SECRET_CONNECTION_KEYS:
            if not value or value == CONNECTION_SECRET_MASK:
                continue
        elif value is None:
            continue
        merged[key] = value
    return merged
