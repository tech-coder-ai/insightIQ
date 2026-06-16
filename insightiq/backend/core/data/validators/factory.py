from __future__ import annotations

import importlib

from core.data.validators.base import ISQLValidator
from core.registry import Registry


VALIDATORS: Registry[ISQLValidator] = Registry("validator")


class ValidatorFactory:
    @staticmethod
    def create(dialect: str, **kw: object) -> ISQLValidator:
        try:
            importlib.import_module(f"core.data.validators.{dialect}_validator")
        except ModuleNotFoundError:
            pass
        return VALIDATORS.create(dialect, **kw)

