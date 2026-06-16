from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    viewer = "viewer"
    editor = "editor"
    admin = "admin"
    super_admin = "super-admin"

