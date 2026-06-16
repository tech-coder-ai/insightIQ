from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar


class UnknownPluginError(KeyError):
    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"Unknown {kind} plugin: {key}")
        self.kind = kind
        self.key = key


T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._items: dict[str, type[T]] = {}

    def register(self, key: str) -> Callable[[type[T]], type[T]]:
        def deco(cls: type[T]) -> type[T]:
            self._items[key] = cls
            return cls

        return deco

    def create(self, key: str, **kw: object) -> T:
        if key not in self._items:
            raise UnknownPluginError(self._kind, key)
        return self._items[key](**kw)

    def keys(self) -> list[str]:
        return sorted(self._items.keys())

