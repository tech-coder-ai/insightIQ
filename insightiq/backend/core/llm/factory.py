from __future__ import annotations

import importlib

from core.llm.base import ILLMProvider
from core.registry import Registry


LLM_PROVIDERS: Registry[ILLMProvider] = Registry("llm")


class LLMProviderFactory:
    @staticmethod
    def create(provider_key: str, **kw: object) -> ILLMProvider:
        try:
            importlib.import_module(f"core.llm.{provider_key}")
        except ModuleNotFoundError:
            pass
        return LLM_PROVIDERS.create(provider_key, **kw)
